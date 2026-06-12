import asyncio
import httpx


async def main():
    headers = {
        "User-Agent": "tiktok-monitor/1.0 (https://github.com/local/tiktok-monitor)",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as c:
        r = await c.post(
            "https://api.bgm.tv/v0/search/subjects",
            headers=headers,
            json={"keyword": "咒术回战", "filter": {"type": [2]}},
            timeout=20,
        )
        print("search", r.status_code)
        items = r.json().get("data") or []
        if not items:
            print("no results")
            return
        sub = items[0]
        print("first", sub.get("id"), sub.get("name"), sub.get("name_cn"))
        sid = sub["id"]
        r2 = await c.get(f"https://api.bgm.tv/v0/subjects/{sid}", headers=headers, timeout=20)
        d2 = r2.json()
        print("images", d2.get("images"))
        print("tags", (d2.get("tags") or [])[:3])


if __name__ == "__main__":
    asyncio.run(main())
