import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "tiktok_monitor.db"
TEST_IDS = [30, 78, 126, 121, 138, 128]
EXPECTED = {
    30: "破墓",
    78: "地球停转之日",
    126: "绝密档案",
    121: "缩小人生",
    138: "水仙花开",
    128: "逃出克隆岛",
}


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("=== Recent recognitions (last 15) ===")
    cur.execute(
        """
        SELECT v.id, v.video_id AS platform_id, r.drama_name, r.drama_type,
               r.confidence, r.status, r.recognition_method, r.completed_at,
               length(r.api_response) AS resp_len
        FROM video_drama_recognition r
        JOIN videos v ON v.id = r.video_id
        ORDER BY r.completed_at DESC
        LIMIT 15
        """
    )
    for row in cur.fetchall():
        print(dict(row))

    print("\n=== Test case benchmark ===")
    hits = 0
    total = 0
    for vid in TEST_IDS:
        cur.execute(
            """
            SELECT v.id, r.drama_name, r.drama_type, r.confidence, r.status,
                   r.recognition_method, r.api_response, r.analysis_reason
            FROM videos v
            LEFT JOIN video_drama_recognition r ON r.video_id = v.id
            WHERE v.id = ?
            """,
            (vid,),
        )
        row = cur.fetchone()
        if not row:
            print(f"id={vid}: NO VIDEO")
            continue
        exp = EXPECTED[vid]
        name = (row["drama_name"] or "未知").replace("《", "").replace("》", "")
        ok = exp in name or name in exp
        if row["status"] == "success" and row["drama_name"]:
            total += 1
            if ok:
                hits += 1
        print(f"id={vid} expect={exp} got={row['drama_name']} conf={row['confidence']} method={row['recognition_method']} status={row['status']} OK={ok}")
        if row["api_response"]:
            resp = row["api_response"]
            for marker in ("=== 第一步", "=== 第二步", "=== 第三步", "=== 最终结论 ==="):
                if marker in resp:
                    idx = resp.find(marker)
                    snippet = resp[idx : idx + 600].replace("\n", " | ")
                    print(f"  {marker}: {snippet[:500]}...")
        print()

    if total:
        print(f"Benchmark: {hits}/{total} ({100*hits/total:.0f}%)")

    print("\n=== Failure patterns ===")
    cur.execute(
        """
        SELECT r.drama_name, COUNT(*) AS c
        FROM video_drama_recognition r
        WHERE r.status = 'success'
        GROUP BY r.drama_name
        ORDER BY c DESC
        LIMIT 15
        """
    )
    for row in cur.fetchall():
        print(dict(row))

    cur.execute(
        """
        SELECT COUNT(*) FROM video_drama_recognition WHERE status='failed'
        """
    )
    print("failed count:", cur.fetchone()[0])
    cur.execute(
        """
        SELECT substr(api_response,1,300) FROM video_drama_recognition
        WHERE status='failed' ORDER BY completed_at DESC LIMIT 3
        """
    )
    print("\nRecent failures:")
    for row in cur.fetchall():
        print(row[0])
        print("---")

    conn.close()


if __name__ == "__main__":
    main()
