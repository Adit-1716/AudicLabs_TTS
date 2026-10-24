from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthContext, audit, current_auth
from app.models import (
    Invite,
    Membership,
    Organization,
    OrganizationSettings,
    RoleName,
    SubscriptionPlan,
    User,
    UserSession,
)
from app.rbac import ASSESSMENT_ROLE
from app.security import (
    create_token,
    hash_password,
    new_totp_secret,
    random_token,
    token_hash,
    totp_uri,
    verify_password,
    verify_totp,
)
from app.services.notify import notify

router = APIRouter()


class RegisterIn(BaseModel):
    email: str
    full_name: str
    password: str
    organization_name: str


class LoginIn(BaseModel):
    email: str
    password: str
    totp: str | None = None


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


class ProfileIn(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    locale: str | None = None
    timezone: str | None = None


class InviteIn(BaseModel):
    email: str
    role: RoleName


class RoleIn(BaseModel):
    role: RoleName


class OrgSettingsIn(BaseModel):
    default_language: str | None = None
    denoise_default: bool | None = None
    diarize_default: bool | None = None
    sla_hours: int | None = None
    tax_percent: float | None = None
    billing_email: str | None = None
    hipaa_mode: bool | None = None
    monthly_credit_quota: int | None = None


def user_out(u: User, membership: Membership | None = None, org: Organization | None = None):
    role = "SUPER_ADMIN" if u.is_super_admin else (membership.role.value if membership else None)
    return {
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name,
        "is_active": u.is_active,
        "is_super_admin": u.is_super_admin,
        "totp_enabled": u.totp_enabled,
        "phone": u.phone,
        "locale": u.locale,
        "timezone": u.timezone,
        "role": role,
        "assessment_role": ASSESSMENT_ROLE.get(membership.role) if membership else ("Owner" if u.is_super_admin else None),
        "organization_id": org.id if org else None,
        "organization_name": org.name if org else None,
    }


@router.post("/auth/register")
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "An account with that email already exists.")
    if len(body.password) < 10:
        raise HTTPException(400, "Password must be at least 10 characters.")
    user = User(
        email=body.email.lower(),
        full_name=body.full_name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in body.organization_name).strip("-")[:80]
    if db.query(Organization).filter(Organization.slug == slug).first():
        slug = slug + "-" + user.id[:6]
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == "Starter").first()
    org = Organization(name=body.organization_name, slug=slug, plan_id=plan.id if plan else None)
    db.add(org)
    db.flush()
    db.add(OrganizationSettings(organization_id=org.id, billing_email=user.email))
    db.add(Membership(user_id=user.id, organization_id=org.id, role=RoleName.ORG_ADMIN))
    token = create_token(user.id)
    audit(db, AuthContext(user, org, None), "auth.register", "user", user.id, request)
    db.commit()
    return {"token": token, "user": user_out(user, None, org)}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password.")
    if not user.is_active:
        raise HTTPException(403, "This account is deactivated.")
    if user.totp_enabled:
        if not body.totp or not user.totp_secret or not verify_totp(user.totp_secret, body.totp):
            raise HTTPException(401, "Two-factor code required.")
    user.last_login_at = datetime.now(timezone.utc)
    membership = db.query(Membership).filter(Membership.user_id == user.id).first()
    org = db.get(Organization, membership.organization_id) if membership else None
    session = UserSession(
        user_id=user.id,
        refresh_hash=token_hash(random_token()),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
    )
    db.add(session)
    audit(db, AuthContext(user, org, membership), "auth.login", "user", user.id, request)
    db.commit()
    return {"token": create_token(user.id), "user": user_out(user, membership, org)}


@router.post("/auth/logout")
def logout(request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    audit(db, ctx, "auth.logout", "user", ctx.user.id, request)
    db.commit()
    return {"ok": True}


@router.get("/auth/me")
def me(ctx: AuthContext = Depends(current_auth)):
    return user_out(ctx.user, ctx.membership, ctx.org)


@router.patch("/auth/profile")
def profile(body: ProfileIn, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    if body.full_name:
        ctx.user.full_name = body.full_name
    if body.phone is not None:
        ctx.user.phone = body.phone
    if body.locale:
        ctx.user.locale = body.locale
    if body.timezone:
        ctx.user.timezone = body.timezone
    db.commit()
    return user_out(ctx.user, ctx.membership, ctx.org)


@router.post("/auth/password")
def change_password(body: PasswordIn, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    if not verify_password(body.current_password, ctx.user.password_hash):
        raise HTTPException(400, "Current password is wrong.")
    if len(body.new_password) < 10:
        raise HTTPException(400, "Password must be at least 10 characters.")
    ctx.user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}


@router.post("/auth/2fa/setup")
def setup_2fa(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    secret = new_totp_secret()
    ctx.user.totp_secret = secret
    ctx.user.totp_enabled = False
    db.commit()
    return {"secret": secret, "otpauth": totp_uri(ctx.user.email, secret)}


@router.post("/auth/2fa/enable")
def enable_2fa(body: dict, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    if not ctx.user.totp_secret or not verify_totp(ctx.user.totp_secret, str(body.get("totp") or "")):
        raise HTTPException(400, "Invalid authenticator code.")
    ctx.user.totp_enabled = True
    db.commit()
    return {"ok": True}


@router.post("/auth/2fa/disable")
def disable_2fa(body: dict, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    if not verify_password(str(body.get("password") or ""), ctx.user.password_hash):
        raise HTTPException(400, "Password required to disable 2FA.")
    ctx.user.totp_enabled = False
    ctx.user.totp_secret = None
    db.commit()
    return {"ok": True}


@router.get("/orgs")
def list_orgs(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    if ctx.user.is_super_admin:
        orgs = db.query(Organization).all()
    else:
        ids = [m.organization_id for m in db.query(Membership).filter(Membership.user_id == ctx.user.id)]
        orgs = db.query(Organization).filter(Organization.id.in_(ids)).all() if ids else []
    return [
        {
            "id": o.id,
            "name": o.name,
            "slug": o.slug,
            "monthly_credit_quota": o.monthly_credit_quota,
            "storage_quota_bytes": o.storage_quota_bytes,
            "is_active": o.is_active,
            "plan_id": o.plan_id,
        }
        for o in orgs
    ]


@router.post("/orgs")
def create_org(body: dict, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    if not ctx.user.is_super_admin:
        raise HTTPException(403, "Only Super Admin can create additional organizations.")
    name = body.get("name") or "New org"
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    org = Organization(name=name, slug=slug)
    db.add(org)
    db.flush()
    db.add(OrganizationSettings(organization_id=org.id))
    audit(db, ctx, "org.create", "organization", org.id, request)
    db.commit()
    return {"id": org.id, "name": org.name, "slug": org.slug}


@router.get("/orgs/current")
def current_org(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    if not ctx.org:
        raise HTTPException(400, "No organization selected.")
    settings = ctx.org.settings or db.query(OrganizationSettings).filter(OrganizationSettings.organization_id == ctx.org.id).first()
    plan = db.get(SubscriptionPlan, ctx.org.plan_id) if ctx.org.plan_id else None
    return {
        "id": ctx.org.id,
        "name": ctx.org.name,
        "slug": ctx.org.slug,
        "monthly_credit_quota": ctx.org.monthly_credit_quota,
        "storage_quota_bytes": ctx.org.storage_quota_bytes,
        "plan": {"id": plan.id, "name": plan.name, "price_inr": plan.price_inr} if plan else None,
        "settings": {
            "default_language": settings.default_language if settings else "auto",
            "denoise_default": settings.denoise_default if settings else True,
            "diarize_default": settings.diarize_default if settings else True,
            "sla_hours": settings.sla_hours if settings else 24,
            "tax_percent": settings.tax_percent if settings else 18,
            "billing_email": settings.billing_email if settings else None,
            "hipaa_mode": settings.hipaa_mode if settings else False,
            "gdpr_dpa_accepted": settings.gdpr_dpa_accepted if settings else True,
        },
    }


@router.patch("/orgs/current")
def update_org(body: OrgSettingsIn, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("org.manage")
    s = db.query(OrganizationSettings).filter(OrganizationSettings.organization_id == ctx.org.id).first()
    if not s:
        s = OrganizationSettings(organization_id=ctx.org.id)
        db.add(s)
    for field in ("default_language", "denoise_default", "diarize_default", "sla_hours", "tax_percent", "billing_email", "hipaa_mode"):
        val = getattr(body, field)
        if val is not None:
            setattr(s, field, val)
    if body.monthly_credit_quota is not None:
        ctx.org.monthly_credit_quota = body.monthly_credit_quota
    audit(db, ctx, "org.update", "organization", ctx.org.id, request)
    db.commit()
    return {"ok": True}


@router.get("/orgs/members")
def members(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    rows = db.query(Membership).filter(Membership.organization_id == ctx.org.id).all()
    out = []
    for m in rows:
        u = db.get(User, m.user_id)
        if u:
            out.append(user_out(u, m, ctx.org))
    return out


@router.post("/orgs/invites")
def invite_member(body: InviteIn, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("members.manage")
    token = random_token(24)
    inv = Invite(
        organization_id=ctx.org.id,
        email=body.email.lower(),
        role=body.role,
        token_hash=token_hash(token),
        invited_by=ctx.user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(inv)
    existing = db.query(User).filter(User.email == body.email.lower()).first()
    if existing:
        notify(
            db,
            existing.id,
            "You were invited",
            f"{ctx.user.full_name} invited you to {ctx.org.name} as {body.role.value}.",
            ctx.org.id,
            link=f"/invite/{token}",
            channels=["in_app", "email"],
        )
    audit(db, ctx, "org.invite", "invite", inv.id, request, {"email": body.email, "role": body.role.value})
    db.commit()
    return {"invite_url": f"/invite/{token}", "token": token, "email": body.email, "role": body.role.value}


@router.post("/orgs/invites/accept")
def accept_invite(body: dict, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    token = body.get("token")
    inv = db.query(Invite).filter(Invite.token_hash == token_hash(token), Invite.accepted_at.is_(None)).first()
    if not inv:
        raise HTTPException(400, "Invite is invalid or expired.")
    exp = inv.expires_at
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and exp < datetime.now(timezone.utc):
        raise HTTPException(400, "Invite is invalid or expired.")
    if ctx.user.email.lower() != inv.email:
        raise HTTPException(403, "This invite was sent to a different email.")
    existing = (
        db.query(Membership)
        .filter(Membership.user_id == ctx.user.id, Membership.organization_id == inv.organization_id)
        .first()
    )
    if not existing:
        db.add(Membership(user_id=ctx.user.id, organization_id=inv.organization_id, role=inv.role))
    inv.accepted_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.patch("/orgs/members/{user_id}")
def change_role(user_id: str, body: RoleIn, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("members.manage")
    m = (
        db.query(Membership)
        .filter(Membership.user_id == user_id, Membership.organization_id == ctx.org.id)
        .first()
    )
    if not m:
        raise HTTPException(404, "Member not found.")
    m.role = body.role
    audit(db, ctx, "org.role_change", "user", user_id, request, {"role": body.role.value})
    db.commit()
    return {"ok": True}


@router.delete("/orgs/members/{user_id}")
def remove_member(user_id: str, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("members.manage")
    m = (
        db.query(Membership)
        .filter(Membership.user_id == user_id, Membership.organization_id == ctx.org.id)
        .first()
    )
    if not m:
        raise HTTPException(404, "Member not found.")
    db.delete(m)
    audit(db, ctx, "org.remove_member", "user", user_id, request)
    db.commit()
    return {"ok": True}


@router.post("/orgs/members/{user_id}/active")
def set_active(user_id: str, body: dict, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("members.manage")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    user.is_active = bool(body.get("is_active", True))
    db.commit()
    return {"id": user.id, "is_active": user.is_active}


@router.get("/plans")
def plans(db: Session = Depends(get_db)):
    return [
        {
            "id": p.id,
            "name": p.name,
            "monthly_credits": p.monthly_credits,
            "storage_gb": p.storage_gb,
            "price_inr": p.price_inr,
            "per_minute_inr": p.per_minute_inr,
            "per_project_inr": p.per_project_inr,
        }
        for p in db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active.is_(True)).all()
    ]
