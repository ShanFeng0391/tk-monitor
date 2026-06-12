import { ref, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { SCRAPE_POLL_INTERVAL_MS, SCRAPE_POLL_MAX_MS } from '@/utils/scrapeConstants'

/**
 * 跟踪博主采集进度：表格显示「采集中」，并在后台轮询刷新列表直至数据入库。
 */
export function useCreatorScrapePolling({ refresh, findCreator }) {
  const scrapingIds = ref(new Set())
  const scrapeMeta = new Map()
  const pollTimers = new Map()

  function isScraping(creatorId, mode = null) {
    if (!scrapingIds.value.has(creatorId)) return false
    if (!mode) return true
    return scrapeMeta.get(creatorId)?.mode === mode
  }

  function addScrapingId(creatorId) {
    scrapingIds.value = new Set([...scrapingIds.value, creatorId])
  }

  function removeScrapingId(creatorId) {
    scrapingIds.value = new Set([...scrapingIds.value].filter((id) => id !== creatorId))
  }

  function isScrapeComplete(creatorId, creator) {
    const meta = scrapeMeta.get(creatorId)
    if (!meta || !creator) return false

    if (meta.mode === 'historical') {
      if (creator.historical_scraped_at && !meta.hadHistorical) return true
      if (creator.video_count > meta.baselineVideoCount) return true
      return false
    }

    if (creator.video_count > meta.baselineVideoCount) return true
    if (creator.last_scraped_at) {
      const scrapedAt = new Date(creator.last_scraped_at).getTime()
      if (scrapedAt >= meta.startedAt - 5000) return true
    }
    return false
  }

  function stopPolling(creatorId) {
    const timer = pollTimers.get(creatorId)
    if (timer) clearTimeout(timer)
    pollTimers.delete(creatorId)
  }

  function finishScrape(creatorId, { notify = false, message } = {}) {
    stopPolling(creatorId)
    scrapeMeta.delete(creatorId)
    removeScrapingId(creatorId)
    if (notify) {
      ElMessage.success(message || '数据采集已完成')
    }
  }

  async function pollCreator(creatorId) {
    const meta = scrapeMeta.get(creatorId)
    if (!meta) return

    if (Date.now() - meta.startedAt > SCRAPE_POLL_MAX_MS) {
      finishScrape(creatorId)
      ElMessage.warning('采集耗时较长，请稍后手动刷新页面查看结果')
      return
    }

    await refresh({ silent: true })
    const creator = findCreator(creatorId)

    if (isScrapeComplete(creatorId, creator)) {
      finishScrape(creatorId, {
        notify: !meta.notifiedViaHttp,
        message: meta.successMessage,
      })
      return
    }

    pollTimers.set(
      creatorId,
      setTimeout(() => pollCreator(creatorId), SCRAPE_POLL_INTERVAL_MS),
    )
  }

  function trackScrape(creator, mode = 'historical') {
    if (!creator?.id) return

    const creatorId = creator.id
    stopPolling(creatorId)
    scrapeMeta.set(creatorId, {
      startedAt: Date.now(),
      baselineVideoCount: creator.video_count ?? 0,
      hadHistorical: !!creator.historical_scraped_at,
      notifiedViaHttp: false,
      successMessage: null,
      mode,
    })
    addScrapingId(creatorId)
    pollTimers.set(
      creatorId,
      setTimeout(() => pollCreator(creatorId), SCRAPE_POLL_INTERVAL_MS),
    )
  }

  function onScrapeDone(creatorId, data) {
    const meta = scrapeMeta.get(creatorId)
    if (meta) {
      meta.notifiedViaHttp = true
      meta.successMessage = data?.message || `新增 ${data?.new_videos ?? 0} 条视频`
    }
    finishScrape(creatorId)
    refresh()
  }

  function onScrapeBackground(creatorId) {
    if (!scrapingIds.value.has(creatorId)) {
      const creator = findCreator(creatorId)
      if (creator) trackScrape(creator)
    }
  }

  onUnmounted(() => {
    pollTimers.forEach((timer) => clearTimeout(timer))
    pollTimers.clear()
    scrapeMeta.clear()
  })

  return {
    isScraping,
    trackScrape,
    onScrapeDone,
    onScrapeBackground,
  }
}
