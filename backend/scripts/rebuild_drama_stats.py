"""全量重算 drama_stats（修复测试期间关联视频数失真）。"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
os.environ.setdefault("DATA_DIR", str(ROOT / "data"))
sys.path.insert(0, str(ROOT / "backend"))

from app.database import async_session  # noqa: E402
from app.services.drama_stats import rebuild_all_drama_stats  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.models import DramaStats  # noqa: E402


async def main() -> None:
    async with async_session() as db:
        count = await rebuild_all_drama_stats(db)
        await db.commit()
        rows = (await db.execute(
            select(DramaStats.drama_name, DramaStats.total_videos).order_by(DramaStats.total_videos.desc())
        )).all()
        print(f"rebuilt {count} dramas")
        for name, total in rows:
            print(f"  {name}: {total}")


if __name__ == "__main__":
    asyncio.run(main())
