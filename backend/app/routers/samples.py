import hashlib
import mimetypes
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthContext, audit, current_auth
from app.models import (
    JobStatus,
    MediaFile,
    Membership,
    Priority,
    Project,
    ProjectAssignment,
    ProjectStatus,
    ProjectStatusHistory,
    QualityScore,
    Review,
    RoleName,
    Transcript,
    TranscriptVersion,
    UploadHistory,
    User,
)
from app.services.jobs import enqueue
from app.services.notify import notify
from app.services.pipeline import process_media
from app.services.storage import put_bytes

router = APIRouter()

SAMPLE_DEFINITIONS = [
    {
        "id": "sample_interview.wav",
        "name": "Sample Interview (Interviewer & Guest)",
        "filename": "sample_interview.wav",
        "format": "WAV",
        "content_type": "audio/wav",
        "category": "Interview",
        "description": "Standard 2-speaker podcast interview with speaker turns, automated diarization, and noise suppression.",
        "duration_est": "6 sec",
        "speakers": 2,
    },
    {
        "id": "audio3.mp3",
        "name": "Tech Talk Clip 3 (MP3)",
        "filename": "audio3.mp3",
        "format": "MP3",
        "content_type": "audio/mpeg",
        "category": "Speech Benchmark",
        "description": "Compact lightweight MP3 recording for fast speech-to-text benchmark.",
        "duration_est": "15 sec",
        "speakers": 2,
    },
    {
        "id": "audio4.mp3",
        "name": "Audio Lecture 4 (MP3)",
        "filename": "audio4.mp3",
        "format": "MP3",
        "content_type": "audio/mpeg",
        "category": "Lecture",
        "description": "Vocal recording with clear enunciation for accent and spelling hint testing.",
        "duration_est": "20 sec",
        "speakers": 2,
    },
    {
        "id": "audio5.mp3",
        "name": "Studio Podcast 5 (MP3)",
        "filename": "audio5.mp3",
        "format": "MP3",
        "content_type": "audio/mpeg",
        "category": "Podcast",
        "description": "Studio recording demonstrating background noise suppression.",
        "duration_est": "16 sec",
        "speakers": 2,
    },
    {
        "id": "audio2.wav",
        "name": "Hi-Fi Speech Sample 2 (WAV)",
        "filename": "audio2.wav",
        "format": "WAV",
        "content_type": "audio/wav",
        "category": "Studio Recording",
        "description": "Uncompressed high dynamic range WAV audio file.",
        "duration_est": "30 sec",
        "speakers": 2,
    },
    {
        "id": "audio1.wav",
        "name": "Full Length Master 1 (WAV)",
        "filename": "audio1.wav",
        "format": "WAV",
        "content_type": "audio/wav",
        "category": "Long Session",
        "description": "Extended long-form master recording for stress testing and quota governance.",
        "duration_est": "2 min",
        "speakers": 2,
    },
]


def _find_sample_file(filename: str) -> Path | None:
    root = Path(__file__).resolve().parents[3]
    candidates = [
        root / "samples" / filename,
        root / "data" / "uploads" / filename,
        root / filename,
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def _range_response(data: bytes, content_type: str, range_header: str | None) -> Response:
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


@router.get("/samples")
def list_samples():
    """List available sample audio datasets with metadata and direct stream URLs."""
    results = []
    for item in SAMPLE_DEFINITIONS:
        path = _find_sample_file(item["filename"])
        size_bytes = path.stat().st_size if path else 0
        size_kb = size_bytes / 1024
        size_str = f"{size_kb / 1024:.1f} MB" if size_kb >= 1024 else f"{size_kb:.0f} KB"
        results.append(
            {
                **item,
                "size_bytes": size_bytes,
                "size_formatted": size_str,
                "stream_url": f"/api/samples/{item['id']}/stream",
                "available": path is not None,
            }
        )
    return results


@router.get("/samples/{sample_id}/stream")
def stream_sample(sample_id: str, request: Request):
    """Stream sample audio file with HTTP Range support for instant browser sound playback."""
    path = _find_sample_file(sample_id)
    if not path or not path.exists():
        raise HTTPException(404, f"Sample audio file '{sample_id}' not found.")
    data = path.read_bytes()
    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = "audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg"
    return _range_response(data, mime, request.headers.get("range"))


class UseSampleIn(BaseModel):
    sample_id: str
    denoise: bool = True
    diarize: bool = True
    language: str = "auto"
    spelling_hints: str = ""


class CreateFromSampleIn(BaseModel):
    title: str
    sample_id: str
    category: str = "general"
    priority: Priority = Priority.MEDIUM
    denoise: bool = True
    diarize: bool = True
    language: str = "auto"
    spelling_hints: str = ""


@router.post("/projects/{project_id}/use-sample")
def use_sample(
    project_id: str,
    body: UseSampleIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(current_auth),
):
    """Attach a sample dataset audio file to a project and trigger transcription pipeline."""
    ctx.require("media.upload")
    project = db.get(Project, project_id)
    if not project or project.organization_id != ctx.org.id:
        raise HTTPException(404, "Project not found.")

    path = _find_sample_file(body.sample_id)
    if not path or not path.exists():
        raise HTTPException(404, f"Sample audio file '{body.sample_id}' not found.")

    data = path.read_bytes()
    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = "audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg"

    key = f"{ctx.org.id}/{project.id}/{hashlib.sha256(data).hexdigest()[:16]}-{path.name}"
    put_bytes(key, data, mime)

    media = MediaFile(
        organization_id=ctx.org.id,
        project_id=project.id,
        original_name=path.name,
        content_type=mime,
        size_bytes=len(data),
        storage_key=key,
        checksum=hashlib.sha256(data).hexdigest(),
        job_status=JobStatus.QUEUED,
        language=body.language or project.language,
        spelling_hints=body.spelling_hints or project.spelling_hints,
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
            source="sample_dataset",
            ip=request.client.host if request.client else None,
        )
    )

    # Process immediately
    db.commit()
    try:
        enqueue(media.id)
    except Exception:
        pass
    process_media(media.id)

    db.expire_all()
    media = db.get(MediaFile, media.id)
    transcript = db.query(Transcript).filter(Transcript.media_file_id == media.id).first()

    audit(db, ctx, "sample.transcribe", "project", project.id, request, {"sample": body.sample_id})
    db.commit()

    return {
        "ok": True,
        "media_id": media.id,
        "media_name": media.original_name,
        "job_status": media.job_status.value if hasattr(media.job_status, "value") else media.job_status,
        "transcript_id": transcript.id if transcript else None,
        "play_url": f"/api/media/{media.id}/stream",
    }


@router.post("/projects/from-sample")
def create_project_from_sample(
    body: CreateFromSampleIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(current_auth),
):
    """Create project from sample audio dataset in one step and transcribe immediately."""
    ctx.require("project.create")
    project = Project(
        organization_id=ctx.org.id,
        title=body.title,
        category=body.category,
        priority=body.priority,
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
            to_status=ProjectStatus.DRAFT.value,
            actor_id=ctx.user.id,
            note="Created from sample dataset",
        )
    )

    # Auto-assign transcribers if applicable
    from app.routers.media import apply_auto_assign

    apply_auto_assign(db, project, ctx.org.id)

    path = _find_sample_file(body.sample_id)
    if not path or not path.exists():
        raise HTTPException(404, f"Sample audio file '{body.sample_id}' not found.")

    data = path.read_bytes()
    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = "audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg"

    key = f"{ctx.org.id}/{project.id}/{hashlib.sha256(data).hexdigest()[:16]}-{path.name}"
    put_bytes(key, data, mime)

    media = MediaFile(
        organization_id=ctx.org.id,
        project_id=project.id,
        original_name=path.name,
        content_type=mime,
        size_bytes=len(data),
        storage_key=key,
        checksum=hashlib.sha256(data).hexdigest(),
        job_status=JobStatus.QUEUED,
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
            source="sample_dataset",
            ip=request.client.host if request.client else None,
        )
    )

    db.commit()
    try:
        enqueue(media.id)
    except Exception:
        pass
    process_media(media.id)

    db.expire_all()
    media = db.get(MediaFile, media.id)
    transcript = db.query(Transcript).filter(Transcript.media_file_id == media.id).first()

    audit(db, ctx, "project.create_from_sample", "project", project.id, request, {"sample": body.sample_id})
    db.commit()

    return {
        "ok": True,
        "project_id": project.id,
        "project_title": project.title,
        "media_id": media.id,
        "media_name": media.original_name,
        "transcript_id": transcript.id if transcript else None,
        "play_url": f"/api/media/{media.id}/stream",
    }


@router.post("/projects/{project_id}/auto-assign")
def auto_assign_project(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(current_auth),
):
    """Auto-assign transcribers and reviewers to project based on RBAC roles."""
    ctx.require("project.assign")
    project = db.get(Project, project_id)
    if not project or project.organization_id != ctx.org.id:
        raise HTTPException(404, "Project not found.")

    transcriber = (
        db.query(Membership)
        .filter(Membership.organization_id == ctx.org.id, Membership.role == RoleName.TRANSCRIBER)
        .first()
    )
    reviewer = (
        db.query(Membership)
        .filter(Membership.organization_id == ctx.org.id, Membership.role == RoleName.REVIEWER)
        .first()
    )

    assigned_count = 0
    existing = {
        a.user_id for a in db.query(ProjectAssignment).filter(ProjectAssignment.project_id == project.id).all()
    }

    if transcriber and transcriber.user_id not in existing:
        db.add(ProjectAssignment(project_id=project.id, user_id=transcriber.user_id, role_on_project="transcriber"))
        notify(
            db,
            transcriber.user_id,
            "Auto-assigned to project",
            f"You were auto-assigned to {project.title}.",
            ctx.org.id,
            link=f"/projects/{project.id}",
        )
        assigned_count += 1

    if reviewer and reviewer.user_id not in existing:
        db.add(ProjectAssignment(project_id=project.id, user_id=reviewer.user_id, role_on_project="reviewer"))
        notify(
            db,
            reviewer.user_id,
            "Assigned as Reviewer",
            f"You were assigned to review {project.title}.",
            ctx.org.id,
            link=f"/projects/{project.id}",
        )
        assigned_count += 1

    if project.status == ProjectStatus.DRAFT:
        project.status = ProjectStatus.ASSIGNED
        db.add(
            ProjectStatusHistory(
                project_id=project.id,
                from_status=ProjectStatus.DRAFT.value,
                to_status=ProjectStatus.ASSIGNED.value,
                actor_id=ctx.user.id,
                note="Auto-assigned team members",
            )
        )

    audit(db, ctx, "project.auto_assign", "project", project.id, request, {"assigned": assigned_count})
    db.commit()

    from app.routers.media import project_out

    return project_out(project, db)


@router.post("/transcripts/{transcript_id}/auto-score")
def auto_score_transcript(
    transcript_id: str,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(current_auth),
):
    """Automatically score accuracy, completion, and quality metrics for a transcript."""
    ctx.require("transcript.view")
    transcript = db.get(Transcript, transcript_id)
    if not transcript or transcript.organization_id != ctx.org.id:
        raise HTTPException(404, "Transcript not found.")

    segments = transcript.segments or []
    confs = [float(s.get("confidence") or 0.95) for s in segments]
    avg_conf = sum(confs) / len(confs) if confs else 0.95

    # Base accuracy percentage on speech model confidence score
    accuracy_pct = round(avg_conf * 100, 1)

    # Completion percentage
    non_empty = [s for s in segments if s.get("text", "").strip()]
    completion_pct = round((len(non_empty) / len(segments)) * 100, 1) if segments else 100.0

    raw = transcript.raw_text or " ".join(s.get("text", "") for s in segments)
    words = raw.split()
    word_count = len(words)

    duration_sec = 0.0
    if segments:
        duration_sec = max(float(s.get("end") or 0) for s in segments)
    wpm = round((word_count / (duration_sec / 60))) if duration_sec > 5 else 140

    speakers = set(s.get("speaker") for s in segments if s.get("speaker"))
    speaker_count = len(speakers)

    review = db.query(Review).filter(Review.transcript_id == transcript.id).first()
    if not review:
        review = Review(
            organization_id=ctx.org.id,
            project_id=transcript.project_id,
            transcript_id=transcript.id,
            reviewer_id=ctx.user.id,
            status="auto_scored",
            accuracy_pct=accuracy_pct,
            completion_pct=completion_pct,
            reviewer_score=round(avg_conf * 5.0, 1),
            notes="Automatically generated quality assessment",
        )
        db.add(review)
        db.flush()
    else:
        review.accuracy_pct = accuracy_pct
        review.completion_pct = completion_pct
        review.reviewer_score = round(avg_conf * 5.0, 1)

    db.add(
        QualityScore(
            review_id=review.id,
            error_count=0,
            grammar_issues=[],
        )
    )
    db.commit()

    return {
        "transcript_id": transcript.id,
        "accuracy_pct": accuracy_pct,
        "completion_pct": completion_pct,
        "word_count": word_count,
        "speaker_count": speaker_count,
        "duration_seconds": round(duration_sec, 1),
        "words_per_minute": wpm,
        "quality_rating": "Excellent" if accuracy_pct >= 95 else "Good",
    }
