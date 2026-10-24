import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return str(uuid.uuid4())


class RoleName(str, PyEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ORG_ADMIN = "ORG_ADMIN"
    PROJECT_MANAGER = "PROJECT_MANAGER"
    TRANSCRIBER = "TRANSCRIBER"
    REVIEWER = "REVIEWER"
    CLIENT = "CLIENT"
    BILLING_MANAGER = "BILLING_MANAGER"


class ProjectStatus(str, PyEnum):
    DRAFT = "Draft"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "In Progress"
    UNDER_REVIEW = "Under Review"
    REVISION_REQUESTED = "Revision Requested"
    APPROVED = "Approved"
    DELIVERED = "Delivered"
    ARCHIVED = "Archived"


class JobStatus(str, PyEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Priority(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    locale: Mapped[str] = mapped_column(String(16), default="en-IN")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships = relationship("Membership", back_populates="user")


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    plan_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("subscription_plans.id"), nullable=True)
    monthly_credit_quota: Mapped[int] = mapped_column(Integer, default=200)
    storage_quota_bytes: Mapped[int] = mapped_column(BigInteger, default=10 * 1024 * 1024 * 1024)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    settings = relationship("OrganizationSettings", back_populates="organization", uselist=False)
    memberships = relationship("Membership", back_populates="organization")


class OrganizationSettings(Base):
    __tablename__ = "organization_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), unique=True)
    default_language: Mapped[str] = mapped_column(String(16), default="auto")
    denoise_default: Mapped[bool] = mapped_column(Boolean, default=True)
    diarize_default: Mapped[bool] = mapped_column(Boolean, default=True)
    sla_hours: Mapped[int] = mapped_column(Integer, default=24)
    tax_percent: Mapped[float] = mapped_column(Float, default=18.0)
    billing_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    gdpr_dpa_accepted: Mapped[bool] = mapped_column(Boolean, default=True)
    hipaa_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    organization = relationship("Organization", back_populates="settings")


class Membership(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", name="uq_member_org"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    role: Mapped[RoleName] = mapped_column(Enum(RoleName, native_enum=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="memberships")
    organization = relationship("Organization", back_populates="memberships")


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[RoleName] = mapped_column(Enum(RoleName, native_enum=False))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("folders.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), index=True)
    folder_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("folders.id"), nullable=True)
    client_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(80), default="general")
    priority: Mapped[Priority] = mapped_column(Enum(Priority, native_enum=False), default=Priority.MEDIUM)
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus, native_enum=False), default=ProjectStatus.DRAFT)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress_pct: Mapped[float] = mapped_column(Float, default=0)
    language: Mapped[str] = mapped_column(String(16), default="auto")
    spelling_hints: Mapped[str] = mapped_column(Text, default="")
    denoise: Mapped[bool] = mapped_column(Boolean, default=True)
    diarize: Mapped[bool] = mapped_column(Boolean, default=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    media_files = relationship("MediaFile", back_populates="project")
    assignments = relationship("ProjectAssignment", back_populates="project")


class ProjectAssignment(Base):
    __tablename__ = "project_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    role_on_project: Mapped[str] = mapped_column(String(40), default="transcriber")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project = relationship("Project", back_populates="assignments")


class ProjectStatusHistory(Base):
    __tablename__ = "project_status_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"))
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"))
    original_name: Mapped[str] = mapped_column(String(400))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(500))
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    job_status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, native_enum=False), default=JobStatus.QUEUED)
    job_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String(16), default="auto")
    spelling_hints: Mapped[str] = mapped_column(Text, default="")
    denoise: Mapped[bool] = mapped_column(Boolean, default=True)
    diarize: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project = relationship("Project", back_populates="media_files")


class UploadHistory(Base):
    __tablename__ = "upload_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    media_file_id: Mapped[str] = mapped_column(String(36), ForeignKey("media_files.id"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(40), default="web")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"))
    media_file_id: Mapped[str] = mapped_column(String(36), ForeignKey("media_files.id"), unique=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    segments: Mapped[list] = mapped_column(JSON, default=list)
    speakers: Mapped[dict] = mapped_column(JSON, default=dict)
    detected_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    accent_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avg_confidence: Mapped[float] = mapped_column(Float, default=0.9)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TranscriptVersion(Base):
    __tablename__ = "transcript_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    transcript_id: Mapped[str] = mapped_column(String(36), ForeignKey("transcripts.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    segments: Mapped[list] = mapped_column(JSON, default=list)
    speakers: Mapped[dict] = mapped_column(JSON, default=dict)
    editor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TranscriptComment(Base):
    __tablename__ = "transcript_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    transcript_id: Mapped[str] = mapped_column(String(36), ForeignKey("transcripts.id"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("transcript_comments.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    mentions: Mapped[list] = mapped_column(JSON, default=list)
    segment_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"))
    transcript_id: Mapped[str] = mapped_column(String(36), ForeignKey("transcripts.id"))
    reviewer_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), default="pending")
    accuracy_pct: Mapped[float] = mapped_column(Float, default=0)
    completion_pct: Mapped[float] = mapped_column(Float, default=0)
    reviewer_score: Mapped[float] = mapped_column(Float, default=0)
    turnaround_hours: Mapped[float] = mapped_column(Float, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewComment(Base):
    __tablename__ = "review_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    review_id: Mapped[str] = mapped_column(String(36), ForeignKey("reviews.id"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QualityScore(Base):
    __tablename__ = "quality_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    review_id: Mapped[str] = mapped_column(String(36), ForeignKey("reviews.id"))
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    grammar_issues: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    monthly_credits: Mapped[int] = mapped_column(Integer)
    storage_gb: Mapped[int] = mapped_column(Integer)
    price_inr: Mapped[float] = mapped_column(Float)
    per_minute_inr: Mapped[float] = mapped_column(Float, default=8.0)
    per_project_inr: Mapped[float] = mapped_column(Float, default=499.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    number: Mapped[str] = mapped_column(String(40), unique=True)
    subtotal: Mapped[float] = mapped_column(Float)
    tax: Mapped[float] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="open")
    billing_mode: Mapped[str] = mapped_column(String(20), default="per_project")
    line_items: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id"))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    amount: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(40))
    provider_ref: Mapped[str] = mapped_column(String(120), default="sandbox")
    status: Mapped[str] = mapped_column(String(20), default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20), default="in_app")
    link: Mapped[str | None] = mapped_column(String(400), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NotificationHistory(Base):
    __tablename__ = "notification_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    notification_id: Mapped[str] = mapped_column(String(36), ForeignKey("notifications.id"))
    channel: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="sent")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    service: Mapped[str] = mapped_column(String(40))
    credits: Mapped[int] = mapped_column(Integer, default=1)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowRule(Base):
    __tablename__ = "workflow_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(120))
    trigger: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(80))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PublicShare(Base):
    __tablename__ = "public_shares"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    transcript_id: Mapped[str] = mapped_column(String(36), ForeignKey("transcripts.id"))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token_hint: Mapped[str] = mapped_column(String(12))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntegrationAccount(Base):
    __tablename__ = "integration_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    provider: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="connected")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    url: Mapped[str] = mapped_column(String(500))
    secret: Mapped[str] = mapped_column(String(80))
    events: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(12), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClientMessage(Base):
    __tablename__ = "client_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sender_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
