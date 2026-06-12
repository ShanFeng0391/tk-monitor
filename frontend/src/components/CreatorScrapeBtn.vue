<template>
  <div class="scrape-actions">
    <button
      type="button"
      class="tm-btn-primary sm"
      :disabled="historicalDisabled"
      @click="scrapeHistorical"
    >
      {{ historicalLabel }}
    </button>
    <button
      v-if="showDaily"
      type="button"
      class="tm-btn-ghost sm"
      :disabled="dailyDisabled"
      @click="scrapeDaily"
    >
      {{ dailyLabel }}
    </button>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/utils/api'
import { SCRAPE_TIMEOUT_MS } from '@/utils/scrapeConstants'

const props = defineProps({
  creatorId: { type: Number, required: true },
  scrapeUrl: { type: String, required: true },
  showDaily: { type: Boolean, default: false },
  dailyUrl: { type: String, default: '' },
  scrapingHistorical: { type: Boolean, default: false },
  scrapingDaily: { type: Boolean, default: false },
})

const emit = defineEmits(['start', 'done', 'background'])

const loadingHistorical = ref(false)
const loadingDaily = ref(false)

const historicalLabel = computed(() => (
  props.scrapingHistorical ? '采集中...' : '采集数据'
))
const dailyLabel = computed(() => (
  props.scrapingDaily ? '更新中...' : '增量更新'
))

const historicalDisabled = computed(() => (
  props.scrapingHistorical || props.scrapingDaily || loadingHistorical.value
))
const dailyDisabled = computed(() => (
  props.scrapingHistorical || props.scrapingDaily || loadingDaily.value
))

watch(
  () => [props.scrapingHistorical, props.scrapingDaily],
  ([historical, daily]) => {
    if (!historical) loadingHistorical.value = false
    if (!daily) loadingDaily.value = false
  },
)

const scrapeConfig = { timeout: SCRAPE_TIMEOUT_MS, skipErrorToast: true }

async function scrapeHistorical() {
  emit('start', 'historical')
  loadingHistorical.value = true
  try {
    const { data } = await api.post(props.scrapeUrl, {}, scrapeConfig)
    const isFailure = (data?.fetched_videos ?? data?.new_videos ?? 0) === 0
      && props.scrapeUrl.includes('/historical')
    if (isFailure) {
      ElMessage.warning(data.message || '未能拉取到视频，请检查代理池后重试')
    } else {
      ElMessage.success(data.message || `新增 ${data.new_videos} 条视频`)
    }
    emit('done', data)
  } catch (err) {
    if (err.code === 'ECONNABORTED' || /timeout/i.test(err.message || '')) {
      ElMessage.info('采集仍在进行中，列表将自动刷新…')
      emit('background')
    } else {
      const detail = err.response?.data?.detail
      const msg = typeof detail === 'string'
        ? detail
        : (err.message || '采集失败')
      ElMessage.error(msg)
    }
  } finally {
    if (!props.scrapingHistorical) loadingHistorical.value = false
  }
}

async function scrapeDaily() {
  if (!props.dailyUrl) return
  emit('start', 'daily')
  loadingDaily.value = true
  try {
    const { data } = await api.post(props.dailyUrl, {}, scrapeConfig)
    ElMessage.success(data.message || '增量更新完成')
    emit('done', data)
  } catch (err) {
    if (err.code === 'ECONNABORTED' || /timeout/i.test(err.message || '')) {
      ElMessage.info('更新仍在进行中，列表将自动刷新…')
      emit('background')
    } else {
      const detail = err.response?.data?.detail
      const msg = typeof detail === 'string'
        ? detail
        : (err.message || '更新失败')
      ElMessage.error(msg)
    }
  } finally {
    if (!props.scrapingDaily) loadingDaily.value = false
  }
}
</script>

<style scoped>
.scrape-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.tm-btn-primary.sm,
.tm-btn-ghost.sm {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 32px;
  min-width: 76px;
  padding: 0 14px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
  line-height: 1;
}

.tm-btn-ghost.sm {
  border: 1.5px solid var(--tm-border);
  border-radius: var(--tm-radius-pill);
  background: transparent;
  color: var(--tm-text);
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.tm-btn-ghost.sm:hover:not(:disabled) {
  border-color: var(--tm-text);
  background: rgba(0, 0, 0, 0.02);
}

.tm-btn-primary:disabled,
.tm-btn-ghost:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
