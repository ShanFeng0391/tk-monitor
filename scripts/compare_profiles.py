import httpx
import re

def profile(handle):
    r = httpx.get(
        f"https://www.tiktok.com/@{handle}",
        follow_redirects=True,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    sec = re.search(r'"secUid":"([^"]+)"', r.text)
    uid = re.search(r'"id":"(\d+)"', r.text)
    unique = re.search(r'"uniqueId":"([^"]+)"', r.text)
    return {
        "handle": handle,
        "secUid": sec.group(1)[:40] + "..." if sec else None,
        "id": uid.group(1) if uid else None,
        "uniqueId": unique.group(1) if unique else None,
    }

for h in ["user171278194880", "salimovie"]:
    print(profile(h))
