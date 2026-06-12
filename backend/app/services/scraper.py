import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, List, Optional

import httpx
from fake_useragent import UserAgent

from app.config import get_settings
from app.services.proxy_pool import get_active_scrape_proxy
from app.services.tiktok_url import build_video_url, normalize_username

settings = get_settings()
ua = UserAgent()
logger = logging.getLogger(__name__)


@dataclass
class TikTokVideoData:
    video_id: str
    title: str
    description: str
    video_url: str
    cover_url: str
    published_at: datetime
    duration: int
    view_count: int
    like_count: int
    share_count: int
    comment_count: int
    hashtags: str = ""
    source_username: str = ""
    uploader_id: str = ""


@dataclass
class TikTokCreatorData:
    username: str
    user_id: str
    display_name: str
    follower_count: int = 0
    exists: bool = True


@dataclass
class CreatorProfileUpdate:
    follower_count: int = 0
    display_name: str = ""
    user_id: str = ""


@dataclass
class VideoMediaInfo:
    cover_urls: list[str]
    play_url: str = ""
    duration: int = 0


class TikTokScraper:
    """TikTok 数据采集引擎，支持 httpx 主引擎 + Playwright 备用。"""

    BASE_URL = "https://www.tiktok.com"

    @property
    def proxy(self) -> str | None:
        return get_active_scrape_proxy()

    def _playwright_proxy(self) -> dict | None:
        if not self.proxy:
            return None
        return {"server": self.proxy}

    def _headers(self) -> dict:
        return {
            "User-Agent": ua.random,
            "Accept": "text/html,application/xhtml+xml,application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": self.BASE_URL,
        }

    async def _delay(self):
        delay = random.uniform(settings.scrape_request_delay_min, settings.scrape_request_delay_max)
        await asyncio.sleep(delay)

    async def verify_creator(self, username: str, *, fast: bool = False) -> TikTokCreatorData:
        username = username.lstrip("@").strip()
        try:
            async with httpx.AsyncClient(
                headers=self._headers(),
                proxy=self.proxy,
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                if fast:
                    await asyncio.sleep(random.uniform(0.2, 0.6))
                else:
                    await self._delay()
                resp = await client.get(f"{self.BASE_URL}/@{username}")
                if resp.status_code == 404:
                    return TikTokCreatorData(username=username, user_id="", display_name="", exists=False)
                parsed = self._parse_creator_from_html(resp.text, username)
                if parsed:
                    return parsed
        except Exception:
            pass
        if not settings.scrape_allow_mock:
            return TikTokCreatorData(username=username, user_id="", display_name="", exists=False)
        return TikTokCreatorData(
            username=username,
            user_id=f"mock_{username}",
            display_name=username,
            follower_count=128_000,
            exists=True,
        )

    def _parse_follower_count_from_html(self, html: str) -> int:
        data = self._extract_universal_data(html)
        if data:
            user_info = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {}).get("userInfo", {})
            stats = user_info.get("stats") or {}
            raw = stats.get("followerCount") or stats.get("follower_count")
            if raw is not None:
                try:
                    return max(0, int(raw))
                except (TypeError, ValueError):
                    pass
        match = re.search(r'"followerCount"\s*:\s*(\d+)', html)
        if match:
            try:
                return max(0, int(match.group(1)))
            except ValueError:
                pass
        return 0

    def _extract_tiktok_user_id(self, html: str) -> str:
        data = self._extract_universal_data(html)
        if data:
            user = (
                data.get("__DEFAULT_SCOPE__", {})
                .get("webapp.user-detail", {})
                .get("userInfo", {})
                .get("user", {})
            )
            uid = user.get("id")
            if uid:
                return str(uid)
        match = re.search(r'"id":"(\d{10,})"', html)
        return match.group(1) if match else ""

    def _parse_creator_profile_from_html(self, html: str) -> CreatorProfileUpdate:
        follower_count = self._parse_follower_count_from_html(html)
        display_name = ""
        name_match = re.search(r'"nickname":"([^"]+)"', html)
        if name_match:
            display_name = name_match.group(1)
        return CreatorProfileUpdate(
            follower_count=follower_count,
            display_name=display_name,
            user_id=self._extract_tiktok_user_id(html),
        )

    def _parse_creator_from_html(self, html: str, username: str) -> Optional[TikTokCreatorData]:
        data = self._extract_universal_data(html)
        if data:
            user_info = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {}).get("userInfo", {})
            user = user_info.get("user") or {}
            if user.get("uniqueId"):
                stats = user_info.get("stats") or {}
                try:
                    followers = int(stats.get("followerCount") or stats.get("follower_count") or 0)
                except (TypeError, ValueError):
                    followers = 0
                return TikTokCreatorData(
                    username=user.get("uniqueId") or username,
                    user_id=str(user.get("id") or ""),
                    display_name=user.get("nickname") or username,
                    follower_count=max(0, followers),
                    exists=True,
                )

        match = re.search(r'"uniqueId":"([^"]+)"', html)
        if not match:
            return None
        name_match = re.search(r'"nickname":"([^"]+)"', html)
        uid_match = re.search(r'"id":"(\d+)"', html)
        profile = self._parse_creator_profile_from_html(html)
        return TikTokCreatorData(
            username=match.group(1),
            user_id=uid_match.group(1) if uid_match else username,
            display_name=profile.display_name or (name_match.group(1) if name_match else username),
            follower_count=profile.follower_count,
            exists=True,
        )

    async def fetch_creator_videos(
        self, username: str, window_hours: int = 30
    ) -> tuple[List[TikTokVideoData], CreatorProfileUpdate]:
        username = username.lstrip("@").strip()
        videos: List[TikTokVideoData] = []
        profile = CreatorProfileUpdate()
        profile_html = ""
        tiktok_user_id = ""

        try:
            async with httpx.AsyncClient(
                headers=self._headers(),
                proxy=self.proxy,
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                await self._delay()
                resp = await client.get(f"{self.BASE_URL}/@{username}")
                if resp.status_code == 200:
                    profile_html = resp.text
                    profile = self._parse_creator_profile_from_html(profile_html)
                    tiktok_user_id = profile.user_id
                    videos = self._parse_videos_from_html(profile_html, username)
                    if not videos:
                        videos = await self._fetch_videos_via_api(
                            client, profile_html, username, window_hours
                        )
        except Exception as exc:
            logger.warning("httpx fetch failed for @%s: %s", username, exc)

        if not videos or window_hours <= 0:
            try:
                ytdlp_videos = await self._fetch_videos_via_ytdlp(
                    username,
                    window_hours,
                    tiktok_user_id=tiktok_user_id,
                )
                if ytdlp_videos and (not videos or len(ytdlp_videos) >= len(videos)):
                    videos = ytdlp_videos
            except Exception as exc:
                logger.warning("yt-dlp fallback failed for @%s: %s", username, exc)

        if not videos or window_hours <= 0:
            for attempt in range(3):
                try:
                    pw_videos = await self._fetch_videos_via_playwright(username, window_hours)
                except Exception:
                    pw_videos = []
                if pw_videos:
                    if videos:
                        videos = self._merge_videos(videos, pw_videos)
                    else:
                        videos = pw_videos
                if window_hours <= 0 and pw_videos:
                    if not videos or len(pw_videos) > len(videos):
                        videos = self._merge_videos(videos, pw_videos) if videos else pw_videos
                    break
                if videos and window_hours > 0:
                    break
                if attempt < 2:
                    await asyncio.sleep(2 + attempt)

        if not videos:
            if settings.scrape_allow_mock:
                videos = self._generate_mock_videos(username, window_hours)
                if not profile.follower_count:
                    profile = CreatorProfileUpdate(follower_count=128_000, display_name=username)
            else:
                return [], profile

        return self._apply_time_filter(videos, window_hours), profile

    def _apply_time_filter(self, videos: List[TikTokVideoData], window_hours: int) -> List[TikTokVideoData]:
        if window_hours <= 0:
            return videos
        cutoff = datetime.utcnow() - timedelta(hours=window_hours)
        return [v for v in videos if v.published_at >= cutoff]

    def _merge_videos(
        self, primary: List[TikTokVideoData], secondary: List[TikTokVideoData]
    ) -> List[TikTokVideoData]:
        merged = {video.video_id: video for video in primary if video.video_id}
        for video in secondary:
            if video.video_id and video.video_id not in merged:
                merged[video.video_id] = video
        return list(merged.values())

    def _items_to_videos(
        self,
        items: list[dict[str, Any]],
        username: str,
        window_hours: int,
    ) -> List[TikTokVideoData]:
        unlimited = window_hours <= 0
        cutoff = datetime.utcnow() - timedelta(hours=window_hours) if not unlimited else None
        collected: List[TikTokVideoData] = []
        seen_ids: set[str] = set()
        for item in items:
            published = self._parse_create_time(item)
            if not unlimited and cutoff and published < cutoff:
                continue
            video = self._item_to_video_data(item, username)
            if not video.video_id or video.video_id in seen_ids:
                continue
            seen_ids.add(video.video_id)
            collected.append(video)
        return collected

    def _extract_universal_data(self, html: str) -> Optional[dict[str, Any]]:
        match = re.search(
            r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>',
            html,
        )
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    def _parse_create_time(self, item: dict[str, Any]) -> datetime:
        raw = item.get("createTime") or item.get("create_time")
        if raw is None:
            return datetime.utcnow()
        try:
            return datetime.utcfromtimestamp(int(raw))
        except (TypeError, ValueError):
            return datetime.utcnow()

    def _normalize_media_url(self, value: Any) -> str:
        if isinstance(value, str) and value:
            return value.replace("\\u002F", "/")
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return first.replace("\\u002F", "/")
        return ""

    def _pick_cover_url(self, item: dict[str, Any]) -> str:
        urls = self._collect_cover_urls(item)
        return urls[0] if urls else ""

    def _collect_cover_urls(self, item: dict[str, Any]) -> list[str]:
        video = item.get("video") or {}
        urls: list[str] = []
        seen: set[str] = set()
        for key in ("cover", "originCover", "dynamicCover", "zoomCover"):
            url = self._normalize_media_url(video.get(key))
            if url and url not in seen:
                seen.add(url)
                urls.append(url)
        return urls

    def _pick_play_url(self, item: dict[str, Any]) -> str:
        video = item.get("video") or {}
        for key in ("playAddr", "downloadAddr", "playApi"):
            url = self._normalize_media_url(video.get(key))
            if url:
                return url
        bitrate_info = video.get("bitrateInfo") or []
        if isinstance(bitrate_info, list):
            for entry in bitrate_info:
                if not isinstance(entry, dict):
                    continue
                play_addr = entry.get("PlayAddr") or entry.get("playAddr")
                url = self._normalize_media_url(
                    play_addr.get("UrlList", [""])[0] if isinstance(play_addr, dict) else play_addr
                )
                if url:
                    return url
        return ""

    def _extract_item_from_universal(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        scope = data.get("__DEFAULT_SCOPE__", {})
        for path in (
            ("webapp.video-detail", "itemInfo", "itemStruct"),
            ("webapp.reflow.video.detail", "itemInfo", "itemStruct"),
        ):
            node = scope.get(path[0], {})
            for key in path[1:]:
                node = node.get(key, {}) if isinstance(node, dict) else {}
            if isinstance(node, dict) and node.get("id"):
                return node
        return None

    async def fetch_video_media(self, video_url: str) -> VideoMediaInfo:
        """拉取单条视频页的封面 URL 列表与播放地址（供识别路径 A/B 使用）。"""
        try:
            async with httpx.AsyncClient(
                headers=self._headers(),
                proxy=self.proxy,
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                await self._delay()
                resp = await client.get(video_url)
                if resp.status_code != 200:
                    return VideoMediaInfo(cover_urls=[])
                data = self._extract_universal_data(resp.text)
                if not data:
                    return VideoMediaInfo(cover_urls=[])
                item = self._extract_item_from_universal(data)
                if not item:
                    return VideoMediaInfo(cover_urls=[])
                video_meta = item.get("video") or {}
                duration = int(video_meta.get("duration") or item.get("duration") or 0)
                return VideoMediaInfo(
                    cover_urls=self._collect_cover_urls(item),
                    play_url=self._pick_play_url(item),
                    duration=duration,
                )
        except Exception:
            return VideoMediaInfo(cover_urls=[])

    def _resolve_stream_url_ytdlp_sync(self, video_url: str) -> str:
        try:
            import yt_dlp
        except ImportError:
            return ""

        ydl_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "format": "best[ext=mp4]/best",
        }
        if self.proxy:
            ydl_opts["proxy"] = self.proxy
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
        if not info:
            return ""
        url = info.get("url") or ""
        if url:
            return url
        formats = info.get("formats") or []
        for fmt in reversed(formats):
            if fmt.get("vcodec") != "none" and fmt.get("url"):
                return str(fmt["url"])
        return ""

    async def resolve_video_stream_url(self, video_url: str) -> str:
        media = await self.fetch_video_media(video_url)
        if media.play_url:
            return media.play_url
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._resolve_stream_url_ytdlp_sync, video_url)
        except Exception:
            return ""

    def _item_to_video_data(self, item: dict[str, Any], username: str) -> TikTokVideoData:
        stats = item.get("stats") or item.get("statsV2") or {}
        vid = str(item.get("id") or item.get("aweme_id") or "")
        desc = (item.get("desc") or item.get("title") or "").replace("\\u002F", "/")
        video_meta = item.get("video") or {}
        duration = int(video_meta.get("duration") or item.get("duration") or 0)
        author = item.get("author") or {}
        source_username = normalize_username(
            author.get("uniqueId") or author.get("unique_id") or username
        )
        uploader_id = str(author.get("id") or author.get("uid") or "")
        return TikTokVideoData(
            video_id=vid,
            title=desc[:100] if desc else f"Video {vid}",
            description=desc,
            video_url=build_video_url(source_username, vid),
            cover_url=self._pick_cover_url(item),
            published_at=self._parse_create_time(item),
            duration=duration,
            view_count=int(stats.get("playCount") or stats.get("play_count") or 0),
            like_count=int(stats.get("diggCount") or stats.get("digg_count") or 0),
            share_count=int(stats.get("shareCount") or stats.get("share_count") or 0),
            comment_count=int(stats.get("commentCount") or stats.get("comment_count") or 0),
            hashtags=" ".join(re.findall(r"#\w+", desc)),
            source_username=source_username,
            uploader_id=uploader_id,
        )

    async def _fetch_videos_via_api(
        self,
        client: httpx.AsyncClient,
        html: str,
        username: str,
        window_hours: int,
    ) -> List[TikTokVideoData]:
        data = self._extract_universal_data(html)
        if not data:
            return []

        user_detail = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {})
        user_info = user_detail.get("userInfo", {}).get("user", {})
        sec_uid = user_info.get("secUid")
        if not sec_uid:
            return []

        unlimited = window_hours <= 0
        cutoff = datetime.utcnow() - timedelta(hours=window_hours) if not unlimited else None
        collected: List[TikTokVideoData] = []
        cursor = 0
        has_more = True
        seen_ids: set[str] = set()
        max_items = 2000 if unlimited else 500

        while has_more and len(collected) < max_items:
            await self._delay()
            resp = await client.get(
                f"{self.BASE_URL}/api/post/item_list/",
                params={
                    "aid": "1988",
                    "app_name": "tiktok_web",
                    "device_platform": "web_pc",
                    "secUid": sec_uid,
                    "count": 30,
                    "cursor": cursor,
                    "coverFormat": 2,
                },
                headers={**self._headers(), "Referer": f"{self.BASE_URL}/@{username}"},
            )
            if resp.status_code != 200:
                break
            try:
                payload = resp.json()
            except json.JSONDecodeError:
                break

            items = payload.get("itemList") or payload.get("items") or []
            if not items:
                break

            reached_cutoff = False
            for item in items:
                published = self._parse_create_time(item)
                if not unlimited and cutoff and published < cutoff:
                    reached_cutoff = True
                    continue
                video = self._item_to_video_data(item, username)
                if not video.video_id or video.video_id in seen_ids:
                    continue
                seen_ids.add(video.video_id)
                collected.append(video)

            if (not unlimited and reached_cutoff) or not payload.get("hasMore"):
                has_more = False
            else:
                next_cursor = payload.get("cursor", 0)
                if next_cursor == cursor:
                    has_more = False
                cursor = next_cursor

        return collected

    def _fetch_videos_via_ytdlp_sync(
        self,
        username: str,
        window_hours: int,
        *,
        tiktok_user_id: str = "",
    ) -> List[TikTokVideoData]:
        import yt_dlp

        profile = username.lstrip("@").strip()
        candidate_urls = [f"{self.BASE_URL}/@{profile}"]
        if tiktok_user_id:
            candidate_urls.append(f"tiktokuser:{tiktok_user_id}")

        ydl_opts: dict[str, Any] = {
            "extract_flat": "in_playlist",
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        if self.proxy:
            ydl_opts["proxy"] = self.proxy

        info = None
        last_error: Exception | None = None
        for url in candidate_urls:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                if (info or {}).get("entries"):
                    break
            except Exception as exc:
                last_error = exc
                info = None

        if not info or not (info.get("entries") or []):
            if last_error:
                logger.warning("yt-dlp could not list videos for @%s: %s", profile, last_error)
            return []

        entries = (info or {}).get("entries") or []
        videos: List[TikTokVideoData] = []
        for entry in entries:
            if not entry:
                continue
            vid = str(entry.get("id") or "")
            if not vid:
                continue
            title = (entry.get("title") or entry.get("description") or "").strip()
            desc = (entry.get("description") or title or "").strip()
            ts = entry.get("timestamp") or entry.get("release_timestamp")
            published = datetime.utcfromtimestamp(int(ts)) if ts else datetime.utcnow()
            thumb = entry.get("thumbnail") or ""
            if not thumb:
                thumbs = entry.get("thumbnails") or []
                if thumbs:
                    thumb = thumbs[0].get("url") or ""
            source_username = normalize_username(entry.get("uploader") or profile)
            uploader_id = str(entry.get("uploader_id") or "")
            video_url = (entry.get("url") or entry.get("webpage_url") or "").strip()
            if not video_url:
                video_url = build_video_url(source_username, vid)
            videos.append(
                TikTokVideoData(
                    video_id=vid,
                    title=title[:100] if title else f"Video {vid}",
                    description=desc,
                    video_url=video_url,
                    cover_url=thumb,
                    published_at=published,
                    duration=int(entry.get("duration") or 0),
                    view_count=int(entry.get("view_count") or 0),
                    like_count=int(entry.get("like_count") or 0),
                    share_count=int(entry.get("repost_count") or entry.get("share_count") or 0),
                    comment_count=int(entry.get("comment_count") or 0),
                    hashtags=" ".join(re.findall(r"#\w+", desc)),
                    source_username=source_username,
                    uploader_id=uploader_id,
                )
            )
        return videos

    async def _fetch_videos_via_ytdlp(
        self,
        username: str,
        window_hours: int,
        *,
        tiktok_user_id: str = "",
    ) -> List[TikTokVideoData]:
        loop = asyncio.get_running_loop()
        videos = await loop.run_in_executor(
            None,
            lambda: self._fetch_videos_via_ytdlp_sync(
                username,
                window_hours,
                tiktok_user_id=tiktok_user_id,
            ),
        )
        return self._apply_time_filter(videos, window_hours)

    async def _fetch_videos_via_playwright(
        self, username: str, window_hours: int
    ) -> List[TikTokVideoData]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return []

        unlimited = window_hours <= 0
        scroll_items: list[dict[str, Any]] = []

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context_kwargs: dict[str, Any] = {
                "user_agent": ua.random,
                "locale": "en-US",
            }
            pw_proxy = self._playwright_proxy()
            if pw_proxy:
                context_kwargs["proxy"] = pw_proxy
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            async def capture_response(response):
                url = response.url
                if "item_list" not in url or response.status != 200:
                    return
                try:
                    payload = await response.json()
                except Exception:
                    return
                items = payload.get("itemList") or payload.get("items") or []
                if items:
                    scroll_items.extend(items)

            page.on("response", capture_response)
            profile_url = f"{self.BASE_URL}/@{username}"
            expected_count = 0
            try:
                await page.goto(profile_url, wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(5000)
                meta = await page.evaluate(
                    """() => {
                        const el = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                        if (!el) return null;
                        const data = JSON.parse(el.textContent);
                        const userInfo = data['__DEFAULT_SCOPE__']['webapp.user-detail']['userInfo'] || {};
                        const user = userInfo.user || {};
                        const stats = userInfo.stats || {};
                        return {
                            secUid: user.secUid || '',
                            videoCount: stats.videoCount || user.videoCount || 0,
                        };
                    }"""
                )
                if meta:
                    expected_count = int(meta.get("videoCount") or 0)

                target_count = expected_count if unlimited and expected_count else 0
                max_rounds = 200 if unlimited else min(30, max(8, window_hours // 72))
                if unlimited and target_count:
                    max_rounds = max(max_rounds, target_count * 2)

                stagnant_rounds = 0
                prev_unique = 0
                for round_idx in range(max_rounds):
                    unique_ids = {
                        str(item.get("id") or item.get("aweme_id") or "")
                        for item in scroll_items
                        if item.get("id") or item.get("aweme_id")
                    }
                    if target_count and len(unique_ids) >= target_count:
                        break

                    await page.mouse.wheel(0, 4000)
                    if round_idx % 3 == 2:
                        await page.keyboard.press("End")
                    await page.wait_for_timeout(1600)

                    unique_ids = {
                        str(item.get("id") or item.get("aweme_id") or "")
                        for item in scroll_items
                        if item.get("id") or item.get("aweme_id")
                    }
                    if len(unique_ids) == prev_unique:
                        stagnant_rounds += 1
                        stop_after = 15 if target_count else 8
                        if stagnant_rounds >= stop_after:
                            break
                    else:
                        stagnant_rounds = 0
                    prev_unique = len(unique_ids)
            except Exception:
                pass
            finally:
                await browser.close()

        return self._items_to_videos(scroll_items, username, window_hours)

    def _parse_videos_from_html(self, html: str, username: str) -> List[TikTokVideoData]:
        videos = []
        pattern = re.compile(
            r'"id":"(\d+)".*?"desc":"([^"]*)".*?"playCount":(\d+).*?"diggCount":(\d+).*?"shareCount":(\d+).*?"commentCount":(\d+).*?"duration":(\d+).*?"cover":"([^"]+)"',
            re.DOTALL,
        )
        for i, match in enumerate(pattern.finditer(html)):
            vid = match.group(1)
            desc = match.group(2).replace("\\u002F", "/")
            videos.append(
                TikTokVideoData(
                    video_id=vid,
                    title=desc[:100] if desc else f"Video {vid}",
                    description=desc,
                    video_url=build_video_url(username, vid),
                    cover_url=match.group(8).replace("\\u002F", "/"),
                    published_at=datetime.utcnow() - timedelta(hours=i * 2),
                    duration=int(match.group(7)),
                    view_count=int(match.group(3)),
                    like_count=int(match.group(4)),
                    share_count=int(match.group(5)),
                    comment_count=int(match.group(6)),
                    hashtags=" ".join(re.findall(r"#\w+", desc)),
                    source_username=normalize_username(username),
                )
            )
        return videos

    def _generate_mock_videos(self, username: str, window_hours: int) -> List[TikTokVideoData]:
        """开发/演示模式：生成模拟数据以便系统可运行验收。"""
        import hashlib

        videos = []
        base_hash = int(hashlib.md5(username.encode()).hexdigest()[:8], 16)
        count = min(60, max(5, window_hours // 48)) if window_hours > 0 else 60
        step_hours = max(6, window_hours // max(count, 1)) if window_hours > 0 else 24

        drama_titles = [
            ("庆余年2定档预告", "范闲归来，再掀风云！", "#庆余年 #张若昀 #电视剧"),
            ("狂飙高燃片段", "安欣与高启强的对决", "#狂飙 #张译 #电视剧"),
            ("繁花黄河路往事", "宝总传奇继续", "#繁花 #胡歌 #电视剧"),
            ("奥本海默核爆瞬间", "历史时刻重现", "#奥本海默 #电影"),
            ("庆余年范闲经典台词", "我要这天下", "#庆余年 #范闲"),
        ]

        for i in range(count):
            idx = (base_hash + i) % len(drama_titles)
            title, desc, tags = drama_titles[idx]
            vid = f"{base_hash}{i:04d}"
            multiplier = (base_hash % 50 + 1) * (i + 1)
            views = 50000 + multiplier * 1000 + i * 20000
            likes = views // 10 + multiplier * 50

            videos.append(
                TikTokVideoData(
                    video_id=vid,
                    title=title,
                    description=f"{desc} {tags}",
                    video_url=build_video_url(username, vid),
                    cover_url=f"https://picsum.photos/seed/{vid}/720/1280",
                    published_at=datetime.utcnow() - timedelta(hours=i * step_hours + (base_hash % 12)),
                    duration=30 + i * 5,
                    view_count=views,
                    like_count=likes,
                    share_count=likes // 20,
                    comment_count=likes // 15,
                    hashtags=tags,
                    source_username=normalize_username(username),
                )
            )
        return videos

    async def download_cover(self, cover_url: str) -> Optional[bytes]:
        try:
            async with httpx.AsyncClient(
                headers=self._headers(),
                proxy=self.proxy,
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                resp = await client.get(cover_url)
                if resp.status_code == 200:
                    return resp.content
        except Exception:
            pass
        return None


scraper = TikTokScraper()
