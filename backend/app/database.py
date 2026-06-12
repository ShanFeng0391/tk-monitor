import os

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

_engine_kwargs = {}
if settings.local_mode:
    os.makedirs(settings.data_dir, exist_ok=True)
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
else:
    _engine_kwargs.update(
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
    )

engine = create_async_engine(
    settings.effective_database_url,
    echo=settings.debug,
    **_engine_kwargs,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

sync_engine = create_engine(
    settings.effective_database_url_sync,
    echo=settings.debug,
    connect_args={"check_same_thread": False, "timeout": 30} if settings.local_mode else {},
    pool_pre_ping=not settings.local_mode,
    pool_size=5 if not settings.local_mode else 5,
    max_overflow=10 if not settings.local_mode else 10,
)
SyncSessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)


def _configure_sqlite_connection(dbapi_conn, _connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


if settings.local_mode:
    event.listen(engine.sync_engine, "connect", _configure_sqlite_connection)
    event.listen(sync_engine, "connect", _configure_sqlite_connection)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_db():
    db = SyncSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
