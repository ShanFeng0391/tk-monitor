<template>
  <div class="video-grid-wrap" :class="{ 'cols-3': columns === 3 }">
    <div v-if="loading" class="loading-state">
      <span class="spinner"></span>
      <span>加载中...</span>
    </div>

    <div v-else-if="!videos.length" class="empty-state">
      <div class="empty-icon">◎</div>
      <p>{{ emptyText }}</p>
    </div>

    <div v-else class="video-grid">
      <article
        v-for="video in videos"
        :key="video.id"
        class="video-item"
        @click="$router.push(`/videos/${video.id}`)"
      >
        <div class="cover-wrap">
          <img :src="video.cover_url || placeholder" :alt="video.title" loading="lazy" />
          <span v-if="video.traffic_grade" class="grade">{{ video.traffic_grade }}</span>
        </div>
        <div class="info">
          <div class="info-top">
            <span v-if="showCategory" class="tm-tag sm" :class="catClass(video)">
              {{ catLabel(video) }}
            </span>
            <span v-if="video.content_type" class="type-inline">{{ video.content_type }}</span>
          </div>
          <h3 v-if="showTitle">{{ video.title || '无标题' }}</h3>
          <p v-if="video.drama_name && linkDrama" class="drama-line">
            <span class="drama-link" @click.stop="goDrama(video.drama_name)">{{ video.drama_name }}</span>
          </p>
          <p v-else-if="video.drama_name" class="drama-line muted">{{ video.drama_name }}</p>
          <p v-if="linkCreator && video.creator_username" class="creator">
            <span class="creator-link" @click.stop="goCreator(video)">@{{ video.creator_username }}</span>
          </p>
          <p v-else class="creator muted">@{{ video.creator_username || 'unknown' }}</p>
          <div class="meta">
            <span>{{ video.creator_follower_count ? formatNum(video.creator_follower_count) : '—' }} 粉丝</span>
            <span>{{ formatNum(video.view_count) }} 播放</span>
            <span>{{ formatNum(video.like_count) }} 赞</span>
            <span v-if="showGrowth && video.instant_view_velocity != null" class="growth">
              瞬时 {{ formatVelocity(video.instant_view_velocity) }}/分
            </span>
            <span v-if="showGrowth && video.avg_view_velocity != null" class="avg-growth">
              平均 {{ formatVelocity(video.avg_view_velocity) }}/分
            </span>
            <span v-if="metaLabel(video)" class="meta-extra">{{ metaLabel(video) }}</span>
          </div>
        </div>
      </article>
    </div>

    <div
      v-if="!loading && videos.length && (columns === 3 || total > pageSize)"
      class="pager"
      :class="{ 'pager-bar': columns === 3 }"
    >
      <span v-if="columns === 3" class="pager-total">共 {{ total }} 条</span>
      <el-pagination
        v-if="total > pageSize"
        background
        :small="columns === 3"
        :layout="columns === 3 ? 'prev, pager, next' : 'prev, pager, next, total'"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="$emit('page-change', $event)"
      />
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { formatNum, formatVelocity, categoryLabel, categoryClass, formatDateYmd } from '@/utils/format'
import { dramaPath, creatorVideosLink } from '@/utils/navLinks'

const props = defineProps({
  videos: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 20 },
  emptyText: { type: String, default: '暂无数据' },
  showCategory: { type: Boolean, default: true },
  showTitle: { type: Boolean, default: true },
  showGrowth: { type: Boolean, default: true },
  linkDrama: { type: Boolean, default: true },
  linkCreator: { type: Boolean, default: true },
  hideHotDate: { type: Boolean, default: false },
  metaKey: { type: String, default: '' },
  columns: { type: Number, default: 0 },
})

defineEmits(['page-change'])

const router = useRouter()
const placeholder = 'https://via.placeholder.com/120x160/f3f3f3/888?text=Video'

function catLabel(video) {
  return categoryLabel(video.category, video)
}

function catClass(video) {
  return categoryClass(video.category, video)
}

function goDrama(name) {
  router.push(dramaPath(name))
}

function goCreator(video) {
  router.push(creatorVideosLink(video.creator_id, video.creator_username))
}

function metaLabel(video) {
  if (!video) return ''
  if (video.hot_date && !props.hideHotDate) return `${video.hot_date} 热门`
  if (video.published_at) return formatDateYmd(video.published_at)
  return ''
}
</script>

<style scoped>
.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 10px;
}

.video-item {
  display: flex;
  align-items: stretch;
  gap: 12px;
  padding: 10px 12px;
  background: var(--tm-surface);
  border-radius: 12px;
  cursor: pointer;
  border: 1px solid rgba(0, 0, 0, 0.05);
  transition: border-color 0.2s, box-shadow 0.2s;
  min-height: 88px;
}

.video-item:hover {
  border-color: rgba(0, 0, 0, 0.12);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.cover-wrap {
  position: relative;
  width: 56px;
  height: 74px;
  flex-shrink: 0;
  border-radius: 8px;
  overflow: hidden;
  background: var(--tm-surface-muted);
}

.cover-wrap img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.grade {
  position: absolute;
  top: 4px;
  right: 4px;
  background: rgba(17, 17, 17, 0.85);
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: var(--tm-radius-pill);
  line-height: 1.4;
}

.info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 3px;
}

.info-top {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.tm-tag.sm {
  padding: 1px 7px;
  font-size: 10px;
}

.type-inline {
  font-size: 10px;
  color: var(--tm-blue);
  font-weight: 600;
}

.info h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.drama-line {
  margin: 0;
  font-size: 11px;
  line-height: 1.35;
}

.drama-link {
  display: inline-block;
  max-width: 100%;
  font-weight: 600;
  color: var(--tm-purple);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
  cursor: pointer;
}

.drama-link:hover { text-decoration: underline; }

.drama-line.muted {
  font-weight: 600;
  color: var(--tm-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.creator {
  margin: 0;
  font-size: 11px;
  line-height: 1.35;
}

.creator-link {
  display: inline-block;
  max-width: 100%;
  color: var(--tm-blue);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
  cursor: pointer;
}

.creator-link:hover { text-decoration: underline; }

.creator.muted {
  color: var(--tm-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
  color: var(--tm-text-secondary);
  margin-top: 2px;
}

.meta .growth {
  color: var(--tm-orange);
  font-weight: 600;
}

.meta .avg-growth {
  color: var(--tm-purple);
  font-weight: 600;
}

.meta-extra {
  color: var(--tm-text-muted);
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 20px;
  color: var(--tm-text-muted);
}

.empty-icon {
  font-size: 32px;
  margin-bottom: 10px;
  color: var(--tm-purple);
}

.spinner {
  width: 28px;
  height: 28px;
  border: 2px solid #ddd;
  border-top-color: var(--tm-black);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  margin-bottom: 12px;
}

.pager {
  display: flex;
  justify-content: center;
  margin-top: 20px;
  flex-shrink: 0;
}

.pager-bar {
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
  padding: 10px 2px 2px;
  border-top: 1px solid var(--tm-border);
}

.pager-total {
  font-size: 12px;
  color: var(--tm-text-muted);
  font-weight: 500;
  flex-shrink: 0;
}

.pager-bar :deep(.el-pagination) {
  --el-pagination-button-height: 28px;
  --el-pagination-font-size: 12px;
}

.pager-bar :deep(.el-pagination.is-background .el-pager li) {
  min-width: 28px;
  height: 28px;
  line-height: 28px;
}

.video-grid-wrap.cols-3 .pager {
  flex-shrink: 0;
  padding-top: 10px;
}

.video-grid-wrap.cols-3 .loading-state,
.video-grid-wrap.cols-3 .empty-state {
  flex: 1;
  min-height: 0;
  padding: 32px 20px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 640px) {
  .video-grid {
    grid-template-columns: 1fr;
  }
}

/* 固定 3 列：爆款视频 */
.video-grid-wrap.cols-3 {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.video-grid-wrap.cols-3 .video-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  flex: 1;
  min-height: 0;
  overflow: auto;
  align-content: start;
}

.video-grid-wrap.cols-3 .video-item {
  min-width: 0;
  padding: 8px 10px;
  gap: 9px;
  min-height: 80px;
}

.video-grid-wrap.cols-3 .cover-wrap {
  width: 52px;
  height: 68px;
}

.video-grid-wrap.cols-3 .info {
  gap: 2px;
  overflow: hidden;
}

.video-grid-wrap.cols-3 .type-inline {
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.video-grid-wrap.cols-3 .drama-line,
.video-grid-wrap.cols-3 .creator {
  font-size: 11px;
}

.video-grid-wrap.cols-3 .info-top {
  flex-wrap: nowrap;
  overflow: hidden;
}

.video-grid-wrap.cols-3 .meta {
  flex-wrap: nowrap;
  gap: 5px 10px;
  font-size: 10px;
  overflow: hidden;
  margin-top: 0;
}

.video-grid-wrap.cols-3 .meta > span {
  white-space: nowrap;
  flex-shrink: 0;
}

.video-grid-wrap.cols-3 .meta .meta-extra {
  flex-shrink: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 1180px) {
  .video-grid-wrap.cols-3 .video-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .video-grid-wrap.cols-3 .video-grid {
    grid-template-columns: 1fr;
  }
}
</style>
