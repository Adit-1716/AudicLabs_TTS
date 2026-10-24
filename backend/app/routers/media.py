import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import AuthContext, audit, current_auth
from app.models import (
    Folder,
    JobStatus,
    MediaFile,
    Membership,
    Priority,
    Project,
    ProjectAssignment,
    ProjectStatus,
    ProjectStatusHistory,
    RoleName,
    UploadHistory,
    UsageRecord,
    User,
    WorkflowRule,
)
from app.services.jobs import enqueue
from app.services.notify import notify
from app.services.pipeline import credits_used_this_month
from app.services.storage import get_bytes, put_bytes

router = APIRouter()

ALLOWED_EXT = {".mp3", ".wav", ".mp4", ".avi", ".mkv", ".aac", ".flac", ".m4a", ".ogg", ".webm"}


class ProjectIn(BaseModel):
    title: str
    category: str = "general"
    priority: Priority = Priority.MEDIUM
    deadline: datetime | None = None
    language: str = "auto"
    spelling_hints: str = ""
    denoise: bool = True
    diarize: bool = True
    client_user_id: str | None = None
    folder_id: str | None = None
    tags: list[str] = []


class AssignIn(BaseModel):
    user_id: str
    role_on_project: str = "transcriber"


class StatusIn(BaseModel):
    status: ProjectStatus
    note: str = ""


def project_out(p: Project, db: Session):
    assignments = [
        {"id": a.id, "user_id": a.user_id, "role_on_project": a.role_on_project}
        for a in db.query(ProjectAssignment).filter(ProjectAssignment.project_id == p.id)
    ]
    media = db.query(MediaFile).filter(MediaFile.project_id == p.id).all()
    return {
        "id": p.id,
        "title": p.title,
        "category": p.category,
        "priority": p.priority.value if hasattr(p.priority, "value") else p.priority,
        "status": p.status.value if hasattr(p.status, "value") else p.status,
        "deadline": p.deadline.isoformat() if p.deadline else None,
        "progress_pct": p.progress_pct,
        "language": p.language,
        "spelling_hints": p.spelling_hints,
        "denoise": p.denoise,
        "diarize": p.diarize,
        "tags": p.tags or [],
        "folder_id": p.folder_id,
        "client_user_id": p.client_user_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "assignments": assignments,
        "media": [media_out(m) for m in media],
    }


def media_out(m: MediaFile):
    return {
        "id": m.id,
        "original_name": m.original_name,
        "content_type": m.content_type,
        "size_bytes": m.size_bytes,
        "job_status": m.job_status.value if hasattr(m.job_status, "value") else m.job_status,
        "job_error": m.job_error,
        "retry_count": m.retry_count,
        "language": m.language,
        "denoise": m.denoise,
        "diarize": m.diarize,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def apply_auto_assign(db: Session, project: Project, org_id: str):
    rules = (
        db.query(WorkflowRule)
        .filter(
            WorkflowRule.organization_id == org_id,
            WorkflowRule.is_active.is_(True),
            WorkflowRule.trigger == "project.created",
            WorkflowRule.action == "auto_assign",
        )
        .all()
    )
    for rule in rules:
        role_name = rule.config.get("role", "TRANSCRIBER")
        try:
            role = RoleName(role_name)
        except ValueError:
            continue
        member = (
            db.query(Membership)
            .filter(Membership.organization_id == org_id, Membership.role == role)
            .first()
        )
        if member:
            db.add(ProjectAssignment(project_id=project.id, user_id=member.user_id, role_on_project="transcriber"))
            project.status = ProjectStatus.ASSIGNED
            notify(
                db,
                member.user_id,
                "Project assigned",
                f"You were auto-assigned to {project.title}.",
                org_id,
                link=f"/projects/{project.id}",
            )


@router.get("/folders")
def folders(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    rows = db.query(Folder).filter(Folder.organization_id == ctx.org.id).all()
    return [{"id": f.id, "name": f.name, "parent_id": f.parent_id} for f in rows]


@router.post("/folders")
def create_folder(body: dict, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("project.create")
    f = Folder(organization_id=ctx.org.id, name=body.get("name") or "Untitled", parent_id=body.get("parent_id"))
    db.add(f)
    db.commit()
    db.refresh(f)
    return {"id": f.id, "name": f.name, "parent_id": f.parent_id}


@router.get("/projects")
def list_projects(
    status: str | None = None,
    category: str | None = None,
    q: str | None = None,
    client_user_id: str | None = None,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(current_auth),
):
    ctx.require("transcript.view")
    query = db.query(Project).filter(Project.organization_id == ctx.org.id)
    if ctx.role == RoleName.CLIENT:
        query = query.filter(Project.client_user_id == ctx.user.id)
    elif ctx.role == RoleName.TRANSCRIBER:
        assigned = db.query(ProjectAssignment.project_id).filter(ProjectAssignment.user_id == ctx.user.id)
        query = query.filter(Project.id.in_(assigned))
    if status:
        query = query.filter(Project.status == status)
    if category:
        query = query.filter(Project.category == category)
    if client_user_id:
        query = query.filter(Project.client_user_id == client_user_id)
    if q:
        query = query.filter(Project.title.ilike(f"%{q}%"))
    return [project_out(p, db) for p in query.order_by(Project.created_at.desc()).all()]


@router.post("/projects")
def create_project(body: ProjectIn, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("project.create")
    p = Project(
        organization_id=ctx.org.id,
        title=body.title,
        category=body.category,
        priority=body.priority,
        deadline=body.deadline,
        language=body.language,
        spelling_hints=body.spelling_hints,
        denoise=body.denoise,
        diarize=body.diarize,
        client_user_id=body.client_user_id or (ctx.user.id if ctx.role == RoleName.CLIENT else None),
        folder_id=body.folder_id,
        tags=body.tags,
        created_by=ctx.user.id,
    )
    db.add(p)
    db.flush()
    db.add(ProjectStatusHistory(project_id=p.id, to_status=ProjectStatus.DRAFT.value, actor_id=ctx.user.id, note="Created"))
    apply_auto_assign(db, p, ctx.org.id)
    audit(db, ctx, "project.create", "project", p.id, request)
    db.commit()
    return project_out(p, db)


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    p = db.get(Project, project_id)
    if not p or p.organization_id != ctx.org.id:
        raise HTTPException(404, "Project not found.")
    history = (
        db.query(ProjectStatusHistory)
        .filter(ProjectStatusHistory.project_id == p.id)
        .order_by(ProjectStatusHistory.created_at.asc())
        .all()
    )
    data = project_out(p, db)
    data["timeline"] = [
        {
            "from_status": h.from_status,
            "to_status": h.to_status,
            "note": h.note,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        }
        for h in history
    ]
    return data


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: dict, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("project.assign")
    p = db.get(Project, project_id)
    if not p or p.organization_id != ctx.org.id:
        raise HTTPException(404, "Project not found.")
    for key in ("title", "category", "language", "spelling_hints", "denoise", "diarize", "progress_pct", "folder_id", "tags"):
        if key in body:
            setattr(p, key, body[key])
    if "priority" in body:
        p.priority = Priority(body["priority"])
    db.commit()
    return project_out(p, db)


@router.post("/projects/{project_id}/assign")
def assign(project_id: str, body: AssignIn, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("project.assign")
    p = db.get(Project, project_id)
    if not p or p.organization_id != ctx.org.id:
        raise HTTPException(404, "Project not found.")
    db.add(ProjectAssignment(project_id=p.id, user_id=body.user_id, role_on_project=body.role_on_project))
    if p.status == ProjectStatus.DRAFT:
        db.add(ProjectStatusHistory(project_id=p.id, from_status=p.status.value, to_status=ProjectStatus.ASSIGNED.value, actor_id=ctx.user.id))
        p.status = ProjectStatus.ASSIGNED
    notify(db, body.user_id, "Assigned to project", p.title, ctx.org.id, link=f"/projects/{p.id}")
    audit(db, ctx, "project.assign", "project", p.id, request)
    db.commit()
    return project_out(p, db)


@router.post("/projects/{project_id}/status")
def set_status(project_id: str, body: StatusIn, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    p = db.get(Project, project_id)
    if not p or p.organization_id != ctx.org.id:
        raise HTTPException(404, "Project not found.")
    if body.status in (ProjectStatus.APPROVED, ProjectStatus.DELIVERED):
        ctx.require("transcript.review")
    elif body.status == ProjectStatus.REVISION_REQUESTED:
        ctx.require("transcript.view")
    else:
        ctx.require("transcript.edit")
    db.add(
        ProjectStatusHistory(
            project_id=p.id,
            from_status=p.status.value if hasattr(p.status, "value") else str(p.status),
            to_status=body.status.value,
            actor_id=ctx.user.id,
            note=body.note,
        )
    )
    p.status = body.status
    if body.status == ProjectStatus.DELIVERED:
        p.progress_pct = 100
    audit(db, ctx, "project.status", "project", p.id, request, {"status": body.status.value})
    db.commit()
    return project_out(p, db)


def _quota_guard(db, ctx):
    used = credits_used_this_month(db, ctx.org.id)
    if used >= ctx.org.monthly_credit_quota:
        raise HTTPException(402, "Monthly workspace credit quota reached. The owner can raise the quota or wait until next month.")
    stored = db.query(MediaFile).filter(MediaFile.organization_id == ctx.org.id).all()
    if sum(m.size_bytes for m in stored) >= ctx.org.storage_quota_bytes:
        raise HTTPException(402, "Organization storage quota reached.")


@router.post("/projects/{project_id}/uploads")
async def upload(
    project_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    language: str = Form("auto"),
    spelling_hints: str = Form(""),
    denoise: bool = Form(True),
    diarize: bool = Form(True),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(current_auth),
):
    ctx.require("media.upload")
    p = db.get(Project, project_id)
    if not p or p.organization_id != ctx.org.id:
        raise HTTPException(404, "Project not found.")
    _quota_guard(db, ctx)
    saved = []
    for upload in files:
        name = upload.filename or "upload.bin"
        ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in ALLOWED_EXT:
            raise HTTPException(422, f"{name} is not a supported format. Use MP3, WAV, MP4, AVI, MKV, AAC, FLAC.")
        data = await upload.read()
        if len(data) > settings.storage_max_file_bytes:
            raise HTTPException(413, "File exceeds 10 GB storage limit.")
        if len(data) > settings.audiclabs_max_file_bytes:
            raise HTTPException(
                413,
                "AudicLabs Speech-to-Text accepts files up to 100 MB. Store large files externally or split them first.",
            )
        key = f"{ctx.org.id}/{p.id}/{hashlib.sha256(data).hexdigest()[:16]}-{name}"
        put_bytes(key, data, upload.content_type or "application/octet-stream")
        media = MediaFile(
            organization_id=ctx.org.id,
            project_id=p.id,
            original_name=name,
            content_type=upload.content_type or "application/octet-stream",
            size_bytes=len(data),
            storage_key=key,
            checksum=hashlib.sha256(data).hexdigest(),
            job_status=JobStatus.QUEUED,
            language=language or p.language,
            spelling_hints=spelling_hints or p.spelling_hints,
            denoise=denoise,
            diarize=diarize,
            created_by=ctx.user.id,
        )
        db.add(media)
        db.flush()
        db.add(
            UploadHistory(
                media_file_id=media.id,
                user_id=ctx.user.id,
                source="web",
                ip=request.client.host if request.client else None,
            )
        )
        try:
            enqueue(media.id)
        except Exception:
            from app.services.pipeline import process_media

            db.commit()
            process_media(media.id)
            db.expire_all()
            media = db.get(MediaFile, media.id)
        saved.append(media)
    audit(db, ctx, "media.upload", "project", p.id, request, {"count": len(saved)})
    db.commit()
    return [media_out(m) for m in saved]


@router.post("/media/{media_id}/retry")
def retry_media(media_id: str, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("media.upload")
    media = db.get(MediaFile, media_id)
    if not media or media.organization_id != ctx.org.id:
        raise HTTPException(404, "Media not found.")
    media.job_status = JobStatus.QUEUED
    media.job_error = None
    db.commit()
    try:
        enqueue(media.id)
    except Exception:
        from app.services.pipeline import process_media

        process_media(media.id)
    return media_out(db.get(MediaFile, media_id))


def _media_range_response(data: bytes, content_type: str, range_header: str | None) -> Response:
    file_size = len(data)
    content_type = content_type or "audio/wav"
    if range_header and range_header.startswith("bytes="):
        try:
            range_val = range_header[6:].strip()
            parts = range_val.split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
            end = min(end, file_size - 1)
            chunk = data[start : end + 1]
            return Response(
                content=chunk,
                status_code=206,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(len(chunk)),
                    "Content-Type": content_type,
                },
            )
        except Exception:
            pass
    return Response(
        content=data,
        status_code=200,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": content_type,
        },
    )


@router.get("/media/{media_id}/stream")
def stream_media(media_id: str, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    media = db.get(MediaFile, media_id)
    if not media or media.organization_id != ctx.org.id:
        raise HTTPException(404, "Media not found.")
    data = get_bytes(media.storage_key)
    return _media_range_response(data, media.content_type, request.headers.get("range"))


@router.get("/media/{media_id}/stream-denoised")
def stream_denoised_media(media_id: str, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    media = db.get(MediaFile, media_id)
    if not media or media.organization_id != ctx.org.id:
        raise HTTPException(404, "Media not found.")
    try:
        data = get_bytes(media.storage_key + ".denoised.wav")
        return _media_range_response(data, "audio/wav", request.headers.get("range"))
    except Exception:
        data = get_bytes(media.storage_key)
        return _media_range_response(data, media.content_type, request.headers.get("range"))



@router.get("/media/{media_id}/status")
def media_status(media_id: str, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    media = db.get(MediaFile, media_id)
    if not media or media.organization_id != ctx.org.id:
        raise HTTPException(404, "Media not found.")
    return media_out(media)
