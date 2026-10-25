import io
import pytest


def register(client, email="transcribe_tester@example.com", org="Audio Transcription Studio"):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Transcribe Tester",
            "password": "SuperSecret123!",
            "organization_name": org,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def auth_headers(token, org_id):
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}


def test_transcribe_audio_file_into_text(client):
    auth_data = register(client, email="transcribe_user1@acme.local")
    token = auth_data["token"]
    org_id = auth_data["user"]["organization_id"]
    headers = auth_headers(token, org_id)

    # 1. Provide an audio file (e.g., sample WAV audio)
    fake_wav_header = (
        b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
        b"\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    )
    audio_bytes = fake_wav_header + b"\x00" * 4000

    files = {"file": ("my_interview_recording.wav", io.BytesIO(audio_bytes), "audio/wav")}
    data = {
        "language": "en-US",
        "spelling_hints": "AudicLabs",
        "denoise": "true",
        "diarize": "true",
        "project_title": "My Interview Project",
    }

    # Call /api/transcripts/transcribe-file
    res = client.post("/api/transcripts/transcribe-file", files=files, data=data, headers=headers)
    assert res.status_code == 200, res.text
    payload = res.json()

    assert payload["ok"] is True
    assert payload["filename"] == "my_interview_recording.wav"
    assert len(payload["text"]) > 0
    assert "formatted_text" in payload
    assert len(payload["segments"]) > 0
    assert payload["word_count"] > 0
    assert payload["character_count"] > 0
    assert payload["transcript_id"] is not None
    assert payload["project_id"] is not None
    assert payload["media_id"] is not None
    assert "play_url" in payload
    assert "export_urls" in payload
    assert payload["export_urls"]["txt"].endswith("/export.txt")


def test_transcribe_to_plain_text(client):
    auth_data = register(client, email="transcribe_user2@acme.local")
    token = auth_data["token"]
    org_id = auth_data["user"]["organization_id"]
    headers = auth_headers(token, org_id)

    fake_audio = b"ID3" + b"\x00" * 2000
    files = {"file": ("podcast_episode.mp3", io.BytesIO(fake_audio), "audio/mpeg")}

    res = client.post("/api/transcripts/transcribe-to-text", files=files, headers=headers)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("text/plain")
    assert "X-Transcript-Id" in res.headers
    assert len(res.text) > 0


def test_transcribe_sample_audio_file(client):
    auth_data = register(client, email="transcribe_user3@acme.local")
    token = auth_data["token"]
    org_id = auth_data["user"]["organization_id"]
    headers = auth_headers(token, org_id)

    res = client.post(
        "/api/transcripts/transcribe-sample",
        json={"sample_id": "sample_interview.wav", "denoise": True, "diarize": True},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["ok"] is True
    assert "Transcribe Hub" in payload["text"]
    assert len(payload["segments"]) == 2
    assert payload["speakers"]["Speaker 1 (Interviewer)"] == "Speaker 1 (Interviewer)"


def test_unsupported_file_extension(client):
    auth_data = register(client, email="transcribe_user4@acme.local")
    token = auth_data["token"]
    org_id = auth_data["user"]["organization_id"]
    headers = auth_headers(token, org_id)

    files = {"file": ("malicious_script.exe", io.BytesIO(b"malicious"), "application/octet-stream")}
    res = client.post("/api/transcripts/transcribe-file", files=files, headers=headers)
    assert res.status_code == 422
    assert "not supported" in res.text
