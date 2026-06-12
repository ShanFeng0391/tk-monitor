"""Find videos whose TikTok owner differs from monitored creator."""
import sqlite3
import yt_dlp

DB = r"C:\Users\Administrator\Projects\tiktok-monitor\data\tiktok_monitor.db"
conn = sqlite3.connect(DB)
rows = conn.execute(
    """
    SELECT v.id, v.video_id, v.video_url, c.tiktok_user_id
    FROM videos v
    JOIN monitored_creators c ON v.creator_id = c.id
    WHERE c.tiktok_user_id IS NOT NULL AND c.tiktok_user_id != ''
    """
).fetchall()
conn.close()

ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True})
bad = []
for db_id, tiktok_id, url, creator_uid in rows:
    try:
        info = ydl.extract_info(url, download=False)
        owner = str(info.get("uploader_id") or "")
        if owner and owner != creator_uid:
            uploader = info.get("uploader") or ""
            canonical = f"https://www.tiktok.com/@{uploader}/video/{tiktok_id}" if uploader else info.get("webpage_url")
            bad.append((db_id, tiktok_id, url, owner, creator_uid, canonical))
    except Exception as exc:
        bad.append((db_id, tiktok_id, url, "ERROR", creator_uid, str(exc)))

print(f"checked {len(rows)}, mismatches {len(bad)}")
for item in bad[:20]:
    print(item)
