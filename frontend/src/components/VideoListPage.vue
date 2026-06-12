<template>
  <div class="page">
    <div class="tm-card">
      <div class="tm-card-header">
        <span class="title">{{ title }}</span>
        <div v-if="filterHint" class="filter-hint">
          <span>{{ filterHint }}</span>
          <button class="tm-btn-ghost sm" @click="clearFilters">清除筛选</button>
        </div>
        <button class="tm-btn-ghost" @click="exportData">导出 CSV</button>
      </div>
      <div class="tm-card-body">
        <VideoGrid
          :videos="videos"
          :loading="loading"
          :total="total"
          :page="page"
          :page-size="pageSize"
          :empty-text="emptyText"
          @page-change="onPageChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/utils/api'
import VideoGrid from '@/components/VideoGrid.vue'

const props = defineProps({
  category: { type: String, default: null },
  title: { type: String, default: '视频列表' },
  sortBy: { type: String, default: 'published_at' },
  emptyText: { type: String, default: '暂无视频数据' },
})

const route = useRoute()
const router = useRouter()

const videos = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const creatorId = ref(null)
const dramaName = ref('')

const filterHint = computed(() => {
  const parts = []
  if (dramaName.value) parts.push(`影视剧：${dramaName.value}`)
  if (creatorId.value) parts.push(`博主 ID：${creatorId.value}`)
  return parts.length ? parts.join(' · ') : ''
})

function readQuery() {
  creatorId.value = route.query.creator_id ? Number(route.query.creator_id) : null
  dramaName.value = route.query.drama_name || ''
  if (route.query.page) page.value = Number(route.query.page) || 1
}

function syncQuery() {
  const q = { page: String(page.value) }
  if (route.query.tab) q.tab = route.query.tab
  if (creatorId.value) q.creator_id = String(creatorId.value)
  if (dramaName.value) q.drama_name = dramaName.value
  router.replace({ query: q })
}

async function loadVideos() {
  loading.value = true
  try {
    const endpoint = props.category === 'viral' ? '/videos/viral'
      : props.category === 'hot' ? '/videos/hot' : '/videos'
    const params = { page: page.value, page_size: pageSize, sort_by: props.sortBy }
    if (creatorId.value) params.creator_id = creatorId.value
    if (dramaName.value) params.drama_name = dramaName.value
    const { data } = await api.get(endpoint, { params })
    videos.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onPageChange(p) {
  page.value = p
  syncQuery()
  loadVideos()
}

function clearFilters() {
  creatorId.value = null
  dramaName.value = ''
  page.value = 1
  const q = {}
  if (route.query.tab) q.tab = route.query.tab
  router.replace({ query: q })
  loadVideos()
}

async function exportData() {
  window.open('/api/v1/export/videos?format=csv', '_blank')
}

onMounted(() => {
  readQuery()
  loadVideos()
})

watch(() => route.query, () => {
  readQuery()
  loadVideos()
})

watch(() => props.category, () => {
  page.value = 1
  loadVideos()
})
</script>

<style scoped>
.filter-hint {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: 12px;
  font-size: 12px;
  color: var(--tm-text-muted);
}

.tm-btn-ghost.sm {
  height: 28px;
  padding: 0 10px;
  font-size: 12px;
}
</style>
