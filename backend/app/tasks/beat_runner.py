"""混合部署 Beat 进程：APScheduler（Daily / A 线闹钟 + B 线协调），不跑 Web。"""
from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [beat] %(levelname)s %(message)s")
logger = logging.getLogger("beat_runner")


async def _beat_heartbeat_loop() -> None:
    import json

    from app.config import get_settings

    settings = get_settings()
    node_id = settings.compute_node_id or "cloud2"

    while True:
        try:
            import redis

            client = redis.from_url(settings.redis_url, decode_responses=True)
            payload = json.dumps({"node_id": node_id, "alive": True})
            client.setex(f"cluster:beat:{node_id}", 120, payload)
        except Exception as exc:
            logger.warning("beat heartbeat failed: %s", exc)
        await asyncio.sleep(45)


async def _run() -> None:
    from app.config import get_settings
    from app.database import async_session
    from app.services import proxy_gateway
    from app.tasks.scheduler import bootstrap_scheduler, start_scheduler, stop_scheduler

    settings = get_settings()
    if settings.local_mode:
        logger.error("beat_runner 仅用于混合部署 (LOCAL_MODE=false)")
        sys.exit(1)

    async with async_session() as session:
        try:
            await proxy_gateway.sync_from_db(session)
        except Exception as exc:
            logger.warning("代理网关启动失败: %s", exc)

    scheduler = start_scheduler()
    await bootstrap_scheduler(scheduler)
    logger.info("Beat 调度器已启动（Daily / hot_ingest / B 线协调）")

    beat_hb = asyncio.create_task(_beat_heartbeat_loop())
    try:
        await asyncio.Event().wait()
    finally:
        beat_hb.cancel()
        try:
            await beat_hb
        except asyncio.CancelledError:
            pass
        stop_scheduler(scheduler)
        from app.services.proxy_gateway import stop_singbox

        stop_singbox()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
