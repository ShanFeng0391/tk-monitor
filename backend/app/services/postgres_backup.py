"""PostgreSQL 逻辑备份并上传 OSS（混合 / 自建 PG 场景）。"""
from __future__ import annotations

import gzip
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from app.config import get_settings, PROJECT_ROOT

logger = logging.getLogger(__name__)
settings = get_settings()


def _local_backup_dir() -> Path:
    path = Path(settings.data_dir) / "backups" / "postgres"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parse_pg_url(database_url_sync: str) -> dict:
    parsed = urlparse(database_url_sync)
    if parsed.scheme not in ("postgresql", "postgres"):
        raise ValueError(f"unsupported database url scheme: {parsed.scheme}")
    dbname = (parsed.path or "/tiktok_monitor").lstrip("/") or "tiktok_monitor"
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "dbname": dbname,
        "query": parsed.query or "",
    }


def _upload_to_oss(local_path: Path, object_name: str) -> str:
    from minio import Minio

    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    bucket = settings.minio_bucket
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    client.fput_object(bucket, object_name, str(local_path))
    protocol = "https" if settings.minio_secure else "http"
    return f"{protocol}://{settings.minio_endpoint}/{bucket}/{object_name}"


def _rotate_local_backups(keep: int) -> int:
    backup_dir = _local_backup_dir()
    files = sorted(backup_dir.glob("tiktok_monitor-*.sql.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for path in files[keep:]:
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def _rotate_remote_backups(keep: int) -> int:
    from minio import Minio

    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    prefix = settings.postgres_backup_bucket_prefix.strip("/") + "/"
    objects = list(
        client.list_objects(settings.minio_bucket, prefix=prefix, recursive=True)
    )
    objects.sort(key=lambda obj: obj.last_modified or datetime.min, reverse=True)
    removed = 0
    for obj in objects[keep:]:
        client.remove_object(settings.minio_bucket, obj.object_name)
        removed += 1
    return removed


def run_postgres_backup() -> dict:
    if settings.local_mode:
        return {"skipped": True, "reason": "local_sqlite_mode"}

    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        return {"skipped": True, "reason": "pg_dump_not_found"}

    try:
        pg = _parse_pg_url(settings.database_url_sync)
    except ValueError as exc:
        return {"skipped": True, "reason": str(exc)}

    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup_dir = _local_backup_dir()
    plain_path = backup_dir / f"tiktok_monitor-{stamp}.sql"
    gzip_path = backup_dir / f"tiktok_monitor-{stamp}.sql.gz"

    env = os.environ.copy()
    if pg["password"]:
        env["PGPASSWORD"] = pg["password"]
    if "sslmode=require" in pg["query"].lower() or "ssl=require" in settings.database_url_sync.lower():
        env["PGSSLMODE"] = "require"

    cmd = [
        pg_dump,
        "-h",
        pg["host"],
        "-p",
        pg["port"],
        "-U",
        pg["user"],
        "-d",
        pg["dbname"],
        "--no-owner",
        "--no-privileges",
        "-F",
        "p",
        "-f",
        str(plain_path),
    ]

    try:
        subprocess.run(cmd, check=True, env=env, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        logger.error("pg_dump failed: %s", exc.stderr or exc.stdout)
        plain_path.unlink(missing_ok=True)
        return {"ok": False, "error": (exc.stderr or exc.stdout or "pg_dump failed")[:500]}

    with plain_path.open("rb") as src, gzip.open(gzip_path, "wb") as dst:
        dst.writelines(src)
    plain_path.unlink(missing_ok=True)

    object_name = f"{settings.postgres_backup_bucket_prefix.strip('/')}/tiktok_monitor-{stamp}.sql.gz"
    remote_url = None
    upload_error = None
    try:
        remote_url = _upload_to_oss(gzip_path, object_name)
    except Exception as exc:
        upload_error = str(exc)
        logger.warning("postgres backup upload failed: %s", exc)

    local_removed = _rotate_local_backups(settings.postgres_backup_keep_local)
    remote_removed = 0
    if remote_url:
        try:
            remote_removed = _rotate_remote_backups(settings.postgres_backup_keep_remote)
        except Exception as exc:
            logger.warning("postgres backup remote rotation failed: %s", exc)

    return {
        "ok": True,
        "local_file": str(gzip_path),
        "remote_url": remote_url,
        "upload_error": upload_error,
        "local_removed": local_removed,
        "remote_removed": remote_removed,
        "project_root": str(PROJECT_ROOT),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run_postgres_backup()
    if result.get("skipped"):
        print(f"skipped: {result.get('reason')}")
        return 0 if result.get("reason") == "local_sqlite_mode" else 1
    if not result.get("ok"):
        print(f"failed: {result.get('error')}")
        return 1
    print(f"backup ok: {result.get('local_file')}")
    if result.get("remote_url"):
        print(f"uploaded: {result['remote_url']}")
    elif result.get("upload_error"):
        print(f"upload failed: {result['upload_error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
