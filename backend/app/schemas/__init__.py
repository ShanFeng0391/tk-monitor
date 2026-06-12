from datetime import datetime, date
from typing import Optional, Literal, List

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRegister(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    email: Optional[EmailStr] = None
    password: str = Field(min_length=6, max_length=100)
    gate_answer: Optional[str] = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v


class UserLogin(BaseModel):
    username: str
    password: str
    gate_answer: Optional[str] = None


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    email: Optional[EmailStr] = None
    password: str = Field(min_length=6, max_length=100)
    role: Optional[Literal["super_admin", "admin", "user"]] = "user"
    is_active: Optional[bool] = True

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v


class AdminUserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=100)
    role: Optional[Literal["super_admin", "admin", "user"]] = None
    is_active: Optional[bool] = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v


class UserStatusUpdate(BaseModel):
    is_active: bool


class AccessGatePublic(BaseModel):
    enabled: bool
    question: Optional[str] = None


class AccessGateOut(AccessGatePublic):
    has_answer: bool = False


class AccessGateUpdate(BaseModel):
    question: str = Field(min_length=1, max_length=200)
    answer: Optional[str] = Field(default=None, max_length=200)


class CreatorCreate(BaseModel):
    tiktok_username: str = Field(min_length=2, max_length=51)

    @field_validator("tiktok_username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("请输入用户名")
        if not value.startswith("@"):
            value = f"@{value}"
        if len(value) < 2:
            raise ValueError("请输入有效的用户名")
        return value
    group_id: int = Field(ge=1)


class CreatorUpdate(BaseModel):
    group_id: int = Field(ge=1)


class CreatorOut(BaseModel):
    id: int
    tiktok_username: str
    tiktok_user_id: Optional[str] = None
    display_name: Optional[str] = None
    follower_count: int = 0
    is_active: bool
    created_at: datetime
    last_scraped_at: Optional[datetime] = None
    last_hot_ingest_at: Optional[datetime] = None
    last_hot_update_at: Optional[datetime] = None
    historical_scraped_at: Optional[datetime] = None
    video_count: int = 0
    user_id: Optional[int] = None
    owner_username: Optional[str] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None
    can_delete: bool = True

    model_config = {"from_attributes": True}


class CreatorPasteRequest(BaseModel):
    pasted_text: str = Field(min_length=1, max_length=12000)


class CreatorPasteOut(BaseModel):
    usernames: List[str] = []
    source: str = "regex"
    tokens_used: int = 0


class CreatorBatchCreate(BaseModel):
    tiktok_usernames: List[str] = Field(min_length=1, max_length=50)
    group_id: int = Field(ge=1)


class CreatorBatchResultItem(BaseModel):
    tiktok_username: str
    ok: bool
    message: str = ""
    creator: Optional["CreatorOut"] = None


class CreatorBatchCreateOut(BaseModel):
    succeeded: int = 0
    failed: int = 0
    results: List[CreatorBatchResultItem] = []


class ScrapeResultOut(BaseModel):
    new_videos: int = 0
    updated_videos: int = 0
    skipped_videos: int = 0
    fetched_videos: int = 0
    total_processed: int = 0
    message: str = ""


class VideoOut(BaseModel):
    id: int
    video_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    video_url: str
    cover_url: Optional[str] = None
    cover_local_path: Optional[str] = None
    published_at: Optional[datetime] = None
    duration: Optional[int] = None
    view_count: int = 0
    like_count: int = 0
    share_count: int = 0
    comment_count: int = 0
    category: str = "normal"
    content_type: Optional[str] = None
    traffic_grade: Optional[str] = None
    is_featured: bool = False
    is_historical_viral: bool = False
    is_daily_hot: bool = False
    daily_hot_growth: Optional[float] = None
    avg_view_velocity: Optional[float] = None
    instant_view_velocity: Optional[float] = None
    creator_username: Optional[str] = None
    creator_id: Optional[int] = None
    creator_follower_count: int = 0
    drama_name: Optional[str] = None
    drama_type: Optional[str] = None
    view_growth: Optional[float] = None
    like_growth: Optional[float] = None
    is_favorited: bool = False

    model_config = {"from_attributes": True}


class HistoricalViralOut(VideoOut):
    archive_id: int
    threshold_used: Optional[int] = None
    archived_at: datetime


class DailyHotOut(VideoOut):
    record_id: int
    hot_date: date
    view_threshold_used: Optional[int] = None
    growth_threshold_used: Optional[float] = None
    detected_at: datetime


class HistoricalSearchParams(BaseModel):
    keyword: Optional[str] = None
    creator_username: Optional[str] = None
    content_type: Optional[str] = None


class VideoDetailOut(VideoOut):
    snapshots: List["SnapshotOut"] = []
    recognition: Optional["RecognitionOut"] = None


class DramaScatterPoint(BaseModel):
    video_id: int
    title: Optional[str] = None
    published_at: datetime
    view_count: int = 0
    creator_username: Optional[str] = None
    is_current: bool = False


class DramaScatterOut(BaseModel):
    drama_name: Optional[str] = None
    points: List[DramaScatterPoint] = []


class SnapshotOut(BaseModel):
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    snapshot_at: datetime

    model_config = {"from_attributes": True}


class FavoriteCreate(BaseModel):
    folder_name: str = "默认收藏夹"
    note: Optional[str] = None


class FavoriteUpdate(BaseModel):
    note: Optional[str] = None
    folder_name: Optional[str] = None


class FavoriteBatchDelete(BaseModel):
    ids: list[int] = Field(..., min_length=1)


class FavoriteOut(BaseModel):
    id: int
    folder_name: str
    note: Optional[str] = None
    created_at: datetime
    video: VideoOut

    model_config = {"from_attributes": True}


class ShareCreate(BaseModel):
    target_user_id: int
    video_id: int


class ShareOut(BaseModel):
    id: int
    video: VideoOut
    shared_at: datetime
    target_username: Optional[str] = None

    model_config = {"from_attributes": True}


class DashboardStats(BaseModel):
    total_creators: int
    total_videos: int
    viral_count: int
    hot_count: int
    total_views: int
    total_likes: int


class DashboardCollectionSegment(BaseModel):
    start_time: str
    end_time: str
    interval_minutes: int


class DashboardCollectionGroupStatus(BaseModel):
    group_id: int
    group_name: str
    last_hot_update_at: Optional[datetime] = None
    last_hot_ingest_at: Optional[datetime] = None
    hot_update_running: bool = False
    current_segment: Optional[DashboardCollectionSegment] = None
    next_hot_update_at: Optional[datetime] = None
    b_due_now: bool = False
    daily_schedules_enabled: int = 0
    hot_ingest_schedules_enabled: int = 0
    segment_count: int = 0


class DashboardCollectionCoordinator(BaseModel):
    status: str = "scheduled"
    check_interval_minutes: int = 1
    description: str = ""


class DashboardCollectionStatusOut(BaseModel):
    items: List[DashboardCollectionGroupStatus] = []
    coordinator: DashboardCollectionCoordinator


class ViralTypeShare(BaseModel):
    content_type: str
    count: int
    percentage: float


class PeriodicViralRecommend(BaseModel):
    drama_name: str
    drama_type: Optional[str] = None
    historical_viral_count: int
    days_since_last_viral: int
    recent_max_views: int
    cycle_score: float
    reason: str


class MultiViralDrama(BaseModel):
    drama_name: str
    drama_type: Optional[str] = None
    viral_count: int
    latest_archived_at: datetime
    total_views: int


class ViralPredictionOut(BaseModel):
    period_days: int = 3
    recent_type_shares: List[ViralTypeShare] = []
    periodic_recommendations: List[PeriodicViralRecommend] = []
    multi_viral_dramas: List[MultiViralDrama] = []


class GrowthPoint(BaseModel):
    snapshot_at: datetime
    view_count: int
    like_count: int


class RecognitionOut(BaseModel):
    id: int
    drama_name: Optional[str] = None
    drama_type: Optional[str] = None
    confidence: Optional[float] = None
    actors: Optional[str] = None
    analysis_reason: Optional[str] = None
    recognition_method: Optional[str] = None
    status: str
    is_manual_override: bool = False
    manual_edited_at: Optional[datetime] = None
    tmdb_poster_url: Optional[str] = None
    tmdb_url: Optional[str] = None
    metadata_source: Optional[str] = None  # tmdb | bangumi
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DramaMetadataLookupRequest(BaseModel):
    drama_name: str = Field(min_length=1, max_length=200)


class DramaDoubaoPasteRequest(BaseModel):
    pasted_text: str = Field(min_length=20, max_length=12000)


class DramaMetadataLookupOut(BaseModel):
    drama_name: str
    drama_type: str = "未知"
    english_name: str = ""
    release_year: str = ""
    actors: str = ""
    director: str = ""
    summary: str = ""
    source: str = "unknown"
    verified: bool = False
    tmdb_id: Optional[int] = None
    tmdb_url: str = ""
    tmdb_ref_note: str = ""
    bangumi_id: Optional[int] = None
    metadata_source: Optional[str] = None
    tokens_used: int = 0


class RecognitionManualUpdate(BaseModel):
    drama_name: Optional[str] = None
    drama_type: Optional[str] = None
    actors: Optional[str] = None
    analysis_reason: Optional[str] = None


class BatchRecognitionRequest(BaseModel):
    video_ids: List[int]


class DramaOut(BaseModel):
    drama_name: str
    drama_type: Optional[str] = None
    total_videos: int = 0
    total_views: int = 0
    total_likes: int = 0
    viral_videos: int = 0
    trend_direction: str = "stable"
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DramaDetailOut(DramaOut):
    recognition: Optional[RecognitionOut] = None


class RecognitionStats(BaseModel):
    total: int
    pending: int
    success: int
    failed: int
    daily_cost: float
    daily_budget: float


class SystemHealth(BaseModel):
    status: str
    database: str
    redis: str
    celery: str
    timestamp: datetime


class SystemSettingsOut(BaseModel):
    historical_view: int
    daily_hot_avg_growth: float
    growth_window: int
    scrape_interval: int
    recent_video_days: int
    recent_video_update_days: int
    doubao_enabled: bool
    daily_budget: float
    confidence: float


class SystemSettingsUpdate(BaseModel):
    historical_view: Optional[int] = None
    daily_hot_avg_growth: Optional[float] = None
    growth_window: Optional[int] = None
    scrape_interval: Optional[int] = None
    recent_video_days: Optional[int] = None
    recent_video_update_days: Optional[int] = None
    doubao_enabled: Optional[bool] = None
    daily_budget: Optional[float] = None
    confidence: Optional[float] = None


class CollectionScheduleOut(BaseModel):
    id: int
    group_id: Optional[int] = None
    name: str = ""
    task_type: str = "daily"
    schedule_type: str
    run_time: Optional[str] = None
    run_at: Optional[datetime] = None
    timezone: str = "Asia/Shanghai"
    enabled: bool = True
    executed: bool = False
    last_run_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CollectionScheduleCreate(BaseModel):
    name: str = ""
    group_id: Optional[int] = None
    task_type: Literal["daily", "hot_ingest"] = "daily"
    schedule_type: Literal["daily", "once"]
    run_time: Optional[str] = None  # HH:MM for daily
    run_at: Optional[datetime] = None  # for once (UTC)
    timezone: str = "Asia/Shanghai"
    enabled: bool = True


class CollectionScheduleUpdate(BaseModel):
    name: Optional[str] = None
    run_time: Optional[str] = None
    run_at: Optional[datetime] = None
    timezone: Optional[str] = None
    enabled: Optional[bool] = None


class HotUpdateSegmentOut(BaseModel):
    id: int
    group_id: int
    start_time: str
    end_time: str
    interval_minutes: int
    sort_order: int = 0

    model_config = {"from_attributes": True}


class HotUpdateSegmentItem(BaseModel):
    start_time: str = Field(pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")
    end_time: str = Field(pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")
    interval_minutes: int = Field(ge=5)
    sort_order: int = 0


class HotUpdateSegmentsReplace(BaseModel):
    segments: List[HotUpdateSegmentItem] = Field(min_length=1)


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int


class ThresholdOut(BaseModel):
    historical_view_threshold: int
    daily_hot_avg_growth_threshold: float
    growth_window_minutes: int
    scrape_window_hours: int


class MonitorGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    historical_view_threshold: int = 100000
    daily_hot_avg_growth_threshold: float = 50.0
    growth_window_minutes: int = 30
    scrape_window_hours: int = 30
    max_creators: int = 999


class MonitorGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    historical_view_threshold: Optional[int] = None
    daily_hot_avg_growth_threshold: Optional[float] = None
    growth_window_minutes: Optional[int] = None
    scrape_window_hours: Optional[int] = None
    max_creators: Optional[int] = None
    is_active: Optional[bool] = None


class MonitorGroupDeleteConfirm(BaseModel):
    password: str = Field(min_length=1, max_length=100)
    confirm_password: str = Field(min_length=1, max_length=100)


class MonitorGroupOut(ThresholdOut):
    id: int
    name: str
    description: Optional[str] = None
    max_creators: int
    is_active: bool
    creator_count: int = 0
    schedule_count: int = 0
    created_at: datetime
    updated_at: datetime


class UserCollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    historical_view_threshold: int = 100000
    daily_hot_avg_growth_threshold: float = 50.0
    growth_window_minutes: int = 30
    scrape_window_hours: int = 30
    max_creators: int = 10


class UserCollectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    historical_view_threshold: Optional[int] = None
    daily_hot_avg_growth_threshold: Optional[float] = None
    growth_window_minutes: Optional[int] = None
    scrape_window_hours: Optional[int] = None
    max_creators: Optional[int] = None
    is_active: Optional[bool] = None


class UserCollectionOut(ThresholdOut):
    id: int
    name: str
    description: Optional[str] = None
    max_creators: int
    is_active: bool
    creator_count: int = 0
    created_at: datetime
    updated_at: datetime


class ProxyCreate(BaseModel):
    host: str = Field(default="", max_length=255)
    port: int = Field(default=1080, ge=1, le=65535)
    username: str = ""
    password: str = ""
    label: str = ""
    enabled: bool = True
    share_uri: Optional[str] = None
    socks5_url: Optional[str] = None
    protocol: str = "socks5"
    raw_uri: Optional[str] = None

    @model_validator(mode="after")
    def resolve_share_link(self):
        uri = (self.share_uri or self.socks5_url or "").strip()
        if uri:
            from app.services.proxy_link_parser import parse_share_link, sanitize_label

            parsed = parse_share_link(uri)
            self.protocol = parsed.protocol
            self.host = parsed.remote_host
            self.port = parsed.remote_port
            if parsed.protocol == "socks5":
                if parsed.username:
                    self.username = parsed.username
                if parsed.password:
                    self.password = parsed.password
            else:
                self.raw_uri = parsed.raw_uri or uri
                self.username = ""
                self.password = ""
            if not self.label.strip() and parsed.label:
                self.label = sanitize_label(parsed.label)
        if not self.host.strip() and self.protocol == "socks5":
            raise ValueError("请填写主机或粘贴 socks5 / vmess / vless 链接")
        if self.protocol in ("vmess", "vless") and not self.raw_uri:
            raise ValueError("vmess / vless 需要完整分享链接")
        return self


class ProxyUpdate(BaseModel):
    host: Optional[str] = Field(None, min_length=1, max_length=255)
    port: Optional[int] = Field(None, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    label: Optional[str] = None
    enabled: Optional[bool] = None
    share_uri: Optional[str] = None
    protocol: Optional[str] = None
    raw_uri: Optional[str] = None

    @model_validator(mode="after")
    def resolve_share_link(self):
        uri = (self.share_uri or "").strip()
        if not uri:
            return self
        from app.services.proxy_link_parser import parse_share_link, sanitize_label

        parsed = parse_share_link(uri)
        self.protocol = parsed.protocol
        self.host = parsed.remote_host
        self.port = parsed.remote_port
        if parsed.protocol == "socks5":
            if parsed.username:
                self.username = parsed.username
            if parsed.password:
                self.password = parsed.password
            self.raw_uri = None
        else:
            self.raw_uri = parsed.raw_uri or uri
            self.username = ""
            self.password = ""
        if self.label is None and parsed.label:
            self.label = sanitize_label(parsed.label)
        return self


class ProxyOut(BaseModel):
    id: int
    protocol: str = "socks5"
    host: str
    port: int
    username: str
    has_password: bool
    label: str
    enabled: bool
    health_status: str
    local_socks_port: Optional[int] = None
    last_check_at: Optional[datetime] = None
    last_ok_at: Optional[datetime] = None
    last_error: Optional[str] = None
    fail_count: int
    success_count: int
    failure_rate: float = 0.0
    masked_url: str
    in_cooldown: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProxyFailureItem(BaseModel):
    id: int
    label: str = ""
    masked_url: str = ""
    health_status: str = "unknown"
    success_count: int = 0
    fail_count: int = 0
    failure_rate: float = 0.0
    in_cooldown: bool = False
    last_error: Optional[str] = None


class ProxyPoolStatsOut(BaseModel):
    total: int
    enabled: int
    healthy: int
    unhealthy: int
    unknown: int
    cooldown: int
    backend: str
    pool_enabled: bool
    fallback_url_configured: bool
    gateway_running: bool = False
    gateway_nodes: int = 0
    gateway_error: Optional[str] = None
    healthy_available: Optional[int] = None
    suggested_min_proxies: Optional[int] = None
    recommendations: list[str] = Field(default_factory=list)
    high_failure_proxies: list[ProxyFailureItem] = Field(default_factory=list)
    prune_candidate_ids: list[int] = Field(default_factory=list)


class ClusterNodeOut(BaseModel):
    node_id: str
    label: str
    online: bool
    last_seen_seconds_ago: Optional[int] = None
    roles: dict = Field(default_factory=dict)
    beat_should_run: bool = False
    beat_online: bool = False
    worker_expected: int = 0
    worker_online: int = 0
    worker_status: str = "offline"
    singbox_running: bool = False
    gateway_error: Optional[str] = None
    is_current_node: bool = False


class ClusterStatusOut(BaseModel):
    overall_status: str
    alerts: list[str] = Field(default_factory=list)
    current_node_id: str
    current_node_label: str
    nodes: list[ClusterNodeOut]
    celery: dict = Field(default_factory=dict)
    data_layer: dict = Field(default_factory=dict)
    peer_api: dict = Field(default_factory=dict)
    proxy_pool: dict = Field(default_factory=dict)
    timestamp: datetime


class ProxyPruneRequest(BaseModel):
    mode: str = "high_failure"
    ids: list[int] = Field(default_factory=list)


class ProxyPruneResult(BaseModel):
    deleted: int
    ids: list[int] = Field(default_factory=list)


class DeployUpdateRequest(BaseModel):
    confirm: bool = False
    backend_only: bool = False
    frontend_only: bool = False
    skip_git_pull: bool = False
    quick: bool = True


class DeployUpdateStatusOut(BaseModel):
    enabled: bool
    state: str = "idle"
    message: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    log_tail: str = ""
    node_label: str = ""
    script_hint: str = ""
    peer_hint: str = ""


class DeployUpdateTriggerOut(BaseModel):
    ok: bool
    message: str
    started_at: Optional[datetime] = None


VideoDetailOut.model_rebuild()
