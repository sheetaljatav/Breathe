"""
Where uploaded source files live between the HTTP upload and the Celery parse.

For the prototype we use a local directory under MEDIA_ROOT. Production would
use object storage (S3 with presigned upload URLs); the contract the parser
and task see is the same — `read_bytes(batch_id)` returns bytes.

Files are deleted after the batch reaches a terminal status (complete or
failed) — we don't need to keep the original bytes once SourceRecord rows
have captured the structured payload.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings


def _base() -> Path:
    root = Path(getattr(settings, "MEDIA_ROOT", "")) or Path(settings.BASE_DIR) / "media"
    p = root / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def storage_path(batch_id: int) -> Path:
    return _base() / f"batch-{batch_id}.bin"


def write_bytes(batch_id: int, data: bytes) -> None:
    storage_path(batch_id).write_bytes(data)


def read_bytes(batch_id: int) -> bytes:
    return storage_path(batch_id).read_bytes()


def delete(batch_id: int) -> None:
    p = storage_path(batch_id)
    if p.exists():
        p.unlink()
