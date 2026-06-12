<template>
  <div class="page page--fill">
    <div class="tm-card viral-card">
      <div class="viral-toolbar">
        <div class="filter-fields">
          <div class="filter-item filter-keyword">
            <label>关键词</label>
            <input v-model="filters.keyword" placeholder="模糊搜索影视剧名或类型" @keyup.enter="search" />
          </div>
          <div class="filter-item filter-narrow">
            <label>最低播放</label>
            <input v-model.number="filters.min_views" type="number" placeholder="100000" @keyup.enter="search" />
          </div>
          <div class="filter-item filter-narrow filter-range">
            <label>博主粉丝区间</label>
            <div class="range-box">
              <div class="range-inner">
                <div class="range-cell">
                  <input
                    v-model.number="filters.min_followers_wan"
                    class="range-field"
                    type="number"
                    min="0"
                    step="0.1"
                    placeholder="最小"
                    @keyup.enter="search"
                  />
                  <span class="range-unit">万</span>
                </div>
                <span class="range-sep">—</span>
                <div class="range-cell">
                  <input
                    v-model.number="filters.max_followers_wan"
                    class="range-field"
                    type="number"
                    min="0"
                    step="0.1"
                    placeholder="最大"
                    @keyup.enter="search"
                  />
                  <span class="range-unit">万</span>
                </div>
              </div>
            </div>
          </div>
          <div class="filter-item filter-narrow">
            <label>排序</label>
            <select v-model="filters.sort_by">
              <option value="published_at">发布时间</option>
              <option value="view_count">播放量</option>
            </select>
          </div>
          <div v-if="creatorFilterLabel" class="filter-item creator-chip-item">
            <label>当前博主</label>
            <div class="creator-chip">
              <span>{{ creatorFilterLabel }}</span>
              <button type="button" class="creator-chip-clear" title="清除博主筛选" @click="clearCreatorFilter">×</button>
            </div>
          </div>
        </div>

        <div class="toolbar-actions">
          <button class="tm-btn-primary" @click="search">搜索</button>
          <button class="tm-btn-ghost" @click="reset">重置</button>
        </div>
      </div>

      <div class="card-content">
        <VideoGrid
          :videos="videos"
          :loading="loading"
          :total="total"
          :page="page"
          :page-size="pageSize"
          :columns="3"
          :show-category="false"
          :show-title="false"
          :show-growth="false"
          empty-text="暂无匹配的爆款视频，请调整筛选条件"
          @page-change="onPageChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import api from '@/utils/api'
import VideoGrid from '@/components/VideoGrid.vue'
import { useGridPageSize } from '@/composables/useGridPageSize'
import { useCategoryFilterStore } from '@/stores/categoryFilter'

const route = useRoute()
const router = useRouter()
const categoryStore = useCategoryFilterStore()
const { selectedGroupId } = storeToRefs(categoryStore)

const videos = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = useGridPageSize()
const total = ref(0)

const WAN = 10000

const filters = ref({
  keyword: '',
  min_views: null,
  min_followers_wan: null,
  max_followers_wan: null,
  sort_by: 'published_at',
})

function toFollowerCount(wan) {
  if (wan == null || wan === '' || Number.isNaN(Number(wan))) return null
  return Math.round(Number(wan) * WAN)
}

function fromFollowerQuery(raw) {
  const v = Number(raw)
  if (!v || Number.isNaN(v)) return null
  return v >= 1000 ? v / WAN : v
}

const creatorFilter = ref({
  id: null,
  username: '',
})

const creatorFilterLabel = computed(() => {
  if (creatorFilter.value.username) return `@${creatorFilter.value.username.replace(/^@/, '')}`
  if (creatorFilter.value.id) return `ID ${creatorFilter.value.id}`
  return ''
})

function syncQuery() {
  const q = { page: String(page.value), sort_by: filters.value.sort_by }
  if (filters.value.keyword) q.keyword = filters.value.keyword
  if (filters.value.min_views) q.min_views = String(filters.value.min_views)
  if (filters.value.min_followers_wan != null && filters.value.min_followers_wan !== '') {
    q.min_followers = String(filters.value.min_followers_wan)
  }
  if (filters.value.max_followers_wan != null && filters.value.max_followers_wan !== '') {
    q.max_followers = String(filters.value.max_followers_wan)
  }
  if (creatorFilter.value.id) q.creator_id = String(creatorFilter.value.id)
  if (creatorFilter.value.username) q.creator_username = creatorFilter.value.username.replace(/^@/, '')
  router.replace({ query: q })
}

function readQuery() {
  const q = route.query
  if (q.page) page.value = Number(q.page) || 1
  if (q.keyword) {
    filters.value.keyword = String(q.keyword)
  } else if (q.drama_name || q.content_type) {
    filters.value.keyword = String(q.drama_name || q.content_type)
  } else {
    filters.value.keyword = ''
  }
  if (q.min_views) filters.value.min_views = Number(q.min_views)
  else filters.value.min_views = null
  if (q.min_followers) filters.value.min_followers_wan = fromFollowerQuery(q.min_followers)
  else filters.value.min_followers_wan = null
  if (q.max_followers) filters.value.max_followers_wan = fromFollowerQuery(q.max_followers)
  else filters.value.max_followers_wan = null
  if (q.sort_by) filters.value.sort_by = q.sort_by
  creatorFilter.value = {
    id: q.creator_id ? Number(q.creator_id) : null,
    username: q.creator_username ? String(q.creator_username).replace(/^@/, '') : '',
  }
}

async function loadVideos() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
      sort_by: filters.value.sort_by,
    }
    if (filters.value.keyword) params.keyword = filters.value.keyword.trim()
    if (filters.value.min_views) params.min_views = filters.value.min_views
    const minFollowers = toFollowerCount(filters.value.min_followers_wan)
    const maxFollowers = toFollowerCount(filters.value.max_followers_wan)
    if (minFollowers != null) params.min_followers = minFollowers
    if (maxFollowers != null) params.max_followers = maxFollowers
    if (creatorFilter.value.id) params.creator_id = creatorFilter.value.id
    if (creatorFilter.value.username) params.creator_username = creatorFilter.value.username
    Object.assign(params, categoryStore.apiParams())

    const { data } = await api.get('/core/historical-viral', { params })
    videos.value = data.items
    total.value = data.total

    if (creatorFilter.value.id && videos.value.length && !creatorFilter.value.username) {
      const name = videos.value[0]?.creator_username
      if (name) creatorFilter.value.username = name.replace(/^@/, '')
    }
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  syncQuery()
  loadVideos()
}

function reset() {
  filters.value = {
    keyword: '',
    min_views: null,
    min_followers_wan: null,
    max_followers_wan: null,
    sort_by: 'published_at',
  }
  creatorFilter.value = { id: null, username: '' }
  search()
}

function clearCreatorFilter() {
  creatorFilter.value = { id: null, username: '' }
  page.value = 1
  syncQuery()
  loadVideos()
}

function onPageChange(p) {
  page.value = p
  syncQuery()
  loadVideos()
}

onMounted(() => {
  readQuery()
  loadVideos()
})

watch(() => route.query, () => {
  readQuery()
  loadVideos()
})

watch(selectedGroupId, () => {
  page.value = 1
  loadVideos()
})

watch(pageSize, () => {
  loadVideos()
})
</script>

<style scoped>
.page { animation: fadeIn 0.4s ease; }

.page--fill {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.viral-card {
  overflow: hidden;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.viral-toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 14px 16px;
  flex-wrap: wrap;
  padding: 16px 20px;
  border-bottom: 1px solid var(--tm-border);
  background: linear-gradient(180deg, rgba(123, 67, 151, 0.06) 0%, transparent 100%);
  flex-shrink: 0;
}

.filter-fields {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px 16px;
  flex: 1;
  min-width: 280px;
}

.filter-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.filter-item label {
  width: 100%;
  font-size: 12px;
  font-weight: 500;
  color: var(--tm-text-muted);
  text-align: center;
}

.filter-item input:not(.range-field),
.filter-item select {
  width: 148px;
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--tm-border);
  border-radius: 10px;
  background: var(--tm-surface);
  font-size: 13px;
  color: var(--tm-text);
  outline: none;
  transition: border-color 0.2s;
}

.filter-item input:not(.range-field):focus,
.filter-item select:focus {
  border-color: var(--tm-purple);
}

.filter-item.filter-keyword input {
  width: 220px;
}

.filter-item.filter-range .range-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 132px;
  height: 36px;
  padding: 0 4px;
  border: 1px solid var(--tm-border);
  border-radius: 10px;
  background: var(--tm-surface);
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.filter-item.filter-range .range-box:focus-within {
  border-color: var(--tm-purple);
}

.filter-item.filter-range .range-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  gap: 2px;
}

.filter-item.filter-range .range-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  min-width: 0;
  height: 100%;
}

.filter-item.filter-range .range-field {
  width: 30px;
  min-width: 0;
  height: 100%;
  padding: 0;
  margin: 0;
  border: none;
  border-radius: 0;
  background: transparent;
  font-family: inherit;
  font-size: 12px;
  line-height: 34px;
  text-align: right;
  outline: none;
  -moz-appearance: textfield;
  appearance: textfield;
}

.filter-item.filter-range .range-field::-webkit-outer-spin-button,
.filter-item.filter-range .range-field::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.filter-item.filter-range .range-field::placeholder {
  font-size: 11px;
  color: var(--tm-text-muted);
  text-align: center;
}

.filter-item.filter-range .range-unit {
  font-size: 12px;
  line-height: 1;
  color: var(--tm-text-secondary);
  flex-shrink: 0;
  transform: translateY(0.5px);
}

.filter-item.filter-range .range-sep {
  flex-shrink: 0;
  color: var(--tm-text-muted);
  font-size: 11px;
  line-height: 1;
  padding: 0 1px;
}

.filter-item.filter-narrow input,
.filter-item.filter-narrow select {
  width: 120px;
}

.creator-chip-item {
  min-width: 140px;
  align-items: center;
}

.creator-chip-item .creator-chip {
  width: 100%;
  justify-content: center;
}

.creator-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 8px 0 12px;
  border: 1px solid rgba(0, 47, 167, 0.22);
  border-radius: 10px;
  background: rgba(0, 47, 167, 0.05);
  color: var(--tm-blue);
  font-size: 13px;
  font-weight: 600;
}

.creator-chip-clear {
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--tm-blue);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}

.creator-chip-clear:hover {
  background: rgba(0, 47, 167, 0.1);
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.card-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 12px 14px 10px;
}

.card-content :deep(.video-grid-wrap.cols-3) {
  flex: 1;
  min-height: 0;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 960px) {
  .viral-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar-actions {
    justify-content: flex-end;
  }
}
</style>
