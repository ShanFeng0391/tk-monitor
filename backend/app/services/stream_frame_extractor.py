"""路径 B：不落盘整片，流式读取视频 URL 并抽取多帧 JPEG。"""
import asyncio
import io
import logging
import shutil
import subprocess
from typing import Optional

from app.config import get_settings
from app.services.scraper import scraper

settings = get_settings()
logger = logging.getLogger(__name__)


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _probe_duration(url: str, timeout: int = 25) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                url,
            ],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            return 0.0
        text = (result.stdout or b"").decode("utf-8", errors="ignore").strip()
        return max(float(text), 0.0)
    except Exception:
        return 0.0


def _extract_single_frame(url: str, timestamp: float, timeout: int = 30) -> Optional[bytes]:
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{max(timestamp, 0.0):.3f}",
                "-i",
                url,
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "pipe:1",
            ],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        with io.BytesIO(result.stdout) as buffer:
            from PIL import Image

            img = Image.open(buffer)
            img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=85)
            return out.getvalue()
    except Exception:
        return None


def _extract_stream_frames_sync(
    stream_url: str,
    *,
    frame_count: int,
    duration_hint: int = 0,
) -> list[bytes]:
    if not _ffmpeg_available():
        logger.warning("ffmpeg/ffprobe not found, stream frame extraction skipped")
        return []

    duration = float(duration_hint) if duration_hint and duration_hint > 0 else _probe_duration(stream_url)
    if duration <= 0:
        duration = 30.0

    # 跳过片头片尾，在 15%～85% 区间均匀取帧
    start = duration * 0.15
    end = max(start + 0.5, duration * 0.85)
    count = max(3, min(frame_count, 6))
    if count == 1:
        positions = [(start + end) / 2]
    else:
        step = (end - start) / (count - 1)
        positions = [start + step * i for i in range(count)]

    frames: list[bytes] = []
    seen: set[str] = set()
    for pos in positions:
        data = _extract_single_frame(stream_url, pos)
        if not data:
            continue
        fp = data[:512]
        if fp in seen:
            continue
        seen.add(fp)
        frames.append(data)
    return frames


async def extract_stream_frames(
    video_url: str,
    *,
    duration_hint: int = 0,
    frame_count: Optional[int] = None,
) -> list[bytes]:
    if not settings.recognition_stream_frames_enabled:
        return []

    stream_url = await scraper.resolve_video_stream_url(video_url)
    if not stream_url:
        return []

    count = frame_count or settings.recognition_stream_frame_count
    return await asyncio.to_thread(
        _extract_stream_frames_sync,
        stream_url,
        frame_count=count,
        duration_hint=duration_hint,
    )
