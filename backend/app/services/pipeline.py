import time
from datetime import datetime, timezone

from app.db import SessionLocal
from app.models import (
    JobStatus,
    MediaFile,
    Project,
    ProjectStatus,
    ProjectStatusHistory,
    Transcript,
    TranscriptVersion,
    UsageRecord,
)
from app.services import audiclabs
from app.services.audiclabs import AudicLabsError
from app.services.storage import get_bytes, put_bytes


def credits_used_this_month(db, org_id: str) -> int:
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.query(UsageRecord).filter(UsageRecord.organization_id == org_id, UsageRecord.created_at >= start).all()
    return sum(r.credits for r in rows)


def record_usage(db, org_id, user_id, service, call):
    db.add(
        UsageRecord(
            organization_id=org_id,
            user_id=user_id,
            service=service,
            credits=1,
            request_id=call.request_id,
            duration_ms=call.duration_ms,
            status_code=call.status,
        )
    )


def process_media(media_id: str) -> None:
    db = SessionLocal()
    media = db.get(MediaFile, media_id)
    if not media:
        db.close()
        return
    media.job_status = JobStatus.PROCESSING
    media.job_error = None
    db.commit()
    try:
        content = get_bytes(media.storage_key)
        working = content
        working_name = media.original_name
        working_type = media.content_type

        if media.denoise:
            call = _run_async(audiclabs.denoise(working_name, working, working_type))
            record_usage(db, media.organization_id, media.created_by, "noise-suppressor", call)
            working = call.body
            working_name = "cleaned.wav"
            working_type = "audio/wav"
            put_bytes(media.storage_key + ".denoised.wav", working, working_type)
            stats = call.headers.get("X-NS-Stats") or call.headers.get("x-ns-stats")
            if stats:
                media.job_error = None

        speakers, dia_segments = {}, []
        if media.diarize:
            call = _run_async(audiclabs.diarize(media.original_name, working, working_type))
            record_usage(db, media.organization_id, media.created_by, "diarization", call)
            speakers, dia_segments = audiclabs.parse_diarization(call.json)

        lang = None if media.language in (None, "", "auto") else media.language
        call = _run_async(
            audiclabs.transcribe(media.original_name, working, working_type, lang, media.spelling_hints or None)
        )
        record_usage(db, media.organization_id, media.created_by, "stt", call)
        parsed = audiclabs.parse_transcript(call.json)
        segments = parsed["segments"] or audiclabs.merge_segments(parsed["text"], dia_segments, speakers)
        if not speakers:
            speakers = {s["speaker"]: s["speaker"] for s in segments}
        confs = [float(s.get("confidence") or 0.9) for s in segments] or [0.9]
        transcript = db.query(Transcript).filter(Transcript.media_file_id == media.id).first()
        if not transcript:
            transcript = Transcript(
                organization_id=media.organization_id,
                project_id=media.project_id,
                media_file_id=media.id,
            )
            db.add(transcript)
            db.flush()
        transcript.raw_text = parsed["text"]
        transcript.segments = segments
        transcript.speakers = speakers
        transcript.detected_language = parsed.get("language") or (lang or "auto")
        transcript.accent_label = transcript.detected_language
        transcript.avg_confidence = sum(confs) / len(confs)
        transcript.current_version = 1
        db.add(
            TranscriptVersion(
                transcript_id=transcript.id,
                version=1,
                raw_text=transcript.raw_text,
                segments=segments,
                speakers=speakers,
                note="Automatic transcription",
            )
        )
        media.job_status = JobStatus.DONE
        project = db.get(Project, media.project_id)
        if project and project.status in (ProjectStatus.DRAFT, ProjectStatus.ASSIGNED):
            db.add(
                ProjectStatusHistory(
                    project_id=project.id,
                    from_status=project.status.value if hasattr(project.status, "value") else str(project.status),
                    to_status=ProjectStatus.IN_PROGRESS.value,
                    note="Transcription finished",
                )
            )
            project.status = ProjectStatus.IN_PROGRESS
            project.progress_pct = 60
        db.commit()
    except AudicLabsError as exc:
        db.rollback()
        media = db.get(MediaFile, media_id)
        media.job_status = JobStatus.FAILED
        media.job_error = exc.message
        media.retry_count += 1
        db.add(
            UsageRecord(
                organization_id=media.organization_id,
                user_id=media.created_by,
                service="audiclabs-error",
                credits=0,
                request_id=exc.request_id,
                duration_ms=0,
                status_code=exc.status,
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        media = db.get(MediaFile, media_id)
        media.job_status = JobStatus.FAILED
        media.job_error = str(exc)
        media.retry_count += 1
        db.commit()
    finally:
        db.close()


def _run_async(coro):
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)
