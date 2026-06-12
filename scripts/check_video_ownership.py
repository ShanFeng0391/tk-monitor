"""Check whether stored videos belong to the monitored creator."""
import sqlite3
import yt_dlp

DB = r"C:\Users\Administrator\Projects\tiktok-monitor\data\tiktok_monitor.db"
conn = sqlite3.connect(DB)
rows = conn.execute(
    """
    SELECT v.id, v.video_id, v.video_url, c.tiktok_username, c.tiktok_user_id
    FROM videos v
    JOIN monitored_creators c ON v.creator_id = c.id
    ORDER BY v.id
    LIMIT 15
    """
).fetchall()
conn.close()

ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True})
mismatch = 0
for vid, tiktok_id, url, creator, creator_uid in rows:
    try:
        info = ydl.extract_info(url, download=False)
        owner = str(info.get("uploader_id") or "")
        canonical = info.get("webpage_url") or url
        ok = not creator_uid or owner == creator_uid
        if not ok:
            mismatch += 1
        print(
            f"id={vid} creator=@{creator} owner=@{info.get('uploader')} "
            f"owner_id={owner} creator_id={creator_uid} match={ok}"
        )
        if canonical != url:
            print(f"  stored: {url}")
            print(f"  canon : {canonical}")
    except Exception as exc:
        print(f"id={vid} ERROR {exc}")

print(f"mismatch in sample: {mismatch}/{len(rows)}")
