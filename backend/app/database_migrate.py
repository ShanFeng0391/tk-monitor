"""SQLite 轻量迁移：为已有库补全新列与新表"""
import logging

from sqlalchemy import inspect, text

from app.database import engine, Base
from app.config import get_settings

logger = logging.getLogger(__name__)

# (table, column, ddl_fragment)
COLUMN_MIGRATIONS = [
    ("users", "max_collections", "INTEGER DEFAULT 5"),
    ("monitored_creators", "collection_id", "INTEGER"),
    ("monitored_creators", "group_id", "INTEGER"),
    ("videos", "content_type", "VARCHAR(50)"),
    ("videos", "is_historical_viral", "BOOLEAN DEFAULT 0"),
    ("videos", "historical_viral_at", "DATETIME"),
    ("videos", "is_daily_hot", "BOOLEAN DEFAULT 0"),
    ("videos", "daily_hot_at", "DATETIME"),
    ("videos", "daily_hot_growth", "FLOAT"),
    ("video_drama_recognition", "is_manual_override", "BOOLEAN DEFAULT 0"),
    ("video_drama_recognition", "manual_edited_by", "INTEGER"),
    ("video_drama_recognition", "manual_edited_at", "DATETIME"),
    ("monitored_creators", "last_scraped_at", "DATETIME"),
    ("monitored_creators", "historical_scraped_at", "DATETIME"),
    ("videos", "source_username", "VARCHAR(50)"),
    ("videos", "avg_view_velocity", "FLOAT"),
    ("videos", "instant_view_velocity", "FLOAT"),
    ("daily_hot_records", "avg_view_velocity", "FLOAT"),
    ("monitor_groups", "daily_hot_avg_growth_threshold", "FLOAT DEFAULT 50"),
    ("user_collections", "daily_hot_avg_growth_threshold", "FLOAT DEFAULT 50"),
    ("video_drama_recognition", "recognition_method", "VARCHAR(40)"),
    ("monitored_creators", "follower_count", "BIGINT DEFAULT 0"),
    ("favorites", "note", "TEXT"),
    ("collection_schedules", "group_id", "INTEGER"),
    ("monitor_groups", "deleted_at", "DATETIME"),
    ("users", "created_by_id", "INTEGER"),
    ("proxy_endpoints", "protocol", "VARCHAR(20) DEFAULT 'socks5'"),
    ("proxy_endpoints", "raw_uri", "TEXT"),
    ("proxy_endpoints", "local_socks_port", "INTEGER"),
    ("collection_schedules", "task_type", "VARCHAR(20) DEFAULT 'daily'"),
    ("video_snapshots", "source", "VARCHAR(20) DEFAULT 'daily'"),
    ("monitored_creators", "last_hot_ingest_at", "DATETIME"),
    ("monitored_creators", "last_hot_update_at", "DATETIME"),
    ("monitor_groups", "last_hot_update_at", "DATETIME"),
]


async def run_migrations():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def _migrate_sync(sync_conn):
            inspector = inspect(sync_conn)
            for table, column, ddl in COLUMN_MIGRATIONS:
                if not inspector.has_table(table):
                    continue
                existing = {c["name"] for c in inspector.get_columns(table)}
                if column not in existing:
                    sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                    logger.info("Added column %s.%s", table, column)

        await conn.run_sync(_migrate_sync)

        def _migrate_users_email_nullable(sync_conn):
            inspector = inspect(sync_conn)
            if not inspector.has_table("users"):
                return
            email_col = next((c for c in inspector.get_columns("users") if c["name"] == "email"), None)
            if not email_col or email_col.get("nullable"):
                return
            sync_conn.execute(text("PRAGMA foreign_keys=OFF"))
            sync_conn.execute(text("""
                CREATE TABLE users__email_null (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    email VARCHAR(100) UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(20),
                    max_monitors INTEGER,
                    max_collections INTEGER,
                    created_at DATETIME,
                    is_active BOOLEAN
                )
            """))
            sync_conn.execute(text("""
                INSERT INTO users__email_null (
                    id, username, email, password_hash, role,
                    max_monitors, max_collections, created_at, is_active
                )
                SELECT id, username, email, password_hash, role,
                       max_monitors, max_collections, created_at, is_active
                FROM users
            """))
            sync_conn.execute(text("DROP TABLE users"))
            sync_conn.execute(text("ALTER TABLE users__email_null RENAME TO users"))
            sync_conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_id ON users (id)"))
            sync_conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
            sync_conn.execute(text("PRAGMA foreign_keys=ON"))
            logger.info("Migrated users.email to nullable")

        await conn.run_sync(_migrate_users_email_nullable)

        def _ensure_single_super_admin(sync_conn):
            """仅保留配置中的 admin 账号为超级管理员，并修正历史误升数据。"""
            admin_username = get_settings().admin_username
            sync_conn.execute(
                text("UPDATE users SET role = 'user' WHERE role = 'super_admin' AND username != :name"),
                {"name": admin_username},
            )
            sync_conn.execute(
                text("UPDATE users SET role = 'super_admin' WHERE username = :name"),
                {"name": admin_username},
            )

        await conn.run_sync(_ensure_single_super_admin)
