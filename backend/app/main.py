import asyncio
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.config import get_settings
from app.database import engine, Base, async_session
from app.database_migrate import run_migrations
from app.models import User
from app.core.security import hash_password, verify_password
from app.api.routes import router
from app.api.system import router as system_router
from app.api.core_videos import router as core_router
from app.api.groups import router as groups_router
from app.api.collections import router as collections_router
from app.api.admin_users import router as admin_users_router
from app.api.access_gate import router as access_gate_router
from app.api.admin_proxies import router as admin_proxies_router
from app.api.admin_cluster import router as admin_cluster_router
from app.tasks.scheduler import start_scheduler, stop_scheduler, bootstrap_scheduler
from app.services.runtime_settings import runtime

settings = get_settings()
logger = logging.getLogger(__name__)


def _verify_socks_support() -> None:
    try:
        import socksio  # noqa: F401
    except ImportError:
        logger.warning(
            "未安装 socksio，SOCKS5 代理池不可用。请在后端 venv 执行: pip install httpx[socks]"
        )


async def init_db():
    await run_migrations()

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.username == settings.admin_username)
        )
        if not result.scalar_one_or_none():
            admin = User(
                username=settings.admin_username,
                email=settings.admin_email,
                password_hash=hash_password(settings.admin_password),
                role="super_admin",
            )
            session.add(admin)
            await session.commit()
        else:
            admin_user = (await session.execute(
                select(User).where(User.username == settings.admin_username)
            )).scalar_one()
            changed = False
            if admin_user.role != "super_admin":
                admin_user.role = "super_admin"
                changed = True
            if not verify_password(settings.admin_password, admin_user.password_hash):
                admin_user.password_hash = hash_password(settings.admin_password)
                changed = True
            if changed:
                await session.commit()

        await runtime.load(session)
        from app.services.group_helpers import purge_expired_groups
        purged = await purge_expired_groups(session)
        if purged:
            await session.commit()


async def _cluster_heartbeat_loop():
    while True:
        try:
            if not settings.local_mode:
                from app.services.cluster_monitor import publish_current_node_heartbeat

                await publish_current_node_heartbeat()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("cluster heartbeat failed")
        await asyncio.sleep(45)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _verify_socks_support()
    await init_db()
    from app.database import async_session
    from app.services import proxy_gateway

    async with async_session() as session:
        try:
            await proxy_gateway.sync_from_db(session)
        except Exception as exc:
            logger.warning("代理网关启动失败: %s", exc)

    scheduler = None
    if settings.local_mode:
        scheduler = start_scheduler()
        await bootstrap_scheduler(scheduler)
        app.state.scheduler = scheduler
    else:
        app.state.scheduler = None
        logger.info("混合部署：APScheduler 由独立 Beat 进程运行，采集由 Celery Worker 执行")

    heartbeat_task = None
    if not settings.local_mode:
        heartbeat_task = asyncio.create_task(_cluster_heartbeat_loop())

    yield
    from app.services.proxy_gateway import stop_singbox

    if heartbeat_task:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
    stop_singbox()
    if scheduler is not None:
        stop_scheduler(scheduler)


def _is_production_hardened() -> bool:
    return settings.app_env == "production" and not settings.debug


def _api_docs_enabled() -> bool:
    if settings.enable_api_docs:
        return True
    return not _is_production_hardened()


def _resolve_cors_origins() -> list[str]:
    raw = (settings.cors_origins or "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    if _is_production_hardened():
        return []
    return ["*"]


_docs_enabled = _api_docs_enabled()
_cors_origins = _resolve_cors_origins()

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
elif not _is_production_hardened():
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(router)
app.include_router(system_router)
app.include_router(core_router)
app.include_router(groups_router)
app.include_router(collections_router)
app.include_router(admin_users_router)
app.include_router(access_gate_router)
app.include_router(admin_proxies_router)
app.include_router(admin_cluster_router)

if settings.local_mode:
    os.makedirs(settings.covers_dir, exist_ok=True)
    app.mount("/static/covers", StaticFiles(directory=settings.covers_dir), name="covers")


def _frontend_dist():
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, "frontend", "dist")


if settings.serve_frontend:
    from fastapi.responses import FileResponse

    _dist = os.path.abspath(_frontend_dist())
    _assets = os.path.join(_dist, "assets")
    if os.path.isdir(_assets):
        app.mount("/assets", StaticFiles(directory=_assets), name="frontend_assets")

    @app.get("/{spa_path:path}")
    async def spa_fallback(spa_path: str):
        if spa_path.startswith("api") or spa_path in ("docs", "openapi.json", "redoc"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = os.path.join(_dist, spa_path)
        if spa_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        index = os.path.join(_dist, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Frontend not built")


@app.get("/")
async def root():
    if settings.serve_frontend:
        index = os.path.join(os.path.abspath(_frontend_dist()), "index.html")
        if os.path.isfile(index):
            from fastapi.responses import FileResponse
            return FileResponse(index)
    return {"name": settings.app_name, "version": "1.0.0"}
