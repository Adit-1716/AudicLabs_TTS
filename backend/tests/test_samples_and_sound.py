from unittest.mock import patch
from app.services.audiclabs import AudicCall


def register(client, email="owner2@example.com", org="Studio Two"):
    r = client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "Studio Owner", "password": "SuperSecret123", "organization_name": org},
    )
    assert r.status_code == 200, r.text
    return r.json()


def auth_headers(token, org_id):
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}


def test_samples_listing_and_stream(client):
    r = client.get("/api/samples")
    assert r.status_code == 200
    samples = r.json()
    assert len(samples) >= 4
    first = samples[0]
    assert "stream_url" in first

    # Stream sample directly without auth
    stream = client.get(first["stream_url"], headers={"Range": "bytes=0-100"})
    assert stream.status_code in (200, 206)
    assert len(stream.content) > 0


def test_use_sample_and_play_stream(client):
    owner = register(client)
    org_id = owner["user"]["organization_id"]
    headers = auth_headers(owner["token"], org_id)

    # 1. Create project from sample dataset
    fake = AudicCall(
        status=200,
        request_id="req-test-sample",
        duration_ms=10,
        headers={"X-Request-Id": "req-test-sample"},
        body=b'{"text":"Good morning and welcome."}',
        json={
            "text": "Good morning and welcome to Transcribe Hub.",
            "language": "en-IN",
            "segments": [
                {"start": 0.0, "end": 2.5, "speaker": "Speaker 1", "text": "Good morning and welcome to Transcribe Hub.", "confidence": 0.98}
            ],
        },
    )

    with patch("app.services.pipeline.audiclabs.transcribe", new=_async_ok(fake)), patch(
        "app.services.pipeline.audiclabs.denoise", new=_async_ok(fake)
    ), patch("app.services.pipeline.audiclabs.diarize", new=_async_ok({"speakers": {}, "segments": []})):
        res = client.post(
            "/api/projects/from-sample",
            json={"title": "Podcast Test", "sample_id": "sample_interview.wav", "denoise": False, "diarize": False},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["ok"] is True
        assert data["media_id"] is not None
        assert data["transcript_id"] is not None

        # 2. Test media streaming with query param token (HTML5 audio simulation)
        media_id = data["media_id"]
        stream = client.get(f"/api/media/{media_id}/stream?token={owner['token']}", headers={"Range": "bytes=0-50"})
        assert stream.status_code == 206
        assert "Content-Range" in stream.headers
        assert len(stream.content) == 51

        # 3. Test transcript output has valid play_url
        t_res = client.get(f"/api/transcripts/{data['transcript_id']}", headers=headers)
        assert t_res.status_code == 200
        t_data = t_res.json()
        assert t_data["play_url"] == f"/api/media/{media_id}/stream"

        # 4. Test auto-score
        score_res = client.post(f"/api/transcripts/{data['transcript_id']}/auto-score", headers=headers)
        assert score_res.status_code == 200
        score_data = score_res.json()
        assert score_data["accuracy_pct"] >= 90
        assert score_data["completion_pct"] == 100.0

        # 5. Test auto-assign
        assign_res = client.post(f"/api/projects/{data['project_id']}/auto-assign", headers=headers)
        assert assign_res.status_code == 200

        # 6. Test lyrics formatting
        lyric_res = client.post(f"/api/transcripts/{data['transcript_id']}/lyrics/format", headers=headers)
        assert lyric_res.status_code == 200

        # 7. Test conversions to TXT, PDF, Word DOCX
        txt_res = client.get(f"/api/transcripts/{data['transcript_id']}/export.txt?mode=lyrics", headers=headers)
        assert txt_res.status_code == 200
        assert b"SONG LYRICS" in txt_res.content

        docx_res = client.get(f"/api/transcripts/{data['transcript_id']}/export.docx?mode=lyrics", headers=headers)
        assert docx_res.status_code == 200
        assert len(docx_res.content) > 100

        pdf_res = client.get(f"/api/transcripts/{data['transcript_id']}/export.pdf?mode=lyrics", headers=headers)
        assert pdf_res.status_code == 200
        assert pdf_res.content.startswith(b"%PDF")


def _async_ok(value):
    async def _inner(*args, **kwargs):
        if isinstance(value, dict):
            return AudicCall(200, "x", 1, {}, b"{}", value)
        return value

    return _inner
