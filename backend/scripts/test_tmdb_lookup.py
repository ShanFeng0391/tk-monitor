"""Quick TMDB lookup smoke test (loads TMDB_API_KEY from ../.env)."""
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

from app.services.tmdb import lookup_movie_metadata  # noqa: E402


async def main() -> None:
    titles = ["水仙花开", "逃出克隆岛", "破墓", "地球停转之日", "绝密档案", "缩小人生"]
    for name in titles:
        result, _ = await lookup_movie_metadata(name, prefer_chinese_name=name)
        print(
            json.dumps(
                {
                    "query": name,
                    "ok": bool(result),
                    "english_name": (result or {}).get("english_name"),
                    "release_year": (result or {}).get("release_year"),
                    "tmdb_id": (result or {}).get("tmdb_id"),
                    "drama_type": (result or {}).get("drama_type"),
                },
                ensure_ascii=True,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
