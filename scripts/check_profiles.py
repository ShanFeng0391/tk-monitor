import httpx
import re

for handle in ["user171278194880", "salimovie"]:
    r = httpx.get(
        f"https://www.tiktok.com/@{handle}",
        follow_redirects=True,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    uid = re.search(r'"uniqueId":"([^"]+)"', r.text)
    nick = re.search(r'"nickname":"([^"]+)"', r.text)
    print(handle, "status", r.status_code, "final", r.url)
    print("  uniqueId", uid.group(1) if uid else None, "nickname", nick.group(1) if nick else None)
