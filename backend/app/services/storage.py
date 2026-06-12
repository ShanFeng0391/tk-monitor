import io
import os
from typing import Optional

from app.config import get_settings

settings = get_settings()


def save_cover_locally(video_id: str, data: bytes, base_dir: Optional[str] = None) -> str:
    base_dir = base_dir or settings.covers_dir
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, f"{video_id}.jpg")
    with open(path, "wb") as f:
        f.write(data)
    return path


def get_local_cover_url(video_id: str) -> str:
    return f"/static/covers/{video_id}.jpg"


def resolve_local_cover_path(video_id: str, cover_url: Optional[str] = None, cover_local_path: Optional[str] = None) -> Optional[str]:
    """Resolve a readable local cover file path from stored video fields."""
    candidates: list[str] = []
    if cover_local_path:
        candidates.append(cover_local_path)
    if cover_url:
        if cover_url.startswith("/static/covers/"):
            candidates.append(os.path.join(settings.covers_dir, os.path.basename(cover_url)))
        elif cover_url.startswith("http://") or cover_url.startswith("https://"):
            return None
        elif os.path.isfile(cover_url):
            candidates.append(cover_url)
    if video_id:
        candidates.append(os.path.join(settings.covers_dir, f"{video_id}.jpg"))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def load_cover_bytes(
    video_id: str,
    cover_url: Optional[str] = None,
    cover_local_path: Optional[str] = None,
) -> Optional[bytes]:
    path = resolve_local_cover_path(video_id, cover_url, cover_local_path)
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


class StorageService:
    """MinIO 存储（Docker 模式）。"""

    def __init__(self):
        from minio import Minio

        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self.bucket = settings.minio_bucket
        self._ensure_bucket()

    def _ensure_bucket(self):
        from minio.error import S3Error

        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except S3Error:
            pass

    def upload_cover(self, video_id: str, data: bytes, content_type: str = "image/jpeg") -> str:
        object_name = f"covers/{video_id}.jpg"
        self.client.put_object(
            self.bucket,
            object_name,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return object_name

    def get_cover_url(self, object_name: str) -> str:
        protocol = "https" if settings.minio_secure else "http"
        return f"{protocol}://{settings.minio_endpoint}/{self.bucket}/{object_name}"


_storage: Optional[StorageService] = None


def get_storage() -> StorageService:
    global _storage
    if _storage is None:
        _storage = StorageService()
    return _storage


def store_cover(video_id: str, data: bytes) -> tuple[str, Optional[str]]:
    """返回 (cover_url, cover_local_path)。"""
    if settings.local_mode:
        path = save_cover_locally(video_id, data)
        return get_local_cover_url(video_id), path
    try:
        storage = get_storage()
        obj_name = storage.upload_cover(video_id, data)
        return storage.get_cover_url(obj_name), None
    except Exception:
        path = save_cover_locally(video_id, data)
        return get_local_cover_url(video_id), path
