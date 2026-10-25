"""Text-To-Speech (TTS) Router for AudicLabs.

Provides voice catalog listing, real-time speech audio synthesis,
and one-click creation of transcription/lyrics projects from generated speech.
"""

from __future__ import annotations

import hashlib
import io
import re
import wave
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthContext, audit, current_auth
from app.models import (
    JobStatus,
    MediaFile,
    Priority,
    Project,
    ProjectStatus,
    ProjectStatusHistory,
    RoleName,
    Transcript,
    TranscriptVersion,
    UploadHistory,
)
from app.services.storage import put_bytes
from app.services.tts import list_voices, synthesize_speech

router = APIRouter(prefix="/tts", tags=["TTS"])


class SynthesizeIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000, description="Text or lyrics to synthesize")
    voice: str = Field("audic-voice-asha", description="Voice ID to use")
    rate: float = Field(1.0, ge=0.5, le=2.5, description="Speaking rate (0.5x to 2.5x)")
    pitch: float = Field(1.0, ge=0.5, le=2.0, description="Pitch modifier (0.5 to 2.0)")
    volume: float = Field(1.0, ge=0.1, le=1.0, description="Volume level (0.1 to 1.0)")


class CreateTTSProjectIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    title: str = Field("Synthesized Speech Project", min_length=1, max_length=200)
    voice: str = Field("audic-voice-asha")
    rate: float = Field(1.0, ge=0.5, le=2.5)
    pitch: float = Field(1.0, ge=0.5, le=2.0)
    volume: float = Field(1.0, ge=0.1, le=1.0)
    category: str = Field("lyrics", description="'lyrics', 'podcast', 'dialogue', or 'speech'")
    language: str = Field("en-IN")


@router.get("/voices")
def get_voices():
    """List all available speech synthesis voices with accents, genders, and recommendations."""
    return list_voices()


@router.post("/synthesize")
async def synthesize(body: SynthesizeIn):
    """Synthesize text or song lyrics into a playable WAV audio stream."""
    audio_bytes = await synthesize_speech(
        text=body.text,
        voice=body.voice,
        rate=body.rate,
        pitch=body.pitch,
        volume=body.volume,
    )
    if not audio_bytes:
        raise HTTPException(500, "Speech synthesis failed to produce audio.")

    headers = {
        "Content-Disposition": 'inline; filename="synthesized_speech.wav"',
        "Content-Length": str(len(audio_bytes)),
        "Cache-Control": "no-cache",
        "X-Voice-ID": body.voice,
    }
    return Response(content=audio_bytes, media_type="audio/wav", headers=headers)


@router.post("/create-project")
async def create_project_from_tts(
    body: CreateTTSProjectIn,
    request: Request,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(current_auth),
):
    """Synthesize text into WAV audio, create a project, and generate synchronized turns/lyrics."""
    ctx.require("project.create")

    # 1. Synthesize audio
    audio_bytes = await synthesize_speech(
        text=body.text,
        voice=body.voice,
        rate=body.rate,
        pitch=body.pitch,
        volume=body.volume,
    )
    if not audio_bytes:
        raise HTTPException(500, "Could not generate speech audio.")

    # Calculate actual duration from WAV header
    duration_sec = 10.0
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                duration_sec = max(1.0, frames / rate)
    except Exception:
        pass

    # 2. Create Project
    project = Project(
        organization_id=ctx.org.id,
        title=body.title.strip() or f"TTS Voice Track - {body.voice}",
        category="song" if body.category == "lyrics" else body.category,
        priority=Priority.MEDIUM,
        language=body.language,
        spelling_hints="",
        denoise=False,
        diarize=False,
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
            note=f"Created via Text-to-Speech Studio with voice {body.voice}",
        )
    )

    # 3. Store Audio & MediaFile
    checksum = hashlib.sha256(audio_bytes).hexdigest()
    filename = f"tts_vocal_{checksum[:8]}.wav"
    storage_key = f"{ctx.org.id}/{project.id}/{filename}"
    put_bytes(storage_key, audio_bytes, "audio/wav")

    media = MediaFile(
        organization_id=ctx.org.id,
        project_id=project.id,
        original_name=filename,
        content_type="audio/wav",
        size_bytes=len(audio_bytes),
        storage_key=storage_key,
        checksum=checksum,
        job_status=JobStatus.DONE,
        language=body.language,
        denoise=False,
        diarize=False,
        created_by=ctx.user.id,
    )
    db.add(media)
    db.flush()

    db.add(
        UploadHistory(
            media_file_id=media.id,
            user_id=ctx.user.id,
            source="tts_studio",
            ip=request.client.host if request.client else None,
        )
    )

    # 4. Generate synchronized transcript turns matching sentences/lines
    lines = [ln.strip() for ln in body.text.split("\n") if ln.strip()]
    if not lines:
        # Split on sentence terminators
        lines = [s.strip() for s in re.split(r"[.!?]+", body.text) if s.strip()]
    if not lines:
        lines = [body.text.strip()]

    # Map lines evenly across audio duration
    turns_data = []
    line_time = duration_sec / max(1, len(lines))
    for idx, line in enumerate(lines):
        start_t = round(idx * line_time, 2)
        end_t = round(min(duration_sec, (idx + 1) * line_time), 2)
        speaker_name = "Vocalist" if body.category == "lyrics" else "Speaker 1"
        turns_data.append(
            {
                "speaker": speaker_name,
                "text": line,
                "start": start_t,
                "end": end_t,
                "confidence": 0.99,
            }
        )

    full_transcript_text = "\n".join(lines)
    transcript = Transcript(
        organization_id=ctx.org.id,
        project_id=project.id,
        media_file_id=media.id,
        raw_text=full_transcript_text,
        segments=turns_data,
        speakers={t["speaker"]: t["speaker"] for t in turns_data},
        current_version=1,
    )
    db.add(transcript)
    db.flush()

    # Save initial version
    db.add(
        TranscriptVersion(
            transcript_id=transcript.id,
            version=1,
            raw_text=full_transcript_text,
            segments=turns_data,
            speakers={t["speaker"]: t["speaker"] for t in turns_data},
            editor_id=ctx.user.id,
            note="Initial Text-to-Speech synthesis",
        )
    )

    project.progress_pct = 80
    audit(db, ctx, "tts.project_create", "project", project.id, request, {"voice": body.voice})
    db.commit()

    return {
        "ok": True,
        "project_id": project.id,
        "transcript_id": transcript.id,
        "media_id": media.id,
        "duration_sec": duration_sec,
        "turn_count": len(turns_data),
        "message": "Project created with synthesized vocal audio and synchronized lines.",
    }
