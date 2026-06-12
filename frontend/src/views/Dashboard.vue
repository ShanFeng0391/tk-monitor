<template>
  <div class="page">
    <div class="tm-stat-grid dashboard-stat-grid">
      <div
        v-for="item in statCards"
        :key="item.label"
        class="tm-stat stat-clickable"
        :class="item.accent"
        @click="$router.push(item.to)"
      >
        <div class="tm-stat-value">{{ item.value }}</div>
        <div class="tm-stat-label">{{ item.label }}</div>
      </div>
    </div>

    <el-row :gutter="16" style="margin-top:16px">
      <el-col :span="14" :xs="24">
        <div class="tm-card">
          <div class="tm-card-header"><span class="title">热门增速排行</span></div>
          <div class="tm-card-body" style="padding-top:0">
            <el-table
              :data="growthData"
              stripe
              size="small"
              empty-text="暂无数据"
              class="clickable-table"
              @row-click="goVideo"
            >
              <el-table-column prop="drama_name" label="影视剧名称" min-width="120" show-overflow-tooltip>
                <template #default="{ row }">{{ row.drama_name || '未识别' }}</template>
              </el-table-column>
              <el-table-column prop="content_type" label="类型" width="100" show-overflow-tooltip>
                <template #default="{ row }">{{ row.content_type || '未标注' }}</template>
              </el-table-column>
              <el-table-column prop="published_at" label="发布时长" width="110">
                <template #default="{ row }">{{ formatPublishAge(row.published_at) }}</template>
              </el-table-column>
              <el-table-column prop="view_count" label="播放量" width="100">
                <template #default="{ row }">{{ formatNum(row.view_count) }}</template>
              </el-table-column>
              <el-table-column prop="avg_view_velocity" label="平均增速" width="120">
                <template #default="{ row }">
                  {{ formatVelocity(row.avg_view_velocity) }}/分
                </template>
              </el-table-column>
              <el-table-column prop="instant_view_velocity" label="瞬时增速" width="120">
                <template #default="{ row }">
                  <span v-if="row.velocity_ready" class="tm-tag daily-hot">
                    {{ formatVelocity(row.instant_view_velocity) }}/分
                  </span>
                  <span v-else class="tm-tag velocity-pending">待刷新</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-col>

      <el-col :span="10" :xs="24">
        <div class="tm-card prediction-card">
          <div class="tm-card-header">
            <span class="title">爆款素材预测</span>
            <span class="sub">近 {{ predictions.period_days || 3 }} 天</span>
          </div>
          <div class="tm-card-body prediction-body">
            <!-- 1. 类型占比 -->
            <section class="pred-section">
              <h4 class="pred-title">爆款类型分布</h4>
              <div v-if="!typeChartData.length" class="pred-empty">暂无有效类型数据</div>
              <div v-else ref="typeChartRef" class="type-pie-chart" />
            </section>

            <!-- 2. 周期推荐 -->
            <section class="pred-section">
              <h4 class="pred-title">周期爆款推荐</h4>
              <div v-if="!predictions.periodic_recommendations?.length" class="pred-empty">暂无周期推荐</div>
              <ul v-else class="rank-list">
                <li v-for="(item, idx) in predictions.periodic_recommendations" :key="item.drama_name">
                  <span class="rank-no">{{ idx + 1 }}</span>
                  <div class="rank-main">
                    <router-link
                      :to="dramaPath(item.drama_name)"
                      class="rank-name"
                    >{{ item.drama_name }}</router-link>
                    <span class="rank-sub">{{ item.reason }}</span>
                  </div>
                  <span class="rank-score">{{ item.cycle_score }}</span>
                </li>
              </ul>
            </section>

            <!-- 3. 同片多爆款 -->
            <section class="pred-section">
              <h4 class="pred-title">同片多爆款</h4>
              <div v-if="!predictions.multi_viral_dramas?.length" class="pred-empty">暂无同片多条爆款</div>
              <ul v-else class="rank-list">
                <li v-for="(item, idx) in predictions.multi_viral_dramas" :key="item.drama_name">
                  <span class="rank-no">{{ idx + 1 }}</span>
                  <div class="rank-main">
                    <router-link
                      :to="historicalViralLink({ drama_name: item.drama_name })"
                      class="rank-name"
                    >{{ item.drama_name }}</router-link>
                    <span class="rank-sub">{{ item.drama_type || '未标注' }} · {{ formatNum(item.total_views) }} 播放</span>
                  </div>
                  <span class="rank-badge">{{ item.viral_count }}条</span>
                </li>
              </ul>
            </section>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import * as echarts from 'echarts'
import api from '@/utils/api'
import { formatNum, formatVelocity, formatPublishAge } from '@/utils/format'
import { historicalViralLink, dramaPath } from '@/utils/navLinks'
import { useCategoryFilterStore } from '@/stores/categoryFilter'

const router = useRouter()
const categoryStore = useCategoryFilterStore()
const { selectedGroupId } = storeToRefs(categoryStore)

const stats = ref({})
const growthData = ref([])
const predictions = ref({
  period_days: 3,
  recent_type_shares: [],
  periodic_recommendations: [],
  multi_viral_dramas: [],
})

const typeChartRef = ref(null)
let typeChartInstance = null

const typeChartData = computed(() => predictions.value.recent_type_shares || [])

const statCards = computed(() => [
  { label: '监控博主', value: stats.value.total_creators || 0, accent: 'purple', to: '/creators' },
  { label: '爆款视频', value: stats.value.viral_count || 0, accent: 'purple', to: '/viral' },
  { label: '当日热门', value: stats.value.hot_count || 0, accent: 'orange', to: '/daily-hot' },
])

function goVideo(row) {
  if (row?.id) router.push(`/videos/${row.id}`)
}

function goHistoricalType(type) {
  if (!type) {
    router.push('/viral')
    return
  }
  router.push(historicalViralLink({ content_type: type }))
}

function renderTypeChart() {
  if (!typeChartRef.value || !typeChartData.value.length) {
    typeChartInstance?.dispose()
    typeChartInstance = null
    return
  }
  if (!typeChartInstance) {
    typeChartInstance = echarts.init(typeChartRef.value)
    typeChartInstance.on('click', (params) => {
      if (params?.name) goHistoricalType(params.name)
    })
  }
  typeChartInstance.setOption({
    color: ['#7b4397', '#9b6bb8', '#6b8cff', '#ffb07a', '#111111', '#c89de0', '#5a9bd5', '#e07979'],
    tooltip: {
      trigger: 'item',
      formatter: (p) => `${p.name}<br/>${p.value} 次 · ${p.percent}%`,
    },
    series: [{
      type: 'pie',
      radius: ['40%', '68%'],
      center: ['50%', '52%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
      label: { formatter: '{b}\n{d}%', fontSize: 11, color: '#444' },
      labelLine: { length: 10, length2: 8, smooth: true },
      data: typeChartData.value.map((item) => ({
        name: item.content_type,
        value: item.count,
      })),
    }],
  }, true)
}

async function loadDashboard() {
  const params = categoryStore.apiParams()
  const [s, g, p] = await Promise.all([
    api.get('/dashboard/stats', { params }),
    api.get('/dashboard/growth', { params }),
    api.get('/dashboard/viral-predictions', { params }),
  ])
  stats.value = s.data
  growthData.value = g.data.items || []
  predictions.value = p.data
  await nextTick()
  renderTypeChart()
}

onMounted(loadDashboard)
watch(selectedGroupId, loadDashboard)
watch(typeChartData, () => nextTick(renderTypeChart))

onUnmounted(() => {
  typeChartInstance?.dispose()
  typeChartInstance = null
})
</script>

<style scoped>
.page { animation: fadeIn 0.4s ease; }

.dashboard-stat-grid {
  grid-template-columns: repeat(3, 1fr);
}

.stat-clickable {
  cursor: pointer;
  transition: box-shadow 0.2s, transform 0.15s;
}

.stat-clickable:hover {
  box-shadow: var(--tm-shadow-sm);
  transform: translateY(-1px);
}

.clickable-table :deep(.el-table__row) {
  cursor: pointer;
}

.type-pie-chart {
  width: 100%;
  height: 220px;
  cursor: pointer;
}

@media (max-width: 960px) {
  .dashboard-stat-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .dashboard-stat-grid {
    grid-template-columns: 1fr;
  }
}

.prediction-card .sub {
  font-size: 12px;
  color: var(--tm-text-muted);
  font-weight: 500;
}

.prediction-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-height: 520px;
  overflow-y: auto;
}

.pred-section + .pred-section {
  padding-top: 16px;
  border-top: 1px solid var(--tm-border);
}

.pred-title {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 700;
  color: var(--tm-text-secondary);
}

.pred-empty {
  font-size: 12px;
  color: var(--tm-text-muted);
  padding: 8px 0;
}

.rank-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rank-list li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
}

.rank-no {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  line-height: 18px;
  text-align: center;
  border-radius: 50%;
  background: var(--tm-surface-muted);
  color: var(--tm-text-muted);
  font-size: 11px;
  font-weight: 700;
}

.rank-main {
  flex: 1;
  min-width: 0;
}

.rank-name {
  display: block;
  font-weight: 600;
  color: var(--tm-text);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rank-name:hover { color: var(--tm-purple); }

.rank-sub {
  display: block;
  margin-top: 2px;
  color: var(--tm-text-muted);
  font-size: 11px;
  line-height: 1.4;
}

.rank-score {
  flex-shrink: 0;
  font-weight: 700;
  color: var(--tm-orange);
  font-size: 11px;
}

.rank-badge {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: var(--tm-radius-pill);
  background: rgba(123, 67, 151, 0.1);
  color: var(--tm-purple);
  font-weight: 700;
  font-size: 11px;
}

.velocity-pending {
  background: rgba(144, 147, 153, 0.12);
  color: var(--tm-muted, #909399);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
