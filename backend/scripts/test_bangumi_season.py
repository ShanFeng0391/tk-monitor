import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

HEADERS = {
    "User-Agent": "tiktok-monitor/1.0 (https://github.com/local/tiktok-monitor)",
    "Content-Type": "application/json",
}


async def search(keyword: str):
    async with httpx.AsyncClient() as c:
        r = await c.post(
            "https://api.bgm.tv/v0/search/subjects",
            headers=HEADERS,
            json={"keyword": keyword, "filter": {"type": [2]}},
            timeout=20,
        )
        items = r.json().get("data") or []
        print(f"--- {keyword} ({len(items)}) ---")
        for item in items[:5]:
            print(item.get("id"), item.get("name_cn") or item.get("name"))


async def main():
    for kw in [
        "恶搞之家第22季",
        "恶搞之家 第22季",
        "恶搞之家",
        "Family Guy Season 22",
        "Family Guy 第22季",
    ]:
        await search(kw)


if __name__ == "__main__":
    asyncio.run(main())
