from datetime import datetime, date
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Date, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    monitored_creators = relationship("MonitoredCreator", back_populates="user", cascade="all, delete-orphan")
    created_users = relationship("User", back_populates="created_by", foreign_keys=[created_by_id])
    created_by = relationship("User", remote_side=[id], foreign_keys=[created_by_id])
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")
    collections = relationship("UserCollection", back_populates="user", cascade="all, delete-orphan")
    monitor_groups = relationship("MonitorGroup", back_populates="owner", cascade="all, delete-orphan")


class MonitorGroup(Base):
    """管理员监控分组 — 每组独立阈值"""
    __tablename__ = "monitor_groups"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    historical_view_threshold = Column(Integer, default=100000)
    daily_hot_avg_growth_threshold = Column(Float, default=50.0)
    growth_window_minutes = Column(Integer, default=30)
    scrape_window_hours = Column(Integer, default=30)
    max_creators = Column(Integer, default=999)
    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime, nullable=True)
    last_hot_update_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="monitor_groups")
    creators = relationship("MonitoredCreator", back_populates="group")
    schedules = relationship("CollectionSchedule", backref="group")
    hot_update_segments = relationship(
        "HotUpdateSegment", back_populates="group", cascade="all, delete-orphan",
        order_by="HotUpdateSegment.sort_order",
    )


class UserCollection(Base):
    """普通用户监控合集 — 分区独立阈值与博主"""
    __tablename__ = "user_collections"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    historical_view_threshold = Column(Integer, default=100000)
    daily_hot_avg_growth_threshold = Column(Float, default=50.0)
    growth_window_minutes = Column(Integer, default=30)
    scrape_window_hours = Column(Integer, default=30)
    max_creators = Column(Integer, default=10)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="collections")
    creators = relationship("MonitoredCreator", back_populates="collection")


class MonitoredCreator(Base):
    __tablename__ = "monitored_creators"
    __table_args__ = (UniqueConstraint("collection_id", "tiktok_username"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    collection_id = Column(Integer, ForeignKey("user_collections.id"), nullable=True)
    group_id = Column(Integer, ForeignKey("monitor_groups.id"), nullable=True)
    tiktok_username = Column(String(50), nullable=False)
    tiktok_user_id = Column(String(50))
    display_name = Column(String(100))
    follower_count = Column(BigInteger, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_scraped_at = Column(DateTime)
    last_hot_ingest_at = Column(DateTime)
    last_hot_update_at = Column(DateTime)
    historical_scraped_at = Column(DateTime)

    user = relationship("User", back_populates="monitored_creators")
    collection = relationship("UserCollection", back_populates="creators")
    group = relationship("MonitorGroup", back_populates="creators")
    videos = relationship("Video", back_populates="creator", cascade="all, delete-orphan")


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("monitored_creators.id"), nullable=False)
    video_id = Column(String(50), unique=True, nullable=False, index=True)
    title = Column(Text)
    description = Column(Text)
    video_url = Column(String(500), nullable=False)
    source_username = Column(String(50))
    cover_url = Column(String(500))
    cover_local_path = Column(String(500))
    published_at = Column(DateTime)
    duration = Column(Integer)
    view_count = Column(BigInteger, default=0)
    like_count = Column(BigInteger, default=0)
    share_count = Column(BigInteger, default=0)
    comment_count = Column(BigInteger, default=0)
    category = Column(String(30), default="normal")
    content_type = Column(String(50))
    traffic_grade = Column(String(5))
    is_featured = Column(Boolean, default=False)
    is_historical_viral = Column(Boolean, default=False)
    historical_viral_at = Column(DateTime)
    is_daily_hot = Column(Boolean, default=False)
    daily_hot_at = Column(DateTime)
    daily_hot_growth = Column(Float)
    avg_view_velocity = Column(Float)
    instant_view_velocity = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = relationship("MonitoredCreator", back_populates="videos")
    snapshots = relationship("VideoSnapshot", back_populates="video", cascade="all, delete-orphan")
    recognition = relationship("VideoDramaRecognition", back_populates="video", uselist=False, cascade="all, delete-orphan")
    historical_archive = relationship("HistoricalViralArchive", back_populates="video", uselist=False, cascade="all, delete-orphan")


class HistoricalViralArchive(Base):
    """功能1：历史爆款长期归档表（只增不改，用于检索分析）"""
    __tablename__ = "historical_viral_archive"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"), unique=True, nullable=False)
    video_platform_id = Column(String(50), index=True)
    title = Column(Text)
    creator_username = Column(String(50), index=True)
    content_type = Column(String(50), index=True)
    view_count = Column(BigInteger)
    like_count = Column(BigInteger)
    share_count = Column(BigInteger)
    comment_count = Column(BigInteger)
    threshold_used = Column(Integer)
    published_at = Column(DateTime)
    archived_at = Column(DateTime, default=datetime.utcnow, index=True)

    video = relationship("Video", back_populates="historical_archive")


class DailyHotRecord(Base):
    """功能2：当日优质热门记录（按日汇总，全平台大盘）"""
    __tablename__ = "daily_hot_records"
    __table_args__ = (UniqueConstraint("video_id", "hot_date"),)

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False, index=True)
    hot_date = Column(Date, nullable=False, index=True)
    view_count = Column(BigInteger)
    view_growth = Column(Float)
    avg_view_velocity = Column(Float)
    view_threshold_used = Column(Integer)
    growth_threshold_used = Column(Float)
    detected_at = Column(DateTime, default=datetime.utcnow)

    video = relationship("Video")


class VideoSnapshot(Base):
    __tablename__ = "video_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(String(50), ForeignKey("videos.video_id"), nullable=False, index=True)
    view_count = Column(BigInteger)
    like_count = Column(BigInteger)
    share_count = Column(BigInteger)
    comment_count = Column(BigInteger)
    source = Column(String(20), default="daily")  # daily | hot_ingest | hot_update
    snapshot_at = Column(DateTime, default=datetime.utcnow, index=True)

    video = relationship("Video", back_populates="snapshots", foreign_keys=[video_id], primaryjoin="VideoSnapshot.video_id==Video.video_id")


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "video_id"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    folder_name = Column(String(50), default="默认收藏夹")
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="favorites")
    video = relationship("Video")


class DataShare(Base):
    __tablename__ = "data_shares"
    __table_args__ = (UniqueConstraint("admin_id", "target_user_id", "video_id"),)

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    shared_at = Column(DateTime, default=datetime.utcnow)


class VideoDramaRecognition(Base):
    __tablename__ = "video_drama_recognition"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"), unique=True, nullable=False)
    drama_name = Column(String(200))
    drama_type = Column(String(50))
    confidence = Column(Float)
    actors = Column(Text)
    analysis_reason = Column(Text)
    cover_image_path = Column(String(500))
    prompt_text = Column(Text)
    api_model = Column(String(100))
    api_response = Column(Text)
    tokens_used = Column(Integer)
    api_cost = Column(Float)
    status = Column(String(20), default="pending")
    retry_count = Column(Integer, default=0)
    is_manual_override = Column(Boolean, default=False)
    manual_edited_by = Column(Integer, ForeignKey("users.id"))
    manual_edited_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    recognition_method = Column(String(40))

    video = relationship("Video", back_populates="recognition")


class DramaStats(Base):
    __tablename__ = "drama_stats"

    id = Column(Integer, primary_key=True, index=True)
    drama_name = Column(String(200), unique=True, nullable=False, index=True)
    drama_type = Column(String(50))
    total_videos = Column(Integer, default=0)
    total_views = Column(BigInteger, default=0)
    total_likes = Column(BigInteger, default=0)
    viral_videos = Column(Integer, default=0)
    first_seen_at = Column(DateTime)
    last_seen_at = Column(DateTime)
    trend_direction = Column(String(20), default="stable")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProxyEndpoint(Base):
    """代理池节点（SOCKS5 / vmess / vless，超级管理员维护）。"""
    __tablename__ = "proxy_endpoints"

    id = Column(Integer, primary_key=True, index=True)
    protocol = Column(String(20), default="socks5")  # socks5 | vmess | vless
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(255), default="")
    password = Column(String(255), default="")
    raw_uri = Column(Text)
    local_socks_port = Column(Integer)
    label = Column(String(100), default="")
    enabled = Column(Boolean, default=True)
    health_status = Column(String(20), default="unknown")
    last_check_at = Column(DateTime)
    last_ok_at = Column(DateTime)
    last_error = Column(Text)
    fail_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HotUpdateSegment(Base):
    """热门更新线 B：分时段采集周期（每组一套，须覆盖 24 小时）。"""
    __tablename__ = "hot_update_segments"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("monitor_groups.id"), nullable=False, index=True)
    start_time = Column(String(5), nullable=False)  # HH:MM 北京时间
    end_time = Column(String(5), nullable=False)
    interval_minutes = Column(Integer, nullable=False, default=30)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("MonitorGroup", back_populates="hot_update_segments")


class CollectionSchedule(Base):
    """博主采集闹钟：daily 增量 / hot_ingest 热门入库（每日定点 / 单次定时）。"""
    __tablename__ = "collection_schedules"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("monitor_groups.id"), nullable=True)
    name = Column(String(100), default="")
    task_type = Column(String(20), default="daily")  # daily | hot_ingest
    schedule_type = Column(String(20), nullable=False)  # daily | once
    run_time = Column(String(5))  # HH:MM，配合 timezone 使用
    run_at = Column(DateTime)  # 单次任务 UTC 时间
    timezone = Column(String(50), default="Asia/Shanghai")
    enabled = Column(Boolean, default=True)
    executed = Column(Boolean, default=False)
    last_run_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


Index("idx_recognition_status", VideoDramaRecognition.status)
Index("idx_recognition_drama", VideoDramaRecognition.drama_name)
Index("idx_historical_archive_type", HistoricalViralArchive.content_type)
Index("idx_historical_archive_creator", HistoricalViralArchive.creator_username)
Index("idx_daily_hot_date", DailyHotRecord.hot_date, DailyHotRecord.view_growth)
