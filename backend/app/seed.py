from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import (
    Membership,
    Organization,
    OrganizationSettings,
    RoleName,
    SubscriptionPlan,
    User,
    WorkflowRule,
)
from app.security import hash_password


DEMO_PASSWORD = "DemoPass123!"


def seed(db: Session) -> None:
    if db.query(SubscriptionPlan).count() == 0:
        db.add_all(
            [
                SubscriptionPlan(name="Starter", monthly_credits=50, storage_gb=5, price_inr=999, per_minute_inr=12, per_project_inr=299),
                SubscriptionPlan(name="Team", monthly_credits=200, storage_gb=50, price_inr=4999, per_minute_inr=8, per_project_inr=499),
                SubscriptionPlan(name="Studio", monthly_credits=1000, storage_gb=500, price_inr=14999, per_minute_inr=5, per_project_inr=799),
            ]
        )
        db.flush()

    if db.query(User).filter(User.email == "superadmin@transcribehub.local").first():
        return

    team = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == "Team").first()
    org = Organization(
        name="Acme Media",
        slug="acme-media",
        plan_id=team.id if team else None,
        monthly_credit_quota=200,
        storage_quota_bytes=50 * 1024 * 1024 * 1024,
    )
    db.add(org)
    db.flush()
    db.add(
        OrganizationSettings(
            organization_id=org.id,
            billing_email="billing@acme.local",
            sla_hours=24,
        )
    )

    people = [
        ("superadmin@transcribehub.local", "Super Admin", True, None),
        ("admin@acme.local", "Asha Patel", False, RoleName.ORG_ADMIN),
        ("pm@acme.local", "Rohit Sharma", False, RoleName.PROJECT_MANAGER),
        ("transcriber@acme.local", "Meera Iyer", False, RoleName.TRANSCRIBER),
        ("reviewer@acme.local", "Kabir Khan", False, RoleName.REVIEWER),
        ("client@acme.local", "Neha Client", False, RoleName.CLIENT),
        ("billing@acme.local", "Arjun Billing", False, RoleName.BILLING_MANAGER),
    ]
    for email, name, super_admin, role in people:
        u = User(
            email=email,
            full_name=name,
            password_hash=hash_password(DEMO_PASSWORD),
            is_super_admin=super_admin,
            is_active=True,
        )
        db.add(u)
        db.flush()
        if role:
            db.add(Membership(user_id=u.id, organization_id=org.id, role=role))

    db.add(
        WorkflowRule(
            organization_id=org.id,
            name="Auto-assign transcribers",
            trigger="project.created",
            action="auto_assign",
            config={"role": "TRANSCRIBER"},
        )
    )
    db.add(
        WorkflowRule(
            organization_id=org.id,
            name="SLA reminder",
            trigger="deadline.approaching",
            action="notify",
            config={"hours_before": 4},
        )
    )
    db.commit()


def month_window():
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now
