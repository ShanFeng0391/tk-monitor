import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.services.bangumi import lookup_anime_metadata
from app.services.drama_names import bangumi_search_queries


async def main():
    name = "《恶搞之家第22季第8集》"
    print("queries:", bangumi_search_queries(name, english_name="Family Guy"))
    result, log = await lookup_anime_metadata(
        name,
        prefer_chinese_name=name,
        english_name="Family Guy",
        analysis_reason="英文名: Family Guy",
    )
    print("id:", result.get("bangumi_id") if result else None)
    print("title:", result.get("bangumi_title_cn") if result else log[:120])
    print("url:", result.get("tmdb_url") if result else None)


if __name__ == "__main__":
    asyncio.run(main())
