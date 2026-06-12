<template>

  <div v-loading="loading" class="page video-detail-page">

    <el-row :gutter="16" v-if="video" class="detail-row">

      <!-- 左侧：原视频封面 + 视频信息（高度与右侧两卡齐平） -->
      <el-col :xs="24" :sm="24" :md="7" :lg="7" class="detail-col-left">

        <div class="tm-card side-card video-info-stretch">

          <div class="tm-card-header"><span class="title">视频信息</span></div>

          <div class="tm-card-body side-body stretch-body">

            <div class="video-cover-wrap">
              <img
                v-if="video.cover_url"
                :src="video.cover_url"
                class="video-cover"
                alt="视频封面"
              />
              <div v-else class="cover-placeholder">暂无封面</div>
            </div>

            <div class="info-block">
              <el-descriptions :column="1" border size="small" class="compact-desc">
                <el-descriptions-item label="博主">
                  <router-link
                    v-if="video.creator_id || video.creator_username"
                    :to="creatorVideosLink(video.creator_id, video.creator_username)"
                    class="text-link"
                  >@{{ video.creator_username }}</router-link>
                  <span v-else>@{{ video.creator_username }}</span>
                </el-descriptions-item>
                <el-descriptions-item label="博主粉丝量">
                  {{ video.creator_follower_count ? formatNum(video.creator_follower_count) : '—' }}
                </el-descriptions-item>
                <el-descriptions-item label="播放量">{{ formatNum(video.view_count) }}</el-descriptions-item>
                <el-descriptions-item label="点赞">{{ formatNum(video.like_count) }}</el-descriptions-item>
                <el-descriptions-item label="发布日期">
                  {{ video.published_at ? formatDateYmd(video.published_at) : '—' }}
                </el-descriptions-item>
                <el-descriptions-item label="分类">{{ displayCategory }}</el-descriptions-item>
              </el-descriptions>

              <div class="side-actions">
                <button
                  type="button"
                  class="tm-btn-primary btn-favorite"
                  :class="{ 'is-favorited': video.is_favorited }"
                  @click="toggleFavorite"
                >
                  {{ video.is_favorited ? '取消收藏' : '收藏' }}
                </button>
                <a
                  class="action-link"
                  :href="tiktokLink"
                  target="_blank"
                  rel="noopener noreferrer"
                >TikTok ↗</a>
              </div>
            </div>

          </div>

        </div>

      </el-col>



      <!-- 右侧：影视剧标注 + TMDB 海报 -->
      <el-col :xs="24" :sm="24" :md="17" :lg="17" class="detail-col-right">

        <div class="right-stack">

        <div class="tm-card side-card">

          <div class="tm-card-header">
            <span class="title">影视剧标注</span>
            <button class="tm-btn-ghost btn-sm" @click="openLabelDialog">
              {{ recognition ? '编辑' : '去标注' }}
            </button>
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

                  <div class="drama-head">
                    <router-link :to="dramaPath(recognition.drama_name)" class="drama-title">
                      {{ recognition.drama_name }}
                    </router-link>
                    <span class="tm-tag orange">人工标注</span>
                  </div>

                  <el-descriptions :column="1" border size="small" class="compact-desc">
                    <el-descriptions-item label="分类">{{ displayCategory }}</el-descriptions-item>
                    <el-descriptions-item label="演员">{{ recognition.actors || '—' }}</el-descriptions-item>
                    <el-descriptions-item v-if="recognition.analysis_reason" label="备注">
                      <span class="info-notes">{{ recognition.analysis_reason }}</span>
                    </el-descriptions-item>
                  </el-descriptions>

                  <div class="cross-links">
                    <router-link :to="dramaPath(recognition.drama_name)">影视剧数据</router-link>
                    <router-link :to="historicalViralLink({ drama_name: recognition.drama_name })">爆款视频</router-link>
                    <router-link :to="videosLink({ drama_name: recognition.drama_name })">相关视频</router-link>
                  </div>

                </div>

              </div>

            </template>

            <div v-else class="empty-rec">
              <p>尚未标注影视剧</p>
              <p class="hint">在豆包中识别封面后，复制完整结果粘贴到标注框</p>
              <button class="tm-btn-primary btn-sm" @click="openLabelDialog">开始标注</button>
            </div>

          </div>

        </div>



        <div class="tm-card side-card chart-card">
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

        </div>

      </el-col>

    </el-row>



    <el-dialog v-model="showEdit" title="影视剧标注" width="640px">

      <el-form label-width="88px">

        <el-form-item label="豆包结果" required>
          <el-input
            v-model="doubaoPaste"
            type="textarea"
            :rows="8"
            placeholder="粘贴豆包对封面的完整识别结果（含片名、年份、导演、主演、类型、剧情等）"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="autofilling" @click="handleParsePaste">AI 提取并填写</el-button>
          <span class="autofill-hint">以豆包原文为准；动漫走 Bangumi、其它走 TMDB 补充参考链接</span>
        </el-form-item>

        <div v-if="lookupPreview" class="lookup-preview" :class="{ unverified: !lookupPreview.verified }">
          <div class="preview-title">
            {{ lookupPreview.verified ? '已从豆包结果提取' : '提取不完整（请核对）' }}
            <a v-if="lookupPreview.tmdb_url" :href="lookupPreview.tmdb_url" target="_blank" rel="noopener">{{ lookupPreview.metadata_source === 'bangumi' ? 'Bangumi' : 'TMDB' }} 参考 ↗</a>
          </div>
          <div v-if="lookupPreview.tmdb_ref_note">{{ lookupPreview.tmdb_ref_note }}</div>
          <div>剧名：{{ lookupPreview.drama_name }}</div>
          <div>类型：{{ lookupPreview.drama_type }}</div>
          <div>英文名：{{ lookupPreview.english_name || '—' }}</div>
          <div>年份：{{ lookupPreview.release_year || '—' }}</div>
          <div>演员：{{ lookupPreview.actors || '—' }}</div>
          <div v-if="lookupPreview.director">导演：{{ lookupPreview.director }}</div>
        </div>

        <el-divider content-position="left">确认 / 微调</el-divider>

        <el-form-item label="剧名" required>
          <el-input v-model="editForm.drama_name" placeholder="提取后自动填写，可手动修改" />
        </el-form-item>

        <el-form-item label="类型"><el-input v-model="editForm.drama_type" placeholder="如 科幻、剧情" /></el-form-item>

        <el-form-item label="演员"><el-input v-model="editForm.actors" placeholder="主要演员，逗号分隔" /></el-form-item>

        <el-form-item label="备注"><el-input v-model="editForm.analysis_reason" type="textarea" :rows="3" placeholder="导演、简介、Bangumi/TMDB 参考等" /></el-form-item>

      </el-form>

      <template #footer>

        <el-button @click="showEdit = false">取消</el-button>

        <el-button type="primary" :loading="savingEdit" @click="saveManualEdit">保存标注</el-button>

      </template>

    </el-dialog>

  </div>

</template>



<script setup>

import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'

import { useRoute, useRouter } from 'vue-router'

import { ElMessage } from 'element-plus'

import * as echarts from 'echarts'

import api from '@/utils/api'

import { formatNum, formatDateYmd } from '@/utils/format'

import { dramaPath, historicalViralLink, videosLink, creatorVideosLink } from '@/utils/navLinks'
import { resolveTikTokVideoUrl } from '@/utils/tiktokUrl'

const route = useRoute()
const router = useRouter()

const video = ref(null)

const recognition = ref(null)

const loading = ref(false)

const chartRef = ref(null)
const scatterData = ref(null)
let chartInstance = null

const showEdit = ref(false)

const savingEdit = ref(false)

const autofilling = ref(false)

const lookupPreview = ref(null)

const doubaoPaste = ref('')

const editForm = ref({ drama_name: '', drama_type: '', actors: '', analysis_reason: '' })



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
  return '—'
})

const tiktokLink = computed(() => resolveTikTokVideoUrl(video.value))

const scatterEmpty = computed(() => {
  if (!recognition.value?.drama_name || isInvalidDrama(recognition.value.drama_name)) {
    return '请先完成人工标注，以查看同影视剧视频分布'
  }
  if (scatterData.value && !scatterData.value.points?.length) {
    return '暂无同剧关联视频数据'
  }
  return ''
})

function isInvalidDrama(name) {
  return !name || ['未知', '非影视内容'].includes(name)
}

function stripBookTitle(name) {
  return (name || '').replace(/^《|》$/g, '').trim()
}

function openLabelDialog() {
  lookupPreview.value = null
  doubaoPaste.value = ''
  if (recognition.value) {
    editForm.value = {
      drama_name: stripBookTitle(recognition.value.drama_name),
      drama_type: recognition.value.drama_type || '',
      actors: recognition.value.actors || '',
      analysis_reason: recognition.value.analysis_reason || '',
    }
  } else {
    editForm.value = { drama_name: '', drama_type: '', actors: '', analysis_reason: '' }
  }
  showEdit.value = true
}



async function loadVideo() {

  loading.value = true

  try {

    const { data } = await api.get(`/videos/${route.params.id}`)

    video.value = data

    recognition.value = data.recognition

    await nextTick()
    await loadDramaScatter()
  } finally {
    loading.value = false
  }
}

async function loadDramaScatter() {
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  try {
    const { data } = await api.get(`/videos/${route.params.id}/drama-scatter`)
    scatterData.value = data
  } catch {
    scatterData.value = { drama_name: recognition.value?.drama_name, points: [] }
  }
  await nextTick()
  if (scatterData.value?.points?.length) {
    renderScatterChart(scatterData.value)
  }
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
      axisLabel: { formatter: (v) => {
        const d = new Date(v)
        return `${d.getMonth() + 1}/${d.getDate()}`
      }},
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
    if (id && id !== video.value?.id) router.push(`/videos/${id}`)
  })
  requestAnimationFrame(() => {
    chartInstance?.resize()
    setTimeout(() => chartInstance?.resize(), 120)
  })
}



async function toggleFavorite() {

  if (video.value.is_favorited) {

    await api.delete(`/videos/${video.value.id}/favorite`)

    video.value.is_favorited = false

    ElMessage.success('已取消收藏')

  } else {

    await api.post(`/videos/${video.value.id}/favorite`)

    video.value.is_favorited = true

    ElMessage.success('已收藏')

  }

}



function buildAnalysisReason(data) {
  const bits = []
  if (data.director) bits.push(`导演：${data.director}`)
  if (data.summary) bits.push(`简介：${data.summary}`)
  if (data.english_name) bits.push(`英文名：${data.english_name}`)
  if (data.release_year) bits.push(`年份：${data.release_year}`)
  if (data.tmdb_ref_note) bits.push(data.tmdb_ref_note)
  else if (data.tmdb_url) bits.push(`TMDB参考：${data.tmdb_url}`)
  return bits.join('；')
}

function applyLookupToForm(data) {
  lookupPreview.value = data
  editForm.value.drama_name = stripBookTitle(data.drama_name)
  if (data.drama_type) editForm.value.drama_type = data.drama_type
  if (data.actors) editForm.value.actors = data.actors
  const extra = buildAnalysisReason(data)
  if (extra) editForm.value.analysis_reason = extra
}

async function handleParsePaste() {
  const text = doubaoPaste.value?.trim()
  if (!text) {
    ElMessage.warning('请先粘贴豆包识别结果')
    return
  }
  if (text.length < 20) {
    ElMessage.warning('粘贴内容过短，请复制完整的豆包识别结果')
    return
  }

  autofilling.value = true
  lookupPreview.value = null
  try {
    const { data } = await api.post('/recognition/parse-doubao-paste', { pasted_text: text })
    applyLookupToForm(data)
    if (data.verified) {
      ElMessage.success('已提取，请核对后保存')
    } else {
      ElMessage.warning('提取不完整，请手动补充')
    }
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '提取失败')
  } finally {
    autofilling.value = false
  }
}

async function saveManualEdit() {

  if (!editForm.value.drama_name?.trim()) {
    ElMessage.warning('请填写剧名')
    return
  }

  savingEdit.value = true

  try {

    const { data } = await api.put(`/videos/${route.params.id}/recognition`, editForm.value)

    recognition.value = data

    if (editForm.value.drama_type) video.value.content_type = editForm.value.drama_type

    showEdit.value = false
    ElMessage.success('标注已保存')
    await loadVideo()

  } finally {

    savingEdit.value = false

  }

}



onMounted(() => {
  loadVideo()
  window.addEventListener('resize', handleChartResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleChartResize)
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
})

function handleChartResize() {
  chartInstance?.resize()
}

</script>



<style scoped>

.video-detail-page {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 桌面端：与侧栏同高，flex 链铺满内容区（不再用 vh 硬算） */
@media (min-width: 992px) {
  .video-detail-page {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }

  .video-detail-page .detail-row {
    flex: 1;
    width: 100%;
    height: 100%;
    margin: 0 !important;
    min-height: 0;
    align-items: stretch;
  }

  .detail-row :deep(.el-col) {
    display: flex;
    min-height: 0;
  }

  .detail-col-left,
  .detail-col-right {
    flex-direction: column;
    min-height: 0;
  }

  .video-info-stretch {
    flex: 1;
    display: flex;
    flex-direction: column;
    width: 100%;
    min-height: 0;
    height: 100%;
  }

  .stretch-body {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    gap: 0;
  }

  .stretch-body .video-cover-wrap {
    flex: 1 1 0;
    display: flex;
    align-items: center;
    justify-content: center;
    max-width: 208px;
    width: 100%;
    margin: 0 auto;
    min-height: 0;
    padding-bottom: 16px;
  }

  .stretch-body .video-cover,
  .stretch-body .cover-placeholder {
    width: 100%;
    max-height: min(52vh, 420px);
    height: auto;
    aspect-ratio: 9 / 16;
    object-fit: cover;
  }

  .stretch-body .info-block {
    flex: 0 0 auto;
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: 100%;
  }

  .stretch-body .compact-desc {
    flex: 0 0 auto;
  }

  .stretch-body .side-actions {
    flex: 0 0 auto;
  }

  .right-stack {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 12px;
    width: 100%;
    height: 100%;
    min-height: 0;
  }

  .right-stack > .side-card:not(.chart-card) {
    flex: 0 0 auto;
    display: flex;
    flex-direction: column;
  }

  .right-stack > .side-card:not(.chart-card) .side-body {
    flex: 0 0 auto;
    overflow: visible;
  }

  .right-stack .chart-card {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .right-stack .chart-card .chart-body {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 160px;
  }

  .right-stack .scatter-chart {
    flex: 1;
    width: 100%;
    min-height: 160px;
    height: 100% !important;
  }
}

.side-card .tm-card-body.side-body { padding: 14px 16px; }

/* 视频信息 / 影视剧标注：标题行等高 */
.detail-col-left > .side-card > .tm-card-header,
.right-stack > .side-card:not(.chart-card) > .tm-card-header {
  min-height: 52px;
  height: 52px;
  padding: 0 18px;
  box-sizing: border-box;
  flex-shrink: 0;
}

.detail-col-left > .side-card > .tm-card-header .title,
.right-stack > .side-card:not(.chart-card) > .tm-card-header .title {
  font-size: 16px;
  line-height: 1.2;
}

.right-stack > .side-card:not(.chart-card) > .tm-card-header .btn-sm {
  flex-shrink: 0;
}

.video-cover-wrap {
  max-width: 208px;
  width: 100%;
  margin: 0 auto 16px;
}

.video-cover {
  width: 100%;
  max-height: min(52vh, 420px);
  aspect-ratio: 9 / 16;
  object-fit: cover;
  border-radius: var(--tm-radius-md);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  display: block;
}

.cover-placeholder,
.poster-placeholder {
  border-radius: var(--tm-radius-md);
  background: #f5f5f7;
  border: 1px dashed var(--tm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--tm-text-muted);
  font-size: 12px;
}

.cover-placeholder {
  width: 100%;
  max-height: min(52vh, 420px);
  aspect-ratio: 9 / 16;
}

.compact-desc :deep(.el-descriptions__label),
.compact-desc :deep(.el-descriptions__cell.el-descriptions__label) {
  width: 84px;
  min-width: 84px;
  font-size: 11px;
  text-align: center !important;
  vertical-align: middle !important;
  white-space: nowrap;
}

.compact-desc :deep(.el-descriptions__content),
.compact-desc :deep(.el-descriptions__cell.el-descriptions__content) {
  font-size: 12px;
  vertical-align: middle !important;
}

.compact-desc :deep(.el-descriptions__label .el-descriptions__label-content) {
  justify-content: center;
  align-items: center;
  white-space: nowrap;
}

.compact-desc :deep(.el-descriptions__content .el-descriptions__content-cell) {
  display: flex;
  align-items: center;
  min-height: 28px;
  line-height: 1.35;
  padding: 0 10px;
}

.compact-desc :deep(.el-descriptions__cell) {
  padding-top: 4px !important;
  padding-bottom: 4px !important;
}

.info-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}

.side-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--tm-border);
}

.btn-favorite {
  flex: 1;
  min-width: 0;
  height: 34px;
  padding: 0 14px;
  border: none;
  border-radius: var(--tm-radius-pill);
  background: var(--tm-black);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s, background 0.2s;
}

.btn-favorite:hover {
  opacity: 0.92;
}

.btn-favorite.is-favorited {
  background: var(--tm-surface);
  color: var(--tm-text);
  border: 1.5px solid var(--tm-border);
}

.action-link {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  color: var(--tm-blue);
  text-decoration: none;
  white-space: nowrap;
}

.action-link:hover {
  text-decoration: underline;
}

.drama-layout {
  display: flex;
  gap: 16px;
  align-items: flex-end;
}

.tmdb-side {
  flex-shrink: 0;
  width: 108px;
  text-align: center;
}

.tmdb-poster {
  width: 108px;
  height: 162px;
  object-fit: cover;
  border-radius: var(--tm-radius-md);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  background: #f0f0f0;
}

.poster-placeholder {
  width: 108px;
  height: 162px;
}

.tmdb-link {
  display: inline-block;
  margin-top: 6px;
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
}

.drama-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.drama-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--tm-text);
  text-decoration: none;
  letter-spacing: -0.02em;
}

.drama-title:hover { color: var(--tm-blue); }

.info-notes {
  font-size: 12px;
  line-height: 1.5;
  color: var(--tm-text);
  word-break: break-word;
}

.link { font-size: 12px; font-weight: 600; color: var(--tm-blue); text-decoration: none; }

.empty-rec {
  text-align: center;
  padding: 28px 16px;
  color: var(--tm-text-muted);
}

.empty-rec .hint {
  font-size: 12px;
  margin: 8px 0 12px;
  line-height: 1.5;
}

.chart-body { padding-top: 0; }

.chart-sub {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--tm-purple);
}

.scatter-chart { height: 280px; min-height: 120px; width: 100%; }

.empty-scatter {
  text-align: center;
  padding: 36px 16px;
  color: var(--tm-text-muted);
  font-size: 13px;
}

.text-link {
  color: var(--tm-blue);
  font-weight: 600;
  text-decoration: none;
  font-size: 13px;
}

.text-link:hover { text-decoration: underline; }

.cross-links {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
  padding-top: 12px;
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

@media (max-width: 992px) {
  .video-cover-wrap { max-width: 140px; }
  .drama-layout { flex-direction: column; align-items: center; }
  .drama-main { width: 100%; }
}

.autofill-hint { margin-left: 10px; font-size: 12px; color: var(--tm-text-muted); }

.lookup-preview {
  margin: 0 0 12px 88px;
  padding: 12px 14px;
  border-radius: var(--tm-radius-md);
  background: #f0faf0;
  border: 1px solid #c8e6c9;
  font-size: 13px;
  line-height: 1.6;
  color: var(--tm-text);
}
.lookup-preview.unverified {
  background: #fff8e6;
  border-color: #ffe0a3;
}
.preview-title {
  font-weight: 600;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.preview-title a {
  font-size: 12px;
  color: var(--tm-blue);
}

.chart-sub {
  margin-left: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--tm-purple);
}
</style>
