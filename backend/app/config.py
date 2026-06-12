import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "TikTok Monitor"
    app_env: str = "development"
    secret_key: str = "change-me"
    debug: bool = True
    local_mode: bool = False
    serve_frontend: bool = False
    enable_api_docs: bool = False
    cors_origins: str = ""
    scrape_allow_mock: bool = True
    data_dir: str = str(PROJECT_ROOT / "data")

    database_url: str = "postgresql+asyncpg://tiktok:tiktok123@localhost:5432/tiktok_monitor"
    database_url_sync: str = "postgresql://tiktok:tiktok123@localhost:5432/tiktok_monitor"

    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "change-me-jwt"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "covers"
    minio_secure: bool = False

    scrape_interval_minutes: int = 1440
    scrape_video_window_hours: int = 30
    scrape_request_delay_min: int = 3
    scrape_request_delay_max: int = 10
    scrape_max_retries: int = 3
    scrape_retry_interval_minutes: int = 5
    scrape_proxy_url: str = ""

    proxy_pool_enabled: bool = True
    proxy_pool_redis_db: int = 1
    proxy_pool_health_url: str = "https://www.tiktok.com"
    proxy_pool_bad_ttl_seconds: int = 1800
    proxy_pool_max_fail_streak: int = 3
    proxy_pool_local_env_fallback: bool = True
    proxy_gateway_base_port: int = 18080
    singbox_enabled: bool = True
    singbox_bin: str = ""

    # 增量采集策略：10 天内每 3 天更新，超过 10 天不更新
    recent_video_days: int = 10
    recent_video_update_days: int = 3

    viral_view_threshold: int = 100000
    viral_growth_threshold: float = 50.0
    hot_like_growth_threshold: float = 30.0

    # 两大核心功能默认阈值
    historical_view_threshold: int = 100000
    daily_hot_avg_growth_threshold: float = 50.0
    growth_window_minutes: int = 30
    historical_scrape_window_hours: int = 0

    # 影视剧识别等
    doubao_enabled: bool = True
    ark_api_key: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_model: str = "doubao-1-5-vision-pro-32k-250115"
    tmdb_api_key: str = ""
    tmdb_read_access_token: str = ""
    bangumi_enabled: bool = True
    bangumi_access_token: str = ""
    bangumi_user_agent: str = "tiktok-monitor/1.0 (https://github.com/local/tiktok-monitor)"
    recognition_auto_trigger: bool = False
    recognition_batch_size: int = 10
    recognition_max_retries: int = 3
    recognition_cooldown_hours: int = 24
    recognition_daily_budget: float = 50.0
    recognition_confidence_threshold: float = 60.0
    recognition_max_cover_variants: int = 6
    recognition_stream_frames_enabled: bool = True
    recognition_stream_frame_count: int = 5

    admin_username: str = "admin"
    admin_password: str = "nimda321"
    admin_email: str = "admin@example.com"

    celery_worker_concurrency: int = 24
    api_uvicorn_workers: int = 1

    snapshot_retention_days: int = 90
    snapshot_purge_batch_size: int = 5000
    postgres_backup_keep_local: int = 7
    postgres_backup_keep_remote: int = 14
    postgres_backup_bucket_prefix: str = "backups/postgres"
    # 本地 Windows 跑 Beat 时设为 false；PG 备份在腾讯云轻量上 cron 执行
    postgres_backup_enabled: bool = True

    compute_node_id: str = "local"
    compute_node_label: str = "本地电脑"
    beat_enabled_on_node: bool = False
    celery_worker_node_prefix: str = "local"
    cluster_peer_api_url: str = ""
    cluster_expected_workers_local: int = 24
    cluster_expected_workers_cloud2: int = 10
    cluster_node_label_local: str = "本地电脑"
    cluster_node_label_cloud2: str = "轻量云 #2"

    # 超级管理员 Web 一键更新本节点（默认关闭，需在 .env 显式开启）
    web_deploy_update_enabled: bool = False

    @property
    def covers_dir(self) -> str:
        return os.path.join(self.data_dir, "covers")

    @property
    def effective_database_url(self) -> str:
        if self.local_mode:
            db_path = os.path.join(self.data_dir, "tiktok_monitor.db").replace("\\", "/")
            return f"sqlite+aiosqlite:///{db_path}"
        return self.database_url

    @property
    def effective_database_url_sync(self) -> str:
        if self.local_mode:
            db_path = os.path.join(self.data_dir, "tiktok_monitor.db").replace("\\", "/")
            return f"sqlite:///{db_path}"
        return self.database_url_sync


@lru_cache
def get_settings() -> Settings:
    return Settings()
