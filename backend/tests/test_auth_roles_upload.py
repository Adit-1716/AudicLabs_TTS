from io import BytesIO
from unittest.mock import patch

from app.services.audiclabs import AudicCall


def register(client, email="owner@example.com", org="Studio One"):
    r = client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "Owner User", "password": "SuperSecret123", "organization_name": org},
    )
    assert r.status_code == 200, r.text
    return r.json()


def auth_headers(token, org_id):
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}


def test_register_login_and_me(client):
    data = register(client)
    token = data["token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "owner@example.com"
    assert body["role"] == "ORG_ADMIN"
    assert body["assessment_role"] == "Owner"

    login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "SuperSecret123"})
    assert login.status_code == 200


def test_roles_viewer_cannot_upload(client):
    owner = register(client)
    org_id = owner["user"]["organization_id"]
    headers = auth_headers(owner["token"], org_id)
    invite = client.post("/api/orgs/invites", json={"email": "reviewer@example.com", "role": "REVIEWER"}, headers=headers)
    assert invite.status_code == 200

    viewer = register(client, email="reviewer@example.com", org="Reviewer Co")
    # accept invite into owner's org
    acc = client.post(
        "/api/orgs/invites/accept",
        json={"token": invite.json()["token"]},
        headers={"Authorization": f"Bearer {viewer['token']}"},
    )
    assert acc.status_code == 200

    project = client.post("/api/projects", json={"title": "Lecture 1"}, headers=headers).json()
    files = {"files": ("talk.mp3", BytesIO(b"ID3fakeaudio"), "audio/mpeg")}
    denied = client.post(
        f"/api/projects/{project['id']}/uploads",
        files=files,
        headers=auth_headers(viewer["token"], org_id),
    )
    assert denied.status_code in (403, 422, 401, 400)


def test_upload_pipeline_mocked(client):
    owner = register(client)
    org_id = owner["user"]["organization_id"]
    headers = auth_headers(owner["token"], org_id)
    project = client.post("/api/projects", json={"title": "Interview", "denoise": False, "diarize": False}, headers=headers).json()

    fake = AudicCall(
        status=200,
        request_id="req-test-1",
        duration_ms=12,
        headers={"X-Request-Id": "req-test-1"},
        body=b'{"text":"hello world"}',
        json={"text": "hello world", "language": "en-IN"},
    )

    with patch("app.services.pipeline.audiclabs.transcribe", new=_async_ok(fake)), patch(
        "app.services.pipeline.audiclabs.denoise", new=_async_ok(fake)
    ), patch("app.services.pipeline.audiclabs.diarize", new=_async_ok({"speakers": {}, "segments": []})):
        files = {"files": ("talk.wav", BytesIO(b"RIFF....WAVEfmt "), "audio/wav")}
        data = {"language": "en-IN", "spelling_hints": "Kadepure", "denoise": "false", "diarize": "false"}
        r = client.post(f"/api/projects/{project['id']}/uploads", files=files, data=data, headers=headers)
        assert r.status_code == 200, r.text
        media = r.json()[0]
        assert media["original_name"] == "talk.wav"


def _async_ok(value):
    async def _inner(*args, **kwargs):
        if isinstance(value, dict):
            return AudicCall(200, "x", 1, {}, b"{}", value)
        return value

    return _inner
