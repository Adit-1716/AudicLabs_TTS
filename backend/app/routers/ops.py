from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthContext, audit, current_auth
from app.models import (
    ActivityLog,
    ApiKey,
    AuditLog,
    IntegrationAccount,
    Invoice,
    MediaFile,
    Notification,
    Payment,
    Project,
    ProjectStatus,
    Review,
    SubscriptionPlan,
    Transcript,
    UsageRecord,
    User,
    WebhookEndpoint,
    WorkflowRule,
)
from app.security import random_token, sign_payload, token_hash
from app.services import audiclabs
from app.services.notify import notify
from app.services.pipeline import credits_used_this_month

router = APIRouter()


@router.get("/lookups/languages")
async def languages(ctx: AuthContext = Depends(current_auth)):
    try:
        return {"languages": await audiclabs.languages()}
    except Exception as exc:
        return {"languages": ["en-US", "en-IN", "hi-IN", "ta-IN", "ar-SA"], "warning": str(exc)}


@router.get("/lookups/models")
async def models(ctx: AuthContext = Depends(current_auth)):
    try:
        return {"models": await audiclabs.models()}
    except Exception as exc:
        return {"models": ["audic-stt-1"], "warning": str(exc)}


@router.get("/lookups/voices")
async def voices(ctx: AuthContext = Depends(current_auth)):
    try:
        return {"voices": await audiclabs.voices()}
    except Exception as exc:
        return {"voices": [], "warning": str(exc)}


@router.get("/lookups/health")
async def health():
    return await audiclabs.health()


@router.get("/usage")
def usage(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("reports.view")
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.query(UsageRecord).filter(UsageRecord.organization_id == ctx.org.id, UsageRecord.created_at >= start).all()
    by_day = defaultdict(int)
    by_member = defaultdict(int)
    by_service = defaultdict(int)
    for r in rows:
        day = r.created_at.date().isoformat() if r.created_at else "unknown"
        by_day[day] += r.credits
        by_member[r.user_id or "system"] += r.credits
        by_service[r.service] += r.credits
    names = {u.id: u.full_name for u in db.query(User).all()}
    return {
        "month_start": start.isoformat(),
        "quota": ctx.org.monthly_credit_quota,
        "used": sum(r.credits for r in rows),
        "remaining": max(ctx.org.monthly_credit_quota - sum(r.credits for r in rows), 0),
        "by_day": by_day,
        "by_member": {names.get(k, k): v for k, v in by_member.items()},
        "by_service": by_service,
        "calls": [
            {
                "id": r.id,
                "service": r.service,
                "credits": r.credits,
                "request_id": r.request_id,
                "duration_ms": r.duration_ms,
                "status_code": r.status_code,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows[-200:]
        ],
    }


@router.get("/reports/kpis")
def kpis(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("reports.view")
    org = ctx.org.id
    projects = db.query(Project).filter(Project.organization_id == org).all()
    reviews = db.query(Review).filter(Review.organization_id == org).all()
    invoices = db.query(Invoice).filter(Invoice.organization_id == org).all()
    members = db.query(func.count()).select_from(User).scalar()
    pending = sum(1 for p in projects if p.status == ProjectStatus.UNDER_REVIEW)
    completed = sum(1 for p in projects if p.status in (ProjectStatus.APPROVED, ProjectStatus.DELIVERED))
    accuracy = sum(r.accuracy_pct for r in reviews) / len(reviews) if reviews else 0
    tat = sum(r.turnaround_hours for r in reviews) / len(reviews) if reviews else 0
    revenue = sum(i.total for i in invoices if i.status == "paid")
    return {
        "total_projects": len(projects),
        "active_users": members,
        "pending_reviews": pending,
        "completed_projects": completed,
        "revenue": revenue,
        "average_accuracy": round(accuracy, 2),
        "average_delivery_hours": round(tat, 2),
        "credits_used": credits_used_this_month(db, org),
    }


@router.get("/reports/productivity")
def productivity(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("reports.view")
    media = db.query(MediaFile).filter(MediaFile.organization_id == ctx.org.id).all()
    by_user = defaultdict(lambda: {"uploads": 0, "done": 0, "failed": 0})
    names = {u.id: u.full_name for u in db.query(User).all()}
    for m in media:
        row = by_user[m.created_by]
        row["uploads"] += 1
        st = m.job_status.value if hasattr(m.job_status, "value") else m.job_status
        if st == "done":
            row["done"] += 1
        if st == "failed":
            row["failed"] += 1
    return [{"user": names.get(k, k), **v} for k, v in by_user.items()]


@router.post("/billing/invoices")
def create_invoice(body: dict, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("billing.manage")
    settings_row = ctx.org.settings
    tax_pct = settings_row.tax_percent if settings_row else 18
    mode = body.get("billing_mode") or "per_project"
    plan = db.get(SubscriptionPlan, ctx.org.plan_id) if ctx.org.plan_id else None
    if mode == "per_minute":
        minutes = float(body.get("minutes") or 0)
        rate = plan.per_minute_inr if plan else 8
        subtotal = minutes * rate
        items = [{"desc": f"{minutes} minutes", "amount": subtotal}]
    elif mode == "subscription":
        subtotal = plan.price_inr if plan else 4999
        items = [{"desc": f"{plan.name if plan else 'Plan'} subscription", "amount": subtotal}]
    else:
        subtotal = plan.per_project_inr if plan else 499
        items = [{"desc": body.get("description") or "Transcription project", "amount": subtotal}]
    tax = round(subtotal * tax_pct / 100, 2)
    total = round(subtotal + tax, 2)
    count = db.query(Invoice).count() + 1
    inv = Invoice(
        organization_id=ctx.org.id,
        number=f"INV-{datetime.now().year}-{count:04d}",
        subtotal=subtotal,
        tax=tax,
        total=total,
        billing_mode=mode,
        line_items=items,
        due_at=datetime.now(timezone.utc) + timedelta(days=15),
    )
    db.add(inv)
    audit(db, ctx, "invoice.create", "invoice", inv.id, request)
    db.commit()
    db.refresh(inv)
    return invoice_out(inv)


def invoice_out(inv: Invoice):
    return {
        "id": inv.id,
        "number": inv.number,
        "subtotal": inv.subtotal,
        "tax": inv.tax,
        "total": inv.total,
        "currency": inv.currency,
        "status": inv.status,
        "billing_mode": inv.billing_mode,
        "line_items": inv.line_items,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
    }


@router.get("/billing/invoices")
def list_invoices(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    rows = db.query(Invoice).filter(Invoice.organization_id == ctx.org.id).order_by(Invoice.created_at.desc()).all()
    if ctx.role == "CLIENT":
        pass
    return [invoice_out(i) for i in rows]


@router.post("/billing/invoices/{invoice_id}/pay")
def pay_invoice(invoice_id: str, body: dict, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("billing.manage")
    inv = db.get(Invoice, invoice_id)
    if not inv or inv.organization_id != ctx.org.id:
        raise HTTPException(404, "Invoice not found.")
    method = body.get("method") or "upi"
    allowed = {"credit_card", "debit_card", "upi", "paypal", "bank_transfer"}
    if method not in allowed:
        raise HTTPException(400, "Unsupported payment method.")
    # Sandbox processor: cards must pass Luhn-like demo check; UPI/PayPal/bank always succeed in demo.
    if method in {"credit_card", "debit_card"}:
        number = str(body.get("card_number") or "").replace(" ", "")
        if number and not number.endswith("4242") and number != "4111111111111111":
            raise HTTPException(402, "Sandbox card declined. Use a test card ending in 4242.")
    pay = Payment(
        invoice_id=inv.id,
        organization_id=ctx.org.id,
        amount=inv.total,
        method=method,
        provider_ref=f"sandbox_{random_token(8)}",
        status="completed",
    )
    db.add(pay)
    inv.status = "paid"
    audit(db, ctx, "invoice.pay", "invoice", inv.id, request, {"method": method})
    db.commit()
    return {"ok": True, "payment_id": pay.id, "status": "paid"}


@router.post("/orgs/plan")
def change_plan(body: dict, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("billing.manage")
    plan = db.get(SubscriptionPlan, body.get("plan_id"))
    if not plan:
        raise HTTPException(404, "Plan not found.")
    ctx.org.plan_id = plan.id
    ctx.org.monthly_credit_quota = plan.monthly_credits
    ctx.org.storage_quota_bytes = plan.storage_gb * 1024 * 1024 * 1024
    db.commit()
    return {"ok": True, "plan": plan.name}


@router.get("/notifications")
def notifications(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == ctx.user.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "link": n.link,
            "read": n.read_at is not None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in rows
    ]


@router.post("/notifications/{nid}/read")
def read_notification(nid: str, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    n = db.get(Notification, nid)
    if n and n.user_id == ctx.user.id:
        n.read_at = datetime.now(timezone.utc)
        db.commit()
    return {"ok": True}


@router.post("/notifications/broadcast")
def broadcast(body: dict, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("org.manage")
    from app.models import Membership

    members = db.query(Membership).filter(Membership.organization_id == ctx.org.id).all()
    for m in members:
        notify(db, m.user_id, body.get("title") or "Notice", body.get("body") or "", ctx.org.id, channels=["in_app", "email"])
    db.commit()
    return {"sent": len(members)}


@router.get("/audit")
def audit_logs(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("audit.view")
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.organization_id == ctx.org.id)
        .order_by(AuditLog.created_at.desc())
        .limit(300)
        .all()
    )
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "action": a.action,
            "entity_type": a.entity_type,
            "entity_id": a.entity_id,
            "ip": a.ip,
            "meta": a.meta,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]


@router.get("/activity")
def activity(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("audit.view")
    rows = (
        db.query(ActivityLog)
        .filter(ActivityLog.organization_id == ctx.org.id)
        .order_by(ActivityLog.created_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "event": a.event,
            "detail": a.detail,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]


@router.get("/search")
def search(q: str, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    ql = f"%{q}%"
    projects = db.query(Project).filter(Project.organization_id == ctx.org.id, Project.title.ilike(ql)).limit(20).all()
    transcripts = db.query(Transcript).filter(Transcript.organization_id == ctx.org.id, Transcript.raw_text.ilike(ql)).limit(20).all()
    from app.models import Membership

    member_ids = [m.user_id for m in db.query(Membership).filter(Membership.organization_id == ctx.org.id)]
    users = (
        db.query(User).filter(User.id.in_(member_ids), or_(User.full_name.ilike(ql), User.email.ilike(ql))).all()
        if member_ids
        else []
    )
    hits = []
    for t in transcripts:
        idx = (t.raw_text or "").lower().find(q.lower())
        snippet = (t.raw_text or "")[max(0, idx - 40) : idx + 80]
        hits.append({"type": "transcript", "id": t.id, "title": snippet, "highlight": q})
    return {
        "projects": [{"id": p.id, "title": p.title, "status": p.status.value} for p in projects],
        "users": [{"id": u.id, "full_name": u.full_name, "email": u.email} for u in users],
        "transcripts": hits,
        "query": q,
    }


@router.get("/workflow/rules")
def rules(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("workflow.manage")
    rows = db.query(WorkflowRule).filter(WorkflowRule.organization_id == ctx.org.id).all()
    return [
        {"id": r.id, "name": r.name, "trigger": r.trigger, "action": r.action, "config": r.config, "is_active": r.is_active}
        for r in rows
    ]


@router.post("/workflow/rules")
def create_rule(body: dict, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("workflow.manage")
    r = WorkflowRule(
        organization_id=ctx.org.id,
        name=body.get("name") or "Rule",
        trigger=body.get("trigger") or "project.created",
        action=body.get("action") or "notify",
        config=body.get("config") or {},
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id}


@router.post("/workflow/sla-check")
def sla_check(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("workflow.manage")
    now = datetime.now(timezone.utc)
    warned = 0
    for p in db.query(Project).filter(Project.organization_id == ctx.org.id, Project.deadline.isnot(None)).all():
        if p.status in (ProjectStatus.DELIVERED, ProjectStatus.ARCHIVED, ProjectStatus.APPROVED):
            continue
        if not p.deadline:
            continue
        dl = p.deadline if p.deadline.tzinfo else p.deadline.replace(tzinfo=timezone.utc)
        if dl < now:
            notify(db, p.created_by, "SLA missed", f"{p.title} is past its deadline.", ctx.org.id, link=f"/projects/{p.id}")
            warned += 1
        elif dl - now < timedelta(hours=4):
            notify(db, p.created_by, "Deadline approaching", f"{p.title} is due soon.", ctx.org.id, link=f"/projects/{p.id}")
            warned += 1
    db.commit()
    return {"alerts": warned}


@router.get("/integrations")
def integrations(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("org.manage")
    rows = db.query(IntegrationAccount).filter(IntegrationAccount.organization_id == ctx.org.id).all()
    providers = ["google_drive", "onedrive", "dropbox", "microsoft_teams", "zoom", "google_meet"]
    connected = {r.provider: r for r in rows}
    return [
        {
            "provider": p,
            "status": connected[p].status if p in connected else "disconnected",
            "id": connected[p].id if p in connected else None,
            "config": connected[p].config if p in connected else {},
        }
        for p in providers
    ]


@router.post("/integrations/{provider}/connect")
def connect_integration(provider: str, body: dict, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("org.manage")
    acc = IntegrationAccount(
        organization_id=ctx.org.id,
        provider=provider,
        status="connected",
        config={"label": body.get("label") or "Demo connection", "folder": body.get("folder") or "/Inbox"},
    )
    db.add(acc)
    db.commit()
    return {"id": acc.id, "status": "connected"}


@router.post("/integrations/{provider}/import")
def import_from_integration(provider: str, body: dict, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("media.upload")
    url = body.get("url")
    if not url:
        raise HTTPException(400, "Provide a recording or file URL to import.")
    import httpx

    resp = httpx.get(url, timeout=60, follow_redirects=True)
    if resp.status_code >= 400:
        raise HTTPException(400, "Could not download that URL.")
    return {"bytes": len(resp.content), "content_type": resp.headers.get("content-type"), "provider": provider}


@router.get("/webhooks")
def webhooks(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("org.manage")
    rows = db.query(WebhookEndpoint).filter(WebhookEndpoint.organization_id == ctx.org.id).all()
    return [{"id": w.id, "url": w.url, "events": w.events, "is_active": w.is_active} for w in rows]


@router.post("/webhooks")
def create_webhook(body: dict, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("org.manage")
    w = WebhookEndpoint(
        organization_id=ctx.org.id,
        url=body.get("url") or "",
        secret=random_token(12),
        events=body.get("events") or ["project.status", "transcript.done"],
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return {"id": w.id, "secret": w.secret, "url": w.url}


@router.post("/webhooks/inbound/{provider}")
async def inbound_webhook(provider: str, request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("x-signature") or ""
    return {"received": True, "provider": provider, "bytes": len(payload), "signature_present": bool(sig)}


@router.post("/api-keys")
def create_api_key(body: dict, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("org.manage")
    raw = "th_" + random_token(24)
    key = ApiKey(
        organization_id=ctx.org.id,
        name=body.get("name") or "API key",
        prefix=raw[:10],
        key_hash=token_hash(raw),
        created_by=ctx.user.id,
    )
    db.add(key)
    audit(db, ctx, "apikey.create", "api_key", key.id, request)
    db.commit()
    return {"id": key.id, "key": raw, "prefix": key.prefix, "warning": "Copy this key now. It will not be shown again."}


@router.get("/api-keys")
def list_keys(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("org.manage")
    rows = db.query(ApiKey).filter(ApiKey.organization_id == ctx.org.id).all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "prefix": k.prefix,
            "revoked": k.revoked_at is not None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        }
        for k in rows
    ]


@router.delete("/privacy/me")
def gdpr_delete(request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.user.is_active = False
    ctx.user.full_name = "Redacted User"
    ctx.user.email = f"redacted-{ctx.user.id[:8]}@invalid.local"
    audit(db, ctx, "gdpr.delete", "user", ctx.user.id, request)
    db.commit()
    return {"ok": True, "note": "Account deactivated and personal fields redacted."}


@router.get("/privacy/export")
def gdpr_export(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    return {
        "user": {"id": ctx.user.id, "email": ctx.user.email, "full_name": ctx.user.full_name},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "standard": "GDPR data portability",
    }
