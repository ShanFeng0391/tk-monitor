import asyncio
import sys

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "backend"))

from app.services.scraper import scraper


async def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "user171278194880"
    videos, profile = await scraper.fetch_creator_videos(username, 0)
    print("total_fetched", len(videos))
    print("follower_count", profile.follower_count)
    above = [v for v in videos if v.view_count >= 100000]
    print("above_100k", len(above))


if __name__ == "__main__":
    asyncio.run(main())
