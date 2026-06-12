import sqlite3

conn = sqlite3.connect(r"C:\Users\Administrator\Projects\tiktok-monitor\data\tiktok_monitor.db")
cur = conn.cursor()
cur.execute("SELECT id, video_id, video_url, title FROM videos WHERE id=82")
print("video 82:", cur.fetchone())
cur.execute(
    "SELECT id, video_id, video_url FROM videos "
    "WHERE video_url NOT LIKE 'https://www.tiktok.com/@%/video/%'"
)
rows = cur.fetchall()
print("bad format count:", len(rows))
for row in rows[:10]:
    print(" bad:", row)
conn.close()
