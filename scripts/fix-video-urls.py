"""修正已有视频的 TikTok 外链与真实作者用户名。"""
from __future__ import annotations

import sqlite3
import sys

import yt_dlp

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "tiktok_monitor.db"


def main() -> int:
    if not DB_PATH.exists():
        print(f"database not found: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT v.id, v.video_id, v.video_url, v.source_username, c.tiktok_user_id
        FROM videos v
        JOIN monitored_creators c ON v.creator_id = c.id
        ORDER BY v.id
        """
    ).fetchall()

    ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True})
    updated = 0
    mismatched = 0

    for row in rows:
        url = row["video_url"]
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as exc:
            print(f"[skip] id={row['id']} extract failed: {exc}")
            continue

        owner = str(info.get("uploader") or "").strip()
        owner_id = str(info.get("uploader_id") or "")
        canonical = (
            f"https://www.tiktok.com/@{owner}/video/{row['video_id']}"
            if owner
            else info.get("webpage_url") or url
        )

        creator_uid = str(row["tiktok_user_id"] or "")
        if creator_uid and owner_id and owner_id != creator_uid:
            mismatched += 1
            print(f"[warn] id={row['id']} owner=@{owner} differs from monitored creator")

        if owner and (row["source_username"] != owner or row["video_url"] != canonical):
            conn.execute(
                "UPDATE videos SET source_username = ?, video_url = ? WHERE id = ?",
                (owner, canonical, row["id"]),
            )
            updated += 1
            print(f"[fix] id={row['id']} -> {canonical}")

    conn.commit()
    conn.close()
    print(f"done: updated={updated}, mismatched={mismatched}, total={len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
