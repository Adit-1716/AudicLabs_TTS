from io import BytesIO
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import settings

_client = None
LOCAL_ROOT = Path(__file__).resolve().parents[3] / "data" / "uploads"


def s3():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=0.5,
                read_timeout=0.5,
                retries={"max_attempts": 0},
            ),
        )
    return _client


def ensure_bucket() -> None:
    try:
        client = s3()
        try:
            client.head_bucket(Bucket=settings.s3_bucket)
        except ClientError:
            client.create_bucket(Bucket=settings.s3_bucket)
    except Exception:
        LOCAL_ROOT.mkdir(parents=True, exist_ok=True)


def _local_path(key: str) -> Path:
    path = LOCAL_ROOT / key
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def put_bytes(key: str, data: bytes, content_type: str) -> None:
    try:
        ensure_bucket()
        s3().upload_fileobj(BytesIO(data), settings.s3_bucket, key, ExtraArgs={"ContentType": content_type})
    except Exception:
        _local_path(key).write_bytes(data)


def get_bytes(key: str) -> bytes:
    try:
        buf = BytesIO()
        s3().download_fileobj(settings.s3_bucket, key, buf)
        return buf.getvalue()
    except Exception:
        return _local_path(key).read_bytes()


def presign(key: str, expires: int = 3600) -> str:
    try:
        return s3().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": key},
            ExpiresIn=expires,
        )
    except Exception:
        return f"/api/files/{key}"
