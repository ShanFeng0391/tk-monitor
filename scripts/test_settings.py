import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.database import async_session
from app.services.runtime_settings import runtime


async def main():
    async with async_session() as db:
        await runtime.load(db)
        print("before", runtime.to_api_dict())
        await runtime.save(db, {"historical_view": 250000})
    async with async_session() as db:
        await runtime.load(db)
        print("after", runtime.to_api_dict())


if __name__ == "__main__":
    asyncio.run(main())
