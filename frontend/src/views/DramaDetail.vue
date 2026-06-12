<template>
  <div v-loading="loading" class="page drama-detail-page">
    <template v-if="drama">
      <el-row :gutter="16" class="detail-panels">
        <el-col :xs="24" :lg="10">
          <div class="tm-card panel-card">
            <div class="tm-card-header">
              <span class="title">{{ panelDramaName }}</span>
            </div>
            <div class="tm-card-body side-body">
              <template v-if="hasValidRecognition">
                <div class="drama-layout">
                  <div class="tmdb-side">
                    <img
                      v-if="tmdbPoster"
                      :src="tmdbPoster"
                      class="tmdb-poster"
                      alt="影视剧海报"
                    />
                    <div v-else class="poster-placeholder">暂无海报</div>
                    <a
                      v-if="recognition?.tmdb_url"
                      :href="recognition.tmdb_url"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="tmdb-link"
                    >{{ metadataLinkLabel }} ↗</a>
                  </div>

                  <div class="drama-main">
                    <el-descriptions :column="1" border size="small" class="compact-desc drama-desc">
                      <el-descriptions-item label="分类">{{ displayCategory }}</el-descriptions-item>
                      <el-descriptions-item label="演员">{{ recognition.actors || '—' }}</el-descriptions-item>
                      <el-descriptions-item
                        v-if="recognition.analysis_reason"
                        label="备注"
                        class-name="desc-notes"
                      >
                        <div class="info-notes">
                          <p v-for="(line, idx) in noteLines" :key="idx" class="note-line">{{ line }}</p>
                        </div>
                      </el-descriptions-item>
                    </el-descriptions>

                    <div class="cross-links">
                      <router-link :to="historicalViralLink({ drama_name: recognition.drama_name })">爆款视频</router-link>
                      <router-link :to="videosLink({ drama_name: recognition.drama_name })">相关视频</router-link>
                    </div>
                  </div>
                </div>
              </template>
              <div v-else class="empty-rec">
                <p>暂无该影视剧的标注信息</p>
                <p class="hint">可在视频详情页完成人工标注后查看</p>
              </div>
            </div>
          </div>
        </el-col>

        <el-col :xs="24" :lg="14">
          <div class="tm-card panel-card chart-card">
            <div class="tm-card-header">
              <span class="title">同剧视频分布</span>
              <span v-if="scatterData?.drama_name" class="chart-sub">{{ scatterData.drama_name }}</span>
            </div>
            <div class="tm-card-body chart-body">
              <div v-if="scatterEmpty" class="empty-scatter">
                <p>{{ scatterEmpty }}</p>
              </div>
              <div v-else ref="chartRef" class="scatter-chart"></div>
            </div>
          </div>
        </el-col>
      </el-row>
    </template>

    <div class="tm-card videos-card">
      <div class="tm-card-header">
        <span class="title">相关视频</span>
        <span class="count">{{ videoTotal }} 条</span>
      </div>
      <div class="tm-card-body videos-body">
        <VideoGrid
          :videos="videos"
          :loading="videosLoading"
          :total="videoTotal"
          :page="videoPage"
          :page-size="relatedPageSize"
          :columns="3"
          :show-category="false"
          :show-title="false"
          :show-growth="false"
          :link-drama="false"
          empty-text="暂无关联视频"
          @page-change="onVideoPageChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as echarts from 'echarts'
import api from '@/utils/api'
import { formatNum } from '@/utils/format'
import VideoGrid from '@/components/VideoGrid.vue'
import { historicalViralLink, videosLink } from '@/utils/navLinks'

const route = useRoute()
const router = useRouter()

const drama = ref(null)
const recognition = ref(null)
const videos = ref([])
const videosLoading = ref(false)
const videoPage = ref(1)
const videoTotal = ref(0)
const relatedPageSize = 3
const dramaNameKey = ref('')
const loading = ref(false)
const chartRef = ref(null)
const scatterData = ref(null)
let chartInstance = null

const hasValidRecognition = computed(() =>
  recognition.value && !isInvalidDrama(recognition.value.drama_name),
)

const tmdbPoster = computed(() => recognition.value?.tmdb_poster_url || '')

const metadataLinkLabel = computed(() => {
  if (recognition.value?.metadata_source === 'bangumi') return 'Bangumi'
  if (recognition.value?.tmdb_url?.includes('bgm.tv')) return 'Bangumi'
  return 'TMDB'
})

const displayCategory = computed(() => {
  if (hasValidRecognition.value && recognition.value?.drama_type) {
    return recognition.value.drama_type
  }
  if (drama.value?.drama_type) return drama.value.drama_type
  return '—'
})

const panelDramaName = computed(() =>
  recognition.value?.drama_name || drama.value?.drama_name || '影视剧详情',
)

const noteLines = computed(() => {
  const text = recognition.value?.analysis_reason
  if (!text) return []
  return text.split(/[；;]/).map((s) => s.trim()).filter(Boolean)
})

const scatterEmpty = computed(() => {
  if (!hasValidRecognition.value) {
    return '暂无标注信息，无法展示同剧视频分布'
  }
  if (scatterData.value && !scatterData.value.points?.length) {
    return '暂无同剧关联视频数据'
  }
  return ''
})

function isInvalidDrama(name) {
  return !name || ['未知', '非影视内容'].includes(name)
}

function scatterTimeExtent(points) {
  const times = points
    .map((p) => (p.published_at ? new Date(p.published_at).getTime() : NaN))
    .filter((t) => Number.isFinite(t))
  if (!times.length) return null
  const min = Math.min(...times)
  const max = Math.max(...times)
  const span = max - min
  const pad = span > 0 ? Math.max(span * 0.06, 6 * 3600000) : 2 * 86400000
  return {
    viewMin: min - pad,
    viewMax: max + pad,
    axisMin: min - pad * 2,
    axisMax: max + pad * 2,
  }
}

function renderScatterChart(data) {
  if (!chartRef.value || !data.points?.length) return
  chartInstance = echarts.init(chartRef.value)

  const others = data.points.filter(p => !p.is_current)
  const current = data.points.filter(p => p.is_current)
  const timeExtent = scatterTimeExtent(data.points)

  const makeSeriesData = (points) => points.map(p => ({
    value: [p.published_at, p.view_count],
    title: p.title,
    creator: p.creator_username,
    videoId: p.video_id,
  }))

  chartInstance.setOption({
    color: ['#7b4397', '#111'],
    tooltip: {
      trigger: 'item',
      formatter(params) {
        const d = params.data
        const date = new Date(d.value[0]).toLocaleString()
        return [
          d.title || '无标题',
          `@${d.creator || '-'}`,
          `发布：${date}`,
          `播放：${formatNum(d.value[1])}`,
        ].join('<br/>')
      },
    },
    legend: {
      data: ['同剧视频', '当前视频'],
      top: 0,
      itemWidth: 8,
      itemHeight: 8,
      itemGap: 16,
      textStyle: { fontSize: 12 },
    },
    grid: { left: 56, right: 24, top: 40, bottom: 48 },
    dataZoom: timeExtent ? [{
      type: 'inside',
      xAxisIndex: 0,
      filterMode: 'none',
      zoomOnMouseWheel: true,
      moveOnMouseMove: true,
      moveOnMouseWheel: false,
      startValue: timeExtent.viewMin,
      endValue: timeExtent.viewMax,
      minValueSpan: 3600000,
    }] : [],
    xAxis: {
      type: 'time',
      name: '发布时间',
      min: timeExtent?.axisMin,
      max: timeExtent?.axisMax,
      axisLabel: {
        formatter: (v) => {
          const d = new Date(v)
          return `${d.getMonth() + 1}/${d.getDate()}`
        },
      },
    },
    yAxis: {
      type: 'value',
      name: '播放量',
      axisLabel: { formatter: (v) => formatNum(v) },
    },
    series: [
      {
        name: '同剧视频',
        type: 'scatter',
        symbolSize: 6,
        data: makeSeriesData(others),
        itemStyle: { color: '#7b4397', opacity: 0.75 },
      },
      {
        name: '当前视频',
        type: 'scatter',
        symbolSize: 8,
        data: makeSeriesData(current),
        itemStyle: { color: '#111', borderColor: '#7b4397', borderWidth: 1.5 },
        z: 10,
      },
    ],
  })

  chartInstance.on('click', (params) => {
    const id = params.data?.videoId
    if (id) router.push(`/videos/${id}`)
  })

  requestAnimationFrame(() => {
    chartInstance?.resize()
    setTimeout(() => chartInstance?.resize(), 120)
  })
}

async function loadDramaScatter(name) {
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  try {
    const { data } = await api.get(`/dramas/${encodeURIComponent(name)}/scatter`)
    scatterData.value = data
  } catch {
    scatterData.value = { drama_name: name, points: [] }
  }
  await nextTick()
  if (scatterData.value?.points?.length) {
    renderScatterChart(scatterData.value)
  }
}

function handleChartResize() {
  chartInstance?.resize()
}

async function loadRelatedVideos() {
  if (!dramaNameKey.value) return
  videosLoading.value = true
  try {
    const { data } = await api.get('/videos', {
      params: {
        drama_name: dramaNameKey.value,
        page: videoPage.value,
        page_size: relatedPageSize,
        sort_by: 'published_at',
      },
    })
    videos.value = data.items || []
    videoTotal.value = data.total || 0
  } finally {
    videosLoading.value = false
  }
}

function onVideoPageChange(p) {
  videoPage.value = p
  loadRelatedVideos()
}

onMounted(async () => {
  loading.value = true
  window.addEventListener('resize', handleChartResize)
  try {
    const name = decodeURIComponent(route.params.name)
    dramaNameKey.value = name
    const { data } = await api.get(`/dramas/${encodeURIComponent(name)}`)
    drama.value = data
    recognition.value = data.recognition
    await Promise.all([loadRelatedVideos(), loadDramaScatter(name)])
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', handleChartResize)
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
})
</script>

<style scoped>
.page { animation: fadeIn 0.4s ease; }

.detail-panels {
  align-items: stretch;
}

.detail-panels :deep(.el-col) {
  display: flex;
  min-height: 0;
}

.panel-card {
  flex: 1;
  width: 100%;
  display: flex;
  flex-direction: column;
  min-height: 380px;
}

.panel-card .side-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  justify-content: center;
}

.panel-card .chart-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.side-card .tm-card-body.side-body,
.panel-card .tm-card-body.side-body {
  padding: 12px 14px 14px;
}

.drama-layout {
  display: flex;
  gap: 14px;
  align-items: center;
  flex: 0 0 auto;
  width: 100%;
}

.tmdb-side {
  flex-shrink: 0;
  width: 92px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.tmdb-poster {
  width: 92px;
  height: 138px;
  object-fit: cover;
  border-radius: var(--tm-radius-md);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
  background: #f0f0f0;
}

.poster-placeholder {
  width: 92px;
  height: 138px;
  border-radius: var(--tm-radius-md);
  background: #f5f5f7;
  border: 1px dashed var(--tm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--tm-text-muted);
  font-size: 11px;
}

.tmdb-link {
  display: inline-block;
  margin-top: 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--tm-blue);
  text-decoration: none;
}

.tmdb-link:hover { text-decoration: underline; }

.drama-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.drama-desc {
  flex: 0 0 auto;
}

.drama-desc :deep(.el-descriptions__label),
.drama-desc :deep(.el-descriptions__cell.el-descriptions__label) {
  width: 52px;
  min-width: 52px;
  font-size: 11px;
  text-align: center !important;
  vertical-align: middle !important;
  white-space: nowrap;
  padding: 0 4px !important;
}

.drama-desc :deep(.el-descriptions__content),
.drama-desc :deep(.el-descriptions__cell.el-descriptions__content) {
  font-size: 12px;
  vertical-align: middle !important;
}

.drama-desc :deep(.el-descriptions__label .el-descriptions__label-content) {
  justify-content: center;
  align-items: center;
  white-space: nowrap;
}

.drama-desc :deep(.el-descriptions__content .el-descriptions__content-cell) {
  display: flex;
  align-items: center;
  min-height: 30px;
  line-height: 1.4;
  padding: 0 8px;
}

.drama-desc :deep(.desc-notes.el-descriptions__cell),
.drama-desc :deep(.el-descriptions__cell.desc-notes) {
  vertical-align: middle !important;
}

.drama-desc :deep(.desc-notes .el-descriptions__content-cell) {
  align-items: center;
  padding: 6px 8px;
  min-height: 30px;
}

.drama-desc :deep(.el-descriptions__cell) {
  padding-top: 3px !important;
  padding-bottom: 3px !important;
}

.info-notes {
  display: flex;
  flex-direction: column;
  gap: 5px;
  width: 100%;
}

.note-line {
  margin: 0;
  font-size: 11px;
  line-height: 1.45;
  color: var(--tm-text-secondary);
  word-break: break-word;
}

.cross-links {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--tm-border);
  flex-shrink: 0;
}

.cross-links a {
  font-size: 12px;
  font-weight: 600;
  color: var(--tm-purple);
  text-decoration: none;
}

.cross-links a:hover { text-decoration: underline; }

.empty-rec {
  text-align: center;
  padding: 28px 16px;
  color: var(--tm-text-muted);
}

.empty-rec .hint {
  font-size: 12px;
  margin: 8px 0 0;
  line-height: 1.5;
}

.chart-body { padding-top: 0; }

.chart-sub {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--tm-purple);
}

.scatter-chart {
  flex: 1;
  width: 100%;
  min-height: 280px;
  height: 100%;
}

.empty-scatter {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 36px 16px;
  color: var(--tm-text-muted);
  font-size: 13px;
}

.videos-card {
  margin-top: 16px;
}

.videos-body {
  padding-top: 0;
}

.count { font-size: 13px; color: var(--tm-text-muted); }

@media (max-width: 992px) {
  .detail-panels :deep(.el-col + .el-col) {
    margin-top: 16px;
  }

  .panel-card {
    min-height: 0;
  }

  .scatter-chart {
    min-height: 260px;
    height: 260px;
  }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
