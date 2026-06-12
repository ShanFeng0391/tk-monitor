/** 历史/增量采集可能耗时数分钟，需远大于默认 API 超时 */
export const SCRAPE_TIMEOUT_MS = 30 * 60 * 1000

/** 轮询博主列表，直到采集完成或超时 */
export const SCRAPE_POLL_INTERVAL_MS = 3000
export const SCRAPE_POLL_MAX_MS = 35 * 60 * 1000
