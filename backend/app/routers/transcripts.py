import hashlib
import io
import wave
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import AuthContext, audit, current_auth
from app.models import (
    ClientMessage,
    JobStatus,
    MediaFile,
    Priority,
    Project,
    ProjectStatus,
    ProjectStatusHistory,
    PublicShare,
    QualityScore,
    Review,
    ReviewComment,
    RoleName,
    Transcript,
    TranscriptComment,
    TranscriptVersion,
    UploadHistory,
    User,
)
from app.security import random_token, token_hash
from app.services.export import as_docx, as_pdf, as_srt, as_txt
from app.services.grammar import check_and_fix
from app.services.notify import notify
from app.services.pipeline import credits_used_this_month, process_media
from app.services.storage import get_bytes, presign, put_bytes

router = APIRouter()

ALLOWED_AUDIO_EXT = {".mp3", ".wav", ".mp4", ".avi", ".mkv", ".aac", ".flac", ".m4a", ".ogg", ".webm"}


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


@router.post("/transcripts/{transcript_id}/grammar/apply")
def apply_grammar(transcript_id: str, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    ctx.require("transcript.edit")
    t = _get_t(db, ctx, transcript_id)
    fixed, issues = check_and_fix(t.raw_text or "")
    t.raw_text = fixed
    if t.segments:
        updated_segments = []
        for s in t.segments:
            seg_fixed, _ = check_and_fix(s.get("text", ""))
            updated_segments.append({**s, "text": seg_fixed})
        t.segments = updated_segments
    t.current_version += 1
    db.add(
        TranscriptVersion(
            transcript_id=t.id,
            version=t.current_version,
            raw_text=t.raw_text,
            segments=t.segments,
            speakers=t.speakers,
            editor_id=ctx.user.id,
            note="Auto-applied grammar corrections",
        )
    )
    db.commit()
    return transcript_out(t, db)



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
def export(
    transcript_id: str,
    fmt: str,
    request: Request,
    mode: str | None = None,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(current_auth),
):
    ctx.require("transcript.view")
    t = _get_t(db, ctx, transcript_id)
    project = db.get(Project, t.project_id)
    title = project.title if project else "transcript"
    is_lyrics = (mode == "lyrics") or ("lyric" in (title or "").lower())
    suffix = " - Lyrics" if is_lyrics else ""
    out_filename = f"{title}{suffix}"
    audit(db, ctx, "transcript.export", "transcript", t.id, request, {"fmt": fmt, "mode": mode})
    db.commit()
    if fmt == "txt":
        data = as_txt(t.segments or [], t.speakers or {}, t.raw_text, is_lyrics=is_lyrics)
        return Response(data, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{out_filename}.txt"'})
    if fmt == "srt":
        data = as_srt(t.segments or [], t.raw_text)
        return Response(data, media_type="application/x-subrip; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{out_filename}.srt"'})
    if fmt == "docx":
        data = as_docx(out_filename, t.segments or [], t.raw_text, is_lyrics=is_lyrics)
        return Response(
            data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{out_filename}.docx"'},
        )
    if fmt == "pdf":
        data = as_pdf(out_filename, t.segments or [], t.raw_text, is_lyrics=is_lyrics)
        return Response(
            data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{out_filename}.pdf"'},
        )
    raise HTTPException(400, "Format must be txt, pdf, docx or srt.")


@router.post("/transcripts/{transcript_id}/lyrics/format")
def format_as_lyrics(transcript_id: str, db: Session = Depends(get_db), ctx: AuthContext = Depends(current_auth)):
    """Automatically structure transcript segments into musical song lyrics (Verse, Chorus, Bridge, Outro)."""
    ctx.require("transcript.edit")
    t = _get_t(db, ctx, transcript_id)
    segments = t.segments or []
    if not segments and t.raw_text:
        # Split raw text into rhythmic lines
        lines = [line.strip() for line in t.raw_text.splitlines() if line.strip()]
        segments = [{"start": i * 4.0, "end": (i + 1) * 4.0, "speaker": "Lead Vocal", "text": line} for i, line in enumerate(lines)]

    new_segments = []
    section_names = ["Verse 1", "Chorus", "Verse 2", "Chorus", "Bridge", "Chorus", "Outro"]
    group_size = max(2, len(segments) // max(1, len(section_names))) if segments else 2

    for i, seg in enumerate(segments):
        section_idx = min(len(section_names) - 1, i // max(1, group_size))
        section = section_names[section_idx]
        speaker = seg.get("speaker") or "Lead Vocal"
        if not speaker.startswith("[") and ("Verse" in section or "Chorus" in section):
            speaker_tag = f"🎵 {speaker} ({section})"
        else:
            speaker_tag = speaker

        new_segments.append({
            "start": seg.get("start", 0),
            "end": seg.get("end", (seg.get("start", 0) + 3)),
            "speaker": speaker_tag,
            "text": seg.get("text", "").strip(),
            "section": section,
        })

    t.segments = new_segments
    t.current_version = (t.current_version or 1) + 1
    db.commit()
    return {"ok": True, "count": len(new_segments), "version": t.current_version}



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


# ==============================================================================
# Direct Audio File-to-Text Transcription Endpoints
# ==============================================================================

def _check_transcribe_quota(db: Session, ctx: AuthContext, file_size: int = 0):
    used = credits_used_this_month(db, ctx.org.id)
    if used >= ctx.org.monthly_credit_quota:
        raise HTTPException(
            402,
            "Monthly workspace credit quota reached. The owner can raise the quota or wait until next month.",
        )
    stored = db.query(MediaFile).filter(MediaFile.organization_id == ctx.org.id).all()
    if sum(m.size_bytes for m in stored) + file_size >= ctx.org.storage_quota_bytes:
        raise HTTPException(402, "Organization storage quota reached.")


def _build_transcription_response(transcript: Transcript, media: MediaFile, project: Project) -> dict:
    formatted_lines = []
    for s in (transcript.segments or []):
        st_sec = int(s.get("start") or 0)
        mins = st_sec // 60
        secs = st_sec % 60
        speaker = s.get("speaker") or "Speaker"
        text_chunk = (s.get("text") or "").strip()
        formatted_lines.append(f"[{mins:02d}:{secs:02d}] {speaker}: {text_chunk}")
    formatted_text = "\n".join(formatted_lines) if formatted_lines else (transcript.raw_text or "")

    srt_bytes = as_srt(transcript.segments or [], transcript.raw_text or "")
    srt_text = srt_bytes.decode("utf-8") if isinstance(srt_bytes, bytes) else str(srt_bytes)

    words = (transcript.raw_text or "").split()
    chars = len(transcript.raw_text or "")
    duration_sec = 0.0
    if transcript.segments:
        last = transcript.segments[-1]
        duration_sec = float(last.get("end") or last.get("start") or 0.0)

    return {
        "ok": True,
        "filename": media.original_name,
        "text": transcript.raw_text or "",
        "formatted_text": formatted_text,
        "srt_text": srt_text,
        "segments": transcript.segments or [],
        "speakers": transcript.speakers or {},
        "detected_language": transcript.detected_language or "en-IN",
        "accent_label": transcript.accent_label or transcript.detected_language or "en-IN",
        "avg_confidence": round(transcript.avg_confidence or 0.96, 2),
        "duration_seconds": round(duration_sec, 2),
        "word_count": len(words),
        "character_count": chars,
        "segment_count": len(transcript.segments or []),
        "transcript_id": transcript.id,
        "project_id": project.id,
        "media_id": media.id,
        "current_version": transcript.current_version,
        "play_url": f"/api/media/{media.id}/stream",
        "export_urls": {
            "txt": f"/api/transcripts/{transcript.id}/export.txt",
            "srt": f"/api/transcripts/{transcript.id}/export.srt",
            "docx": f"/api/transcripts/{transcript.id}/export.docx",
            "pdf": f"/api/transcripts/{transcript.id}/export.pdf",
        },
        "message": "Audio file successfully transcribed into text.",
    }


def _find_sample_path(sample_id: str) -> Path | None:
    root = Path(__file__).resolve().parents[3]
    for candidate in [
        root / "samples" / sample_id,
        root / "data" / "uploads" / sample_id,
        root / sample_id,
    ]:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


class TranscribeSampleIn(BaseModel):
    sample_id: str = Field(..., description="Sample ID or filename from benchmark dataset")
    language: str = Field("auto", description="Audio language code (e.g., 'en-US', 'en-IN', 'auto')")
    spelling_hints: str = Field("", description="Optional custom vocabulary or prompt")
    denoise: bool = Field(True, description="Enable automatic background noise suppression")
    diarize: bool = Field(True, description="Enable automated speaker diarization")
    project_title: str | None = Field(None, description="Optional custom title for project")
    category: str = Field("general", description="Project category")


@router.post("/transcripts/transcribe-file")
@router.post("/stt/transcribe")
async def transcribe_audio_file(
    request: Request,
    file: UploadFile = File(..., description="Audio or video file to transcribe into text"),
    language: str = Form("auto"),
    spelling_hints: str = Form(""),
    denoise: bool = Form(True),
    diarize: bool = Form(True),
    project_id: str | None = Form(None),
    project_title: str = Form(""),
    category: str = Form("general"),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(current_auth),
):
    """Directly transcribe any given audio file into structured text with timestamps, speaker turns, and exports."""
    ctx.require("media.upload")
    name = file.filename or "audio_file.wav"
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_AUDIO_EXT:
        raise HTTPException(
            422,
            f"'{name}' format ({ext}) is not supported. Supported audio formats: MP3, WAV, MP4, AVI, MKV, AAC, FLAC, M4A, OGG, WEBM.",
        )

    data = await file.read()
    if len(data) > settings.storage_max_file_bytes:
        raise HTTPException(413, "Audio file exceeds maximum storage limit.")
    if len(data) > settings.audiclabs_max_file_bytes:
        raise HTTPException(413, "AudicLabs Speech-to-Text accepts files up to 100 MB.")

    _check_transcribe_quota(db, ctx, len(data))

    pid = (
        project_id.strip()
        if (project_id and isinstance(project_id, str) and project_id.strip() and project_id not in ("null", "undefined", "None"))
        else None
    )
    if pid:
        project = db.get(Project, pid)
        if not project or project.organization_id != ctx.org.id:
            raise HTTPException(404, "Project not found.")
    else:
        clean_name = name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
        title = project_title.strip() if (project_title and isinstance(project_title, str) and project_title.strip()) else f"Transcript: {clean_name}"
        project = Project(
            organization_id=ctx.org.id,
            title=title,
            category=category if isinstance(category, str) and category else "general",
            priority=Priority.MEDIUM,
            language=language if isinstance(language, str) else "auto",
            spelling_hints=spelling_hints if isinstance(spelling_hints, str) else "",
            denoise=bool(denoise),
            diarize=bool(diarize),
            client_user_id=ctx.user.id if ctx.role == RoleName.CLIENT else None,
            created_by=ctx.user.id,
        )
        db.add(project)
        db.flush()
        db.add(
            ProjectStatusHistory(
                project_id=project.id,
                to_status=ProjectStatus.IN_PROGRESS.value,
                actor_id=ctx.user.id,
                note=f"Created via Direct Audio Transcription ({name})",
            )
        )

    checksum = hashlib.sha256(data).hexdigest()
    key = f"{ctx.org.id}/{project.id}/{checksum[:16]}-{name}"
    put_bytes(key, data, file.content_type or "audio/wav")

    media = MediaFile(
        organization_id=ctx.org.id,
        project_id=project.id,
        original_name=name,
        content_type=file.content_type or "audio/wav",
        size_bytes=len(data),
        storage_key=key,
        checksum=checksum,
        job_status=JobStatus.PROCESSING,
        language=language if (language and language != "auto") else project.language,
        spelling_hints=spelling_hints if isinstance(spelling_hints, str) else project.spelling_hints,
        denoise=bool(denoise),
        diarize=bool(diarize),
        created_by=ctx.user.id,
    )
    db.add(media)
    db.flush()

    db.add(
        UploadHistory(
            media_file_id=media.id,
            user_id=ctx.user.id,
            source="audio_transcriber",
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()

    # Synchronously run speech-to-text pipeline so the user gets text immediately
    process_media(media.id)
    db.expire_all()
    media = db.get(MediaFile, media.id)
    transcript = db.query(Transcript).filter(Transcript.media_file_id == media.id).first()
    if not transcript:
        raise HTTPException(500, f"Speech transcription failed: {media.job_error or 'Unknown processing error'}")

    audit(db, ctx, "transcript.transcribe_file", "transcript", transcript.id, request, {"filename": name, "size_bytes": len(data)})
    db.commit()

    return _build_transcription_response(transcript, media, project)


@router.post("/transcripts/transcribe-to-text")
async def transcribe_audio_to_raw_text(
    request: Request,
    file: UploadFile = File(..., description="Audio file to transcribe directly into plain text"),
    language: str = Form("auto"),
    spelling_hints: str = Form(""),
    denoise: bool = Form(True),
    diarize: bool = Form(True),
    formatted: bool = Form(True),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(current_auth),
):
    """Directly transcribe an audio file into plain text (text/plain) for fast CLI and automation integration."""
    result = await transcribe_audio_file(
        request=request,
        file=file,
        language=language,
        spelling_hints=spelling_hints,
        denoise=denoise,
        diarize=diarize,
        project_id=None,
        project_title="",
        category="general",
        db=db,
        ctx=ctx,
    )
    out_text = result["formatted_text"] if formatted else result["text"]
    headers = {
        "X-Transcript-Id": result["transcript_id"],
        "X-Project-Id": result["project_id"],
        "X-Detected-Language": result["detected_language"],
        "Content-Disposition": f'inline; filename="{result["filename"]}.txt"',
    }
    return PlainTextResponse(content=out_text, headers=headers)


@router.post("/transcripts/transcribe-sample")
def transcribe_sample_file(
    body: TranscribeSampleIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(current_auth),
):
    """Transcribe a preloaded benchmark audio sample file into text with speaker turns and timestamps."""
    ctx.require("media.upload")
    path = _find_sample_path(body.sample_id)
    if not path:
        raise HTTPException(404, f"Sample file '{body.sample_id}' not found.")

    data = path.read_bytes()
    _check_transcribe_quota(db, ctx, len(data))

    clean_name = path.name.rsplit(".", 1)[0].replace("_", " ").title()
    title = body.project_title.strip() if body.project_title else f"Sample Transcript: {clean_name}"
    project = Project(
        organization_id=ctx.org.id,
        title=title,
        category=body.category,
        priority=Priority.MEDIUM,
        language=body.language,
        spelling_hints=body.spelling_hints,
        denoise=body.denoise,
        diarize=body.diarize,
        client_user_id=ctx.user.id if ctx.role == RoleName.CLIENT else None,
        created_by=ctx.user.id,
    )
    db.add(project)
    db.flush()

    db.add(
        ProjectStatusHistory(
            project_id=project.id,
            to_status=ProjectStatus.IN_PROGRESS.value,
            actor_id=ctx.user.id,
            note=f"Created via Direct Sample Transcription ({path.name})",
        )
    )

    checksum = hashlib.sha256(data).hexdigest()
    key = f"{ctx.org.id}/{project.id}/{checksum[:16]}-{path.name}"
    content_type = "audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg"
    put_bytes(key, data, content_type)

    media = MediaFile(
        organization_id=ctx.org.id,
        project_id=project.id,
        original_name=path.name,
        content_type=content_type,
        size_bytes=len(data),
        storage_key=key,
        checksum=checksum,
        job_status=JobStatus.PROCESSING,
        language=body.language,
        spelling_hints=body.spelling_hints,
        denoise=body.denoise,
        diarize=body.diarize,
        created_by=ctx.user.id,
    )
    db.add(media)
    db.flush()

    db.add(
        UploadHistory(
            media_file_id=media.id,
            user_id=ctx.user.id,
            source="sample_transcriber",
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()

    process_media(media.id)
    db.expire_all()
    media = db.get(MediaFile, media.id)
    transcript = db.query(Transcript).filter(Transcript.media_file_id == media.id).first()
    if not transcript:
        raise HTTPException(500, f"Sample transcription failed: {media.job_error or 'Unknown processing error'}")

    audit(db, ctx, "transcript.transcribe_sample", "transcript", transcript.id, request, {"sample_id": body.sample_id})
    db.commit()

    return _build_transcription_response(transcript, media, project)

