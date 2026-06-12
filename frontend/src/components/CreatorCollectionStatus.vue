<template>
  <span :class="['status', statusClass]">{{ statusLabel }}</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  creator: { type: Object, required: true },
  scraping: { type: Boolean, default: false },
})

const statusLabel = computed(() => {
  if (props.scraping) return '采集中'
  if (props.creator?.historical_scraped_at) {
    if ((props.creator?.video_count ?? 0) === 0) return '无入库'
    return '已完成'
  }
  if (props.creator?.last_scraped_at && (props.creator?.video_count ?? 0) === 0) {
    return '采集失败'
  }
  if (props.creator?.last_scraped_at) return '仅增量'
  return '未采集'
})

const statusClass = computed(() => {
  if (props.scraping) return 'running'
  if (props.creator?.historical_scraped_at) {
    if ((props.creator?.video_count ?? 0) === 0) return 'partial'
    return 'ok'
  }
  if (props.creator?.last_scraped_at && (props.creator?.video_count ?? 0) === 0) return 'daily-hot'
  if (props.creator?.last_scraped_at) return 'partial'
  return 'pending'
})
</script>

<style scoped>
.status.ok { color: var(--tm-purple); font-weight: 600; }
.status.partial { color: var(--tm-orange); font-weight: 600; }
.status.pending { color: var(--tm-text-muted); font-weight: 600; }
.status.running { color: #2563eb; font-weight: 600; }
</style>
