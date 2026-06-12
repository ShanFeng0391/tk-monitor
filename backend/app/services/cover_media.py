"""路径 A：多封面/动图预览帧采集与去重。"""
import hashlib
import io
from typing import Optional

from PIL import Image

from app.config import get_settings
from app.models import Video
from app.services.scraper import scraper
from app.services.storage import load_cover_bytes

settings = get_settings()


def _image_fingerprint(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data)) as img:
            thumb = img.convert("RGB")
            thumb.thumbnail((64, 64))
            buffer = io.BytesIO()
            thumb.save(buffer, format="JPEG", quality=60)
            return hashlib.md5(buffer.getvalue()).hexdigest()
    except Exception:
        return hashlib.md5(data[:4096]).hexdigest()


def dedupe_image_bytes(images: list[bytes], *, max_total: int) -> list[bytes]:
    seen: set[str] = set()
    unique: list[bytes] = []
    for data in images:
        if not data:
            continue
        fp = _image_fingerprint(data)
        if fp in seen:
            continue
        seen.add(fp)
        unique.append(data)
        if len(unique) >= max_total:
            break
    return unique


def extract_animated_frames(data: bytes, *, max_frames: int = 4) -> list[bytes]:
    """从 dynamicCover 等动图/WebP 中均匀抽取若干帧。"""
    frames: list[bytes] = []
    try:
        with Image.open(io.BytesIO(data)) as img:
            total = getattr(img, "n_frames", 1) or 1
            if total <= 1:
                return []
            picks = max(1, min(max_frames, total))
            if picks == 1:
                indices = [0]
            else:
                step = max(1, (total - 1) // (picks - 1))
                indices = [min(i * step, total - 1) for i in range(picks)]
            for index in indices:
                img.seek(index)
                frame = img.convert("RGB")
                buffer = io.BytesIO()
                frame.save(buffer, format="JPEG", quality=85)
                frames.append(buffer.getvalue())
    except Exception:
        return []
    return frames


def expand_cover_bytes(data: bytes, *, max_animated_frames: int = 4) -> list[bytes]:
    """静态图返回原图；动图返回多帧。"""
    animated = extract_animated_frames(data, max_frames=max_animated_frames)
    return animated if animated else [data]


async def load_path_a_images(
    video: Video,
    primary_cover: Optional[bytes] = None,
) -> list[bytes]:
    """路径 A：主封面 + 视频页多封面 URL + 动图拆帧。"""
    images: list[bytes] = []
    max_total = max(2, settings.recognition_max_cover_variants)

    if not primary_cover:
        primary_cover = load_cover_bytes(
            video.video_id,
            video.cover_url,
            video.cover_local_path,
        )
    if primary_cover:
        images.extend(expand_cover_bytes(primary_cover, max_animated_frames=4))

    media = await scraper.fetch_video_media(video.video_url)
    for url in media.cover_urls:
        if video.cover_url and url.rstrip("/") == video.cover_url.rstrip("/"):
            continue
        data = await scraper.download_cover(url)
        if data:
            images.extend(expand_cover_bytes(data, max_animated_frames=4))

    if not images and video.cover_url and video.cover_url.startswith(("http://", "https://")):
        data = await scraper.download_cover(video.cover_url)
        if data:
            images.extend(expand_cover_bytes(data, max_animated_frames=4))

    return dedupe_image_bytes(images, max_total=max_total)
