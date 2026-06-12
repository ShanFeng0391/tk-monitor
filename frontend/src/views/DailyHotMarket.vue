<template>
  <div class="page">
    <div class="tm-card hot-card">
      <div class="hot-toolbar">
        <div class="hot-summary">
          <span class="hot-count">{{ marketStats?.count ?? '—' }}</span>
          <span class="hot-label">条热门视频</span>
        </div>

        <div class="filter-fields">
          <div class="filter-item">
            <label>影视类型</label>
            <input v-model="contentType" type="text" placeholder="筛选类型" @keyup.enter="reload" />
          </div>
          <div class="filter-item filter-narrow">
            <label>最低瞬时增速</label>
            <input v-model.number="minGrowth" type="number" placeholder="10" @keyup.enter="reload" />
          </div>
        </div>

        <button class="tm-btn-primary" @click="reload">刷新</button>
      </div>

      <div class="card-content">
        <VideoGrid
          :videos="videos"
          :loading="loading"
          :total="total"
          :page="page"
          :page-size="pageSize"
          :show-category="false"
          :show-title="false"
          :show-growth="false"
          :hide-hot-date="true"
          empty-text="当日暂无优质热门视频"
          @page-change="onPageChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import api from '@/utils/api'
import VideoGrid from '@/components/VideoGrid.vue'
import { useCategoryFilterStore } from '@/stores/categoryFilter'

const route = useRoute()
const router = useRouter()
const categoryStore = useCategoryFilterStore()
const { selectedGroupId } = storeToRefs(categoryStore)

const videos = ref([])
const marketStats = ref(null)
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const contentType = ref('')
const minGrowth = ref(null)

function syncQuery() {
  const q = { page: String(page.value) }
  if (contentType.value) q.content_type = contentType.value
  if (minGrowth.value) q.min_growth = String(minGrowth.value)
  router.replace({ query: q })
}

function readQuery() {
  const q = route.query
  if (q.content_type) contentType.value = q.content_type
  if (q.min_growth) minGrowth.value = Number(q.min_growth)
  if (q.page) page.value = Number(q.page) || 1
}

async function loadStats() {
  const { data } = await api.get('/core/daily-hot/stats', { params: categoryStore.apiParams() })
  marketStats.value = data
}

async function loadVideos() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize, ...categoryStore.apiParams() }
    if (contentType.value) params.content_type = contentType.value
    if (minGrowth.value) params.min_growth = minGrowth.value
    const { data } = await api.get('/core/daily-hot', { params })
    videos.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  syncQuery()
  loadStats()
  loadVideos()
}

function onPageChange(p) {
  page.value = p
  syncQuery()
  loadVideos()
}

onMounted(() => {
  readQuery()
  reload()
})

watch(selectedGroupId, () => {
  page.value = 1
  reload()
})
</script>

<style scoped>
.page { animation: fadeIn 0.4s ease; }

.hot-toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  padding: 20px 24px;
  border-bottom: 1px solid var(--tm-border);
  background: linear-gradient(180deg, rgba(255, 176, 122, 0.08) 0%, transparent 100%);
}

.hot-summary {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 120px;
}

.hot-count {
  font-size: 36px;
  font-weight: 800;
  line-height: 1;
  color: var(--tm-orange);
  letter-spacing: -0.03em;
}

.hot-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--tm-text-secondary);
}

.filter-fields {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 16px 20px;
  flex: 1;
  justify-content: center;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-item label {
  font-size: 12px;
  font-weight: 500;
  color: var(--tm-text-muted);
}

.filter-item input {
  width: 160px;
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

.filter-item input:focus {
  border-color: var(--tm-text);
}

.filter-narrow input {
  width: 120px;
}

.card-content {
  padding: 16px 24px 24px;
}

@media (max-width: 768px) {
  .hot-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .hot-summary {
    justify-content: center;
    padding-bottom: 4px;
  }

  .filter-fields {
    justify-content: stretch;
  }

  .filter-item input {
    width: 100%;
  }

  .filter-narrow input {
    width: 100%;
  }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
