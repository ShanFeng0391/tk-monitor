"""清空指定博主视频数据并重新触发历史采集。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import delete, select

from app.database import async_session
from app.models import (
    DailyHotRecord,
    DataShare,
    DramaStats,
    Favorite,
    HistoricalViralArchive,
    MonitoredCreator,
    Video,
)
from app.services.collection import collection_service


async def clear_creator(username: str) -> int:
    async with async_session() as db:
        creator = (
            await db.execute(
                select(MonitoredCreator).where(MonitoredCreator.tiktok_username == username)
            )
        ).scalar_one_or_none()
        if not creator:
            raise SystemExit(f"博主 @{username} 不存在")

        videos = (
            await db.execute(select(Video).where(Video.creator_id == creator.id))
        ).scalars().all()
        video_ids = [v.id for v in videos]

        if video_ids:
            await db.execute(delete(Favorite).where(Favorite.video_id.in_(video_ids)))
            await db.execute(delete(DataShare).where(DataShare.video_id.in_(video_ids)))
            await db.execute(delete(DailyHotRecord).where(DailyHotRecord.video_id.in_(video_ids)))
            await db.execute(delete(HistoricalViralArchive).where(HistoricalViralArchive.video_id.in_(video_ids)))
            for video in videos:
                if video.cover_local_path and os.path.isfile(video.cover_local_path):
                    try:
                        os.remove(video.cover_local_path)
                    except OSError:
                        pass
                await db.delete(video)

        await db.execute(
            delete(HistoricalViralArchive).where(
                HistoricalViralArchive.creator_username == creator.tiktok_username
            )
        )
        await db.execute(delete(DramaStats))

        creator.last_scraped_at = None
        creator.historical_scraped_at = None
        await db.commit()
        return len(video_ids)


async def rescrape(username: str):
    from sqlalchemy.orm import selectinload

    async with async_session() as db:
        creator = (
            await db.execute(
                select(MonitoredCreator)
                .options(
                    selectinload(MonitoredCreator.group),
                    selectinload(MonitoredCreator.collection),
                )
                .where(MonitoredCreator.tiktok_username == username)
            )
        ).scalar_one()
        stats = await collection_service.scrape_creator(db, creator, mode="historical")
        await db.commit()
        return stats.to_dict()


async def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "user171278194880"
    removed = await clear_creator(username)
    print(f"已删除 {removed} 条视频及相关归档")
    result = await rescrape(username)
    print(f"采集结果: {result}")


if __name__ == "__main__":
    asyncio.run(main())
