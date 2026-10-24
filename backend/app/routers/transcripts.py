from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import AuthContext, audit, current_auth
from app.models import (
    ClientMessage,
    MediaFile,
    Project,
    ProjectStatus,
    PublicShare,
    QualityScore,
    Review,
    ReviewComment,
    Transcript,
    TranscriptComment,
    TranscriptVersion,
    User,
)
from app.security import random_token, token_hash
from app.services.export import as_docx, as_srt, as_txt
from app.services.grammar import check_and_fix
from app.services.notify import notify
from app.services.storage import presign

router = APIRouter()


class EditIn(BaseModel):
    raw_text: str | None = None
    segments: list | None = None
    speakers: dict | None = None
    note: str = "edit"


class CommentIn(BaseModel):
    body: str
    parent_id: str | None = None
    segment_index: int | None = None


class ReviewIn(BaseModel):
    accuracy_pct: float
    completion_pct: float
    reviewer_score: float
    notes: str = ""
    status: str = "approved"


def _get_t(db, ctx, transcript_id: str) -> Transcript:
    t = db.get(Transcript, transcript_id)
    if not t or t.organization_id != ctx.org.id:
        raise HTTPException(404, "Transcript not found.")
    return t


def transcript_out(t: Transcript, db: Session):
    media = db.get(MediaFile, t.media_file_id)
    project = db.get(Project, t.project_id)
    play_url = None
    try:
        play_url = presign(media.storage_key) if media else None
    except Exception:
        play_url = f"/api/media/{media.id}/stream" if media else None
    return {
        "id": t.id,
        "project_id": t.project_id,
        "project_title": project.title if project else None,
        "media_file_id": t.media_file_id,
        "media_name": media.original_name if media else None,
        "media_type": media.content_type if media else None,
        "raw_text": t.raw_text,
        "segments": t.segments or [],
        "speakers": t.speakers or {},
        "detected_language": t.detected_language,
        "accent_label": t.accent_label,
        "avg_confidence": t.avg_confidence,
        "current_version": t.current_version,
        "is_archived": t.is_archived,
        "play_url": play_url,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@router.get("/transcripts")
def list_transcripts(
    q: str | None = None,
    archived: bool = False,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(current_auth),
):
    ctx.require("transcript.view")
    query = db.query(Transcript).filter(Transcript.organization_id == ctx.org.id, Transcript.is_archived == archived)
    rows = query.order_by(Transcript.updated_at.desc()).all()
    if q:
        ql = q.lower()
        rows = [t for t in rows if ql in (t.raw_text or "").lower() or any(ql in (s.get("text") or "").lower() for s in (t.segments or []))]
    return [transcript_out(t, db) for t in rows]


@router.get("/transcripts/{transcript_id}")
def get_transcript(transcript_id: str, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    return transcript_out(_get_t(db, ctx, transcript_id), db)


@router.patch("/transcripts/{transcript_id}")
def edit_transcript(transcript_id: str, body: EditIn, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.edit")
    t = _get_t(db, ctx, transcript_id)
    if body.raw_text is not None:
        t.raw_text = body.raw_text
    if body.segments is not None:
        t.segments = body.segments
        t.raw_text = " ".join(s.get("text") or "" for s in body.segments)
    if body.speakers is not None:
        t.speakers = body.speakers
    t.current_version += 1
    t.updated_at = datetime.now(timezone.utc)
    db.add(
        TranscriptVersion(
            transcript_id=t.id,
            version=t.current_version,
            raw_text=t.raw_text,
            segments=t.segments,
            speakers=t.speakers,
            editor_id=ctx.user.id,
            note=body.note,
        )
    )
    audit(db, ctx, "transcript.edit", "transcript", t.id, request, {"version": t.current_version})
    db.commit()
    return transcript_out(t, db)


@router.get("/transcripts/{transcript_id}/versions")
def versions(transcript_id: str, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    t = _get_t(db, ctx, transcript_id)
    rows = (
        db.query(TranscriptVersion)
        .filter(TranscriptVersion.transcript_id == t.id)
        .order_by(TranscriptVersion.version.desc())
        .all()
    )
    return [
        {
            "id": v.id,
            "version": v.version,
            "note": v.note,
            "editor_id": v.editor_id,
            "raw_text": v.raw_text,
            "segments": v.segments,
            "speakers": v.speakers,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in rows
    ]


@router.post("/transcripts/{transcript_id}/restore/{version}")
def restore(transcript_id: str, version: int, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.edit")
    t = _get_t(db, ctx, transcript_id)
    v = (
        db.query(TranscriptVersion)
        .filter(TranscriptVersion.transcript_id == t.id, TranscriptVersion.version == version)
        .first()
    )
    if not v:
        raise HTTPException(404, "Version not found.")
    t.raw_text = v.raw_text
    t.segments = v.segments
    t.speakers = v.speakers
    t.current_version += 1
    db.add(
        TranscriptVersion(
            transcript_id=t.id,
            version=t.current_version,
            raw_text=t.raw_text,
            segments=t.segments,
            speakers=t.speakers,
            editor_id=ctx.user.id,
            note=f"Restored v{version}",
        )
    )
    db.commit()
    return transcript_out(t, db)


@router.get("/transcripts/{transcript_id}/comments")
def comments(transcript_id: str, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    rows = db.query(TranscriptComment).filter(TranscriptComment.transcript_id == transcript_id).all()
    users = {u.id: u.full_name for u in db.query(User).all()}
    return [
        {
            "id": c.id,
            "body": c.body,
            "parent_id": c.parent_id,
            "segment_index": c.segment_index,
            "mentions": c.mentions,
            "user_id": c.user_id,
            "user_name": users.get(c.user_id),
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in rows
    ]


@router.post("/transcripts/{transcript_id}/comments")
def add_comment(transcript_id: str, body: CommentIn, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    t = _get_t(db, ctx, transcript_id)
    mentions = []
    for part in body.body.split():
        if part.startswith("@") and len(part) > 1:
            email = part[1:].rstrip(".,")
            u = db.query(User).filter(User.email == email).first()
            if u:
                mentions.append(u.id)
                notify(db, u.id, "You were mentioned", body.body, ctx.org.id, link=f"/transcripts/{t.id}")
    c = TranscriptComment(
        transcript_id=t.id,
        user_id=ctx.user.id,
        parent_id=body.parent_id,
        body=body.body,
        mentions=mentions,
        segment_index=body.segment_index,
    )
    db.add(c)
    db.commit()
    return {"id": c.id}


@router.post("/transcripts/{transcript_id}/grammar")
def grammar(transcript_id: str, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.edit")
    t = _get_t(db, ctx, transcript_id)
    fixed, issues = check_and_fix(t.raw_text or "")
    return {"fixed_text": fixed, "issues": issues, "original": t.raw_text}


@router.post("/transcripts/{transcript_id}/reviews")
def create_review(transcript_id: str, body: ReviewIn, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.review")
    t = _get_t(db, ctx, transcript_id)
    project = db.get(Project, t.project_id)
    turnaround = 0.0
    if project and project.created_at:
        cat = project.created_at if project.created_at.tzinfo else project.created_at.replace(tzinfo=timezone.utc)
        turnaround = (datetime.now(timezone.utc) - cat).total_seconds() / 3600
    review = Review(
        organization_id=ctx.org.id,
        project_id=t.project_id,
        transcript_id=t.id,
        reviewer_id=ctx.user.id,
        status=body.status,
        accuracy_pct=body.accuracy_pct,
        completion_pct=body.completion_pct,
        reviewer_score=body.reviewer_score,
        turnaround_hours=turnaround,
        notes=body.notes,
    )
    db.add(review)
    db.flush()
    _, issues = check_and_fix(t.raw_text or "")
    db.add(QualityScore(review_id=review.id, error_count=len(issues), grammar_issues=issues))
    if body.status == "approved" and project:
        project.status = ProjectStatus.APPROVED
        project.progress_pct = 90
    audit(db, ctx, "review.submit", "review", review.id, request)
    db.commit()
    return {"id": review.id, "status": review.status}


@router.get("/reviews")
def list_reviews(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.review")
    rows = db.query(Review).filter(Review.organization_id == ctx.org.id).order_by(Review.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "project_id": r.project_id,
            "transcript_id": r.transcript_id,
            "status": r.status,
            "accuracy_pct": r.accuracy_pct,
            "completion_pct": r.completion_pct,
            "reviewer_score": r.reviewer_score,
            "turnaround_hours": r.turnaround_hours,
            "notes": r.notes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/reviews/{review_id}/comments")
def review_comment(review_id: str, body: CommentIn, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.review")
    db.add(ReviewComment(review_id=review_id, user_id=ctx.user.id, body=body.body))
    db.commit()
    return {"ok": True}


@router.post("/transcripts/{transcript_id}/share")
def share(transcript_id: str, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.edit")
    t = _get_t(db, ctx, transcript_id)
    token = random_token(18)
    share = PublicShare(
        transcript_id=t.id,
        organization_id=ctx.org.id,
        token_hash=token_hash(token),
        token_hint=token[:8],
        created_by=ctx.user.id,
    )
    db.add(share)
    audit(db, ctx, "transcript.share", "transcript", t.id, request)
    db.commit()
    return {"url": f"{settings.public_base_url}/share/{token}", "token": token}


@router.post("/transcripts/{transcript_id}/share/revoke")
def revoke(transcript_id: str, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.edit")
    rows = db.query(PublicShare).filter(PublicShare.transcript_id == transcript_id, PublicShare.revoked_at.is_(None)).all()
    now = datetime.now(timezone.utc)
    for s in rows:
        s.revoked_at = now
    db.commit()
    return {"revoked": len(rows)}


@router.get("/public/share/{token}")
def public_share(token: str, db: Session = Depends(get_db)):
    s = db.query(PublicShare).filter(PublicShare.token_hash == token_hash(token), PublicShare.revoked_at.is_(None)).first()
    if not s:
        raise HTTPException(404, "This share link is invalid or has been revoked.")
    t = db.get(Transcript, s.transcript_id)
    project = db.get(Project, t.project_id) if t else None
    return {
        "title": project.title if project else "Transcript",
        "raw_text": t.raw_text,
        "segments": t.segments,
        "speakers": t.speakers,
        "read_only": True,
    }


@router.get("/transcripts/{transcript_id}/export.{fmt}")
def export(transcript_id: str, fmt: str, request: Request, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    t = _get_t(db, ctx, transcript_id)
    project = db.get(Project, t.project_id)
    title = project.title if project else "transcript"
    audit(db, ctx, "transcript.export", "transcript", t.id, request, {"fmt": fmt})
    db.commit()
    if fmt == "txt":
        data = as_txt(t.segments or [], t.speakers or {}, t.raw_text)
        return Response(data, media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="{title}.txt"'})
    if fmt == "srt":
        data = as_srt(t.segments or [], t.raw_text)
        return Response(data, media_type="application/x-subrip", headers={"Content-Disposition": f'attachment; filename="{title}.srt"'})
    if fmt == "docx":
        data = as_docx(title, t.segments or [], t.raw_text)
        return Response(
            data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{title}.docx"'},
        )
    raise HTTPException(400, "Format must be txt, srt or docx.")


@router.post("/transcripts/{transcript_id}/archive")
def archive(transcript_id: str, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.edit")
    t = _get_t(db, ctx, transcript_id)
    t.is_archived = True
    db.commit()
    return {"ok": True}


@router.get("/messages")
def messages(project_id: str | None = None, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    q = db.query(ClientMessage).filter(ClientMessage.organization_id == ctx.org.id)
    if project_id:
        q = q.filter(ClientMessage.project_id == project_id)
    rows = q.order_by(ClientMessage.created_at.asc()).all()
    names = {u.id: u.full_name for u in db.query(User).all()}
    return [
        {
            "id": m.id,
            "project_id": m.project_id,
            "sender_id": m.sender_id,
            "sender_name": names.get(m.sender_id),
            "body": m.body,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]


@router.post("/messages")
def send_message(body: dict, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.view")
    m = ClientMessage(
        organization_id=ctx.org.id,
        project_id=body.get("project_id"),
        sender_id=ctx.user.id,
        body=body.get("body") or "",
    )
    db.add(m)
    db.commit()
    return {"id": m.id}
