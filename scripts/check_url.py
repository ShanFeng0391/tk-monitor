import sqlite3
conn = sqlite3.connect(r"C:\Users\Administrator\Projects\tiktok-monitor\data\tiktok_monitor.db")
rows = conn.execute(
    "SELECT video_id, video_url, title FROM videos WHERE title LIKE ? LIMIT 5",
    ("%Wait I love%",),
).fetchall()
for row in rows:
    print(row)
