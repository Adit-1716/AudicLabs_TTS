from fastapi import Cookie, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ApiKey, Membership, Organization, User
from app.rbac import can
from app.security import decode_token, token_hash


class AuthContext:
    def __init__(self, user: User, org: Organization | None, membership: Membership | None):
        self.user = user
        self.org = org
        self.membership = membership
        self.api_key_role = None

    @property
    def role(self):
        if self.user.is_super_admin:
            return "SUPER_ADMIN"
        if self.api_key_role:
            return self.api_key_role
        return self.membership.role if self.membership else None

    def require(self, permission: str):
        if not self.org and not self.user.is_super_admin:
            raise HTTPException(400, "Select an organization (X-Org-Id).")
        if not can(self.role or "CLIENT", permission, self.user.is_super_admin):
            raise HTTPException(403, f"Role {self.role} cannot perform {permission}.")


def _user_from_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    return db.get(User, payload.get("sub"))


def current_auth(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    access_token: str | None = Cookie(default=None),
    token: str | None = Query(default=None),
) -> AuthContext:
    user = None
    if authorization and authorization.lower().startswith("bearer "):
        user = _user_from_token(db, authorization.split(" ", 1)[1])
    if not user:
        user = _user_from_token(db, access_token)
    if not user and token:
        user = _user_from_token(db, token)
    if not user and x_api_key:
        hashed = token_hash(x_api_key)
        key = db.query(ApiKey).filter(ApiKey.key_hash == hashed, ApiKey.revoked_at.is_(None)).first()
        if key:
            org = db.get(Organization, key.organization_id)
            owner = db.get(User, key.created_by)
            if owner and owner.is_active:
                ctx = AuthContext(owner, org, None)
                ctx.api_key_role = "ORG_ADMIN"
                return ctx
    if not user or not user.is_active:
        raise HTTPException(401, "Please sign in.")
    org = db.get(Organization, x_org_id) if x_org_id else None
    membership = None
    if org:
        membership = (
            db.query(Membership)
            .filter(Membership.user_id == user.id, Membership.organization_id == org.id)
            .first()
        )
        if not membership and not user.is_super_admin:
            raise HTTPException(403, "You are not a member of this organization.")
    elif not user.is_super_admin:
        membership = db.query(Membership).filter(Membership.user_id == user.id).first()
        if membership:
            org = db.get(Organization, membership.organization_id)
    return AuthContext(user, org, membership)


def audit(db: Session, ctx: AuthContext, action: str, entity_type: str, entity_id: str | None, request: Request, meta: dict | None = None):
    from app.models import ActivityLog, AuditLog

    db.add(
        AuditLog(
            organization_id=ctx.org.id if ctx.org else None,
            user_id=ctx.user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            ip=request.client.host if request.client else None,
            meta=meta or {},
        )
    )
    db.add(
        ActivityLog(
            user_id=ctx.user.id,
            organization_id=ctx.org.id if ctx.org else None,
            event=action,
            detail=f"{entity_type}:{entity_id or ''}",
        )
    )
