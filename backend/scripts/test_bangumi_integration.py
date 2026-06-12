import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.services.drama_metadata_providers import resolve_drama_assets, supplement_reference


async def main():
    poster, url, source = await resolve_drama_assets("咒术回战", "动画、战斗", "")
    print("resolve:", source, url, bool(poster))

    parsed = {
        "drama_name": "《咒术回战》",
        "drama_type": "动画、战斗",
        "english_name": "Jujutsu Kaisen",
    }
    parsed, _log = await supplement_reference(parsed)
    print("note:", parsed.get("tmdb_ref_note"))
    print("url:", parsed.get("tmdb_url"))

    poster2, url2, source2 = await resolve_drama_assets("破墓", "恐怖、惊悚", "")
    print("movie:", source2, url2, bool(poster2))


if __name__ == "__main__":
    asyncio.run(main())
