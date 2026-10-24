import asyncio
import json
import time
from dataclasses import dataclass

import httpx

from app.config import settings


class AudicLabsError(Exception):
    def __init__(self, status: int, message: str, request_id: str | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.request_id = request_id


@dataclass
class AudicCall:
    status: int
    request_id: str | None
    duration_ms: int
    headers: dict
    body: bytes
    json: dict | None


USER_MESSAGES = {
    401: "The AudicLabs API key is missing or invalid.",
    402: "AudicLabs credits are exhausted. Reply to the assessment email if this key should still have credits.",
    403: "This API key is not allowed to call that AudicLabs service.",
    413: "The media file is larger than AudicLabs allows for this endpoint.",
    422: "The audio or video file could not be processed (invalid_audio).",
    429: "AudicLabs is rate-limiting requests. The job will retry automatically.",
    503: "AudicLabs is temporarily unavailable. The job will retry automatically.",
}


def user_message(status: int, fallback: str) -> str:
    return USER_MESSAGES.get(status, fallback)


async def _request(method: str, url: str, **kwargs) -> AudicCall:
    if not settings.audiclabs_api_key:
        raise AudicLabsError(401, USER_MESSAGES[401])
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {settings.audiclabs_api_key}"
    start = time.perf_counter()
    last_err: AudicLabsError | None = None
    for attempt in range(4):
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.request(method, url, headers=headers, **kwargs)
        duration_ms = int((time.perf_counter() - start) * 1000)
        req_id = resp.headers.get("x-request-id") or resp.headers.get("X-Request-Id")
        body = resp.content
        parsed = None
        if resp.headers.get("content-type", "").startswith("application/json"):
            try:
                parsed = resp.json()
            except Exception:
                parsed = None
        if resp.status_code in (429, 503):
            retry_after = resp.headers.get("Retry-After", "2")
            try:
                wait = min(float(retry_after), 30.0)
            except ValueError:
                wait = 2.0 * (attempt + 1)
            last_err = AudicLabsError(resp.status_code, user_message(resp.status_code, resp.text), req_id)
            await asyncio.sleep(wait)
            continue
        if resp.status_code >= 400:
            raise AudicLabsError(resp.status_code, user_message(resp.status_code, resp.text[:500]), req_id)
        return AudicCall(resp.status_code, req_id, duration_ms, dict(resp.headers), body, parsed)
    assert last_err
    raise last_err


def _url(path: str) -> str:
    return settings.audiclabs_base_url.rstrip("/") + path


async def health() -> dict:
    if not settings.audiclabs_api_key and settings.audiclabs_demo_fallback:
        return {"ok": True, "service": "audiclabs-stt", "mode": "demo_fallback", "status": 200}
    try:
        call = await _request("GET", _url("/stt/health"))
        return {"ok": True, "request_id": call.request_id, "body": call.json}
    except AudicLabsError as exc:
        return {"ok": False, "error": exc.message, "status": exc.status, "request_id": exc.request_id}


async def languages() -> list:
    if not settings.audiclabs_api_key and settings.audiclabs_demo_fallback:
        return [
            {"code": "auto", "name": "Auto-detect"},
            {"code": "en-US", "name": "English (US)"},
            {"code": "en-IN", "name": "English (India)"},
            {"code": "hi-IN", "name": "Hindi (India)"},
            {"code": "ta-IN", "name": "Tamil (India)"},
            {"code": "te-IN", "name": "Telugu (India)"},
            {"code": "es-ES", "name": "Spanish"},
            {"code": "fr-FR", "name": "French"},
            {"code": "de-DE", "name": "German"},
        ]
    call = await _request("GET", _url("/stt/languages"))
    data = call.json or []
    if isinstance(data, dict):
        data = data.get("languages") or data.get("data") or []
    return data


async def models() -> list:
    if not settings.audiclabs_api_key and settings.audiclabs_demo_fallback:
        return ["audic-stt-1", "audic-stt-pro"]
    call = await _request("GET", _url("/stt/models"))
    data = call.json or []
    if isinstance(data, dict):
        data = data.get("models") or data.get("data") or []
    return data


async def voices() -> list:
    if not settings.audiclabs_api_key and settings.audiclabs_demo_fallback:
        return [
            {"id": "audic-voice-asha", "name": "Asha (en-IN)"},
            {"id": "audic-voice-rohit", "name": "Rohit (en-IN)"},
            {"id": "audic-voice-aditya", "name": "Aditya (en-IN)"},
        ]
    call = await _request("GET", _url("/tts/voices"))
    data = call.json or []
    if isinstance(data, dict):
        data = data.get("voices") or data.get("data") or []
    return data


async def denoise(filename: str, content: bytes, content_type: str, model: str = "audic-3") -> AudicCall:
    if not settings.audiclabs_api_key and settings.audiclabs_demo_fallback:
        return AudicCall(
            status=200,
            request_id="demo-ns-001",
            duration_ms=64,
            headers={"X-Request-Id": "demo-ns-001", "X-NS-Stats": "snr_improvement_db=15.4"},
            body=content,
            json=None,
        )
    files = {"file": (filename, content, content_type)}
    return await _request("POST", _url("/noise-suppressor/denoise"), files=files, data={"model": model})


async def diarize(filename: str, content: bytes, content_type: str) -> AudicCall:
    if not settings.audiclabs_api_key and settings.audiclabs_demo_fallback:
        dia_payload = {
            "speakers": {"1": "Speaker 1 (Interviewer)", "2": "Speaker 2 (Guest)"},
            "segments": [
                {"start": 0.0, "end": 4.5, "speaker": "1", "confidence": 0.97},
                {"start": 4.8, "end": 11.2, "speaker": "2", "confidence": 0.95},
                {"start": 11.5, "end": 17.8, "speaker": "1", "confidence": 0.98},
                {"start": 18.0, "end": 24.0, "speaker": "2", "confidence": 0.96},
            ],
        }
        return AudicCall(
            status=200,
            request_id="demo-dia-002",
            duration_ms=115,
            headers={"X-Request-Id": "demo-dia-002"},
            body=json.dumps(dia_payload).encode(),
            json=dia_payload,
        )
    files = {"file": (filename, content, content_type)}
    return await _request(
        "POST",
        _url("/diarization/diarize"),
        files=files,
        data={"model": "audic-diar-1", "response_format": "json"},
    )


async def transcribe(
    filename: str,
    content: bytes,
    content_type: str,
    language: str | None,
    prompt: str | None,
) -> AudicCall:
    if not settings.audiclabs_api_key and settings.audiclabs_demo_fallback:
        hint_text = f" Focused on {prompt}." if prompt else ""
        text = (
            "Welcome everyone to Transcribe Hub by AudicLabs. "
            "In this session we demonstrate multi-speaker diarization, automated timestamps, "
            "noise reduction, and instant inline editing." + hint_text
        )
        stt_payload = {
            "text": text,
            "language": language or "en-IN",
            "segments": [
                {
                    "start": 0.0,
                    "end": 4.5,
                    "speaker": "Speaker 1 (Interviewer)",
                    "text": "Welcome everyone to Transcribe Hub by AudicLabs.",
                    "confidence": 0.97,
                },
                {
                    "start": 4.8,
                    "end": 11.2,
                    "speaker": "Speaker 2 (Guest)",
                    "text": "In this session we demonstrate multi-speaker diarization, automated timestamps,",
                    "confidence": 0.95,
                },
                {
                    "start": 11.5,
                    "end": 17.8,
                    "speaker": "Speaker 1 (Interviewer)",
                    "text": "noise reduction, and instant inline editing.",
                    "confidence": 0.98,
                },
                {
                    "start": 18.0,
                    "end": 24.0,
                    "speaker": "Speaker 2 (Guest)",
                    "text": hint_text.strip() or "All features are active and verified across the portal.",
                    "confidence": 0.96,
                },
            ],
        }
        return AudicCall(
            status=200,
            request_id="demo-stt-003",
            duration_ms=142,
            headers={"X-Request-Id": "demo-stt-003"},
            body=json.dumps(stt_payload).encode(),
            json=stt_payload,
        )
    files = {"file": (filename, content, content_type)}
    data: dict[str, str] = {"model": "audic-stt-1"}
    if language and language not in ("auto", "", "null"):
        data["language"] = language
    if prompt:
        data["prompt"] = prompt
    return await _request("POST", _url("/stt/transcriptions"), files=files, data=data)


def parse_transcript(payload: dict | None, text_fallback: str = "") -> dict:
    payload = payload or {}
    text = (
        payload.get("text")
        or payload.get("transcript")
        or payload.get("result")
        or text_fallback
    )
    if isinstance(text, dict):
        text = text.get("text") or json.dumps(text)
    segments = payload.get("segments") or payload.get("chunks") or []
    lang = payload.get("language") or payload.get("detected_language")
    return {"text": text or "", "segments": segments, "language": lang, "raw": payload}


def parse_diarization(payload: dict | None) -> tuple[dict, list]:
    payload = payload or {}
    speakers = payload.get("speakers") or {}
    segments = payload.get("segments") or payload.get("utterances") or []
    if isinstance(speakers, list):
        speakers = {str(s.get("id", i)): s.get("label") or f"Speaker {i+1}" for i, s in enumerate(speakers)}
    return speakers, segments


def merge_segments(text: str, dia_segments: list, speakers: dict) -> list:
    if dia_segments:
        out = []
        for i, seg in enumerate(dia_segments):
            speaker = str(seg.get("speaker") or seg.get("speaker_id") or f"S{i%2}")
            label = speakers.get(speaker, speaker if speaker.startswith("Speaker") else f"Speaker {speaker}")
            start = float(seg.get("start") or seg.get("start_time") or 0)
            end = float(seg.get("end") or seg.get("end_time") or start)
            chunk = seg.get("text") or ""
            out.append(
                {
                    "start": start,
                    "end": end,
                    "speaker": label,
                    "text": chunk,
                    "confidence": float(seg.get("confidence") or 0.88),
                }
            )
        if text and not any(s["text"] for s in out):
            words = text.split()
            n = max(len(out), 1)
            chunk_size = max(len(words) // n, 1)
            for i, seg in enumerate(out):
                seg["text"] = " ".join(words[i * chunk_size : (i + 1) * chunk_size])
            if words[n * chunk_size :]:
                out[-1]["text"] += " " + " ".join(words[n * chunk_size :])
        return out
    return [{"start": 0, "end": 0, "speaker": "Speaker 1", "text": text, "confidence": 0.9}]
