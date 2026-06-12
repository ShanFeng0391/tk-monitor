export function formatVelocity(value) {
  if (value == null || value === '') return '0'
  const num = Number(value)
  if (Number.isNaN(num)) return '0'
  return Math.round(num).toLocaleString(undefined, { maximumFractionDigits: 0 })
}

export function formatNum(n) {
  if (n == null || n === '') return '0'
  const num = Number(n)
  if (Number.isNaN(num)) return '0'
  if (num >= 100000000) return (num / 100000000).toFixed(1) + '亿'
  if (num >= 10000) return (num / 10000).toFixed(1) + '万'
  return num.toLocaleString()
}

/** 后端 datetime 为 UTC  naive 字符串，需按 UTC 解析（避免被当成本地时间多算 8 小时） */
export function parseBackendUtcDate(value) {
  if (!value) return null
  if (value instanceof Date) return value
  const text = String(value).trim()
  if (!text) return null
  if (text.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(text)) {
    const parsed = new Date(text)
    return Number.isNaN(parsed.getTime()) ? null : parsed
  }
  const normalized = text.includes('T') ? text : text.replace(' ', 'T')
  const parsed = new Date(`${normalized}Z`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

export function formatDate(d) {
  const parsed = parseBackendUtcDate(d)
  if (!parsed) return '-'
  return parsed.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

/** 年月日，如 2026/06/08 */
export function formatDateYmd(d) {
  const parsed = parseBackendUtcDate(d)
  if (!parsed) return ''
  const y = parsed.getFullYear()
  const m = String(parsed.getMonth() + 1).padStart(2, '0')
  const day = String(parsed.getDate()).padStart(2, '0')
  return `${y}/${m}/${day}`
}

/** 自发布至今的时长，如「17小时」「2天3小时」 */
export function formatPublishAge(publishedAt) {
  const published = parseBackendUtcDate(publishedAt)
  if (!published) return '-'
  const ms = Date.now() - published.getTime()
  if (Number.isNaN(ms) || ms < 0) return '刚刚'
  const minutes = Math.floor(ms / 60000)
  if (minutes < 1) return '1分钟内'
  if (minutes < 60) return `${minutes}分钟`
  const hours = Math.floor(minutes / 60)
  const remMinutes = minutes % 60
  if (hours < 24) {
    return remMinutes >= 30 ? `${hours}小时${remMinutes}分钟` : `${hours}小时`
  }
  const days = Math.floor(hours / 24)
  const remHours = hours % 24
  return remHours ? `${days}天${remHours}小时` : `${days}天`
}

export function categoryLabel(category, video = {}) {
  const isHistorical = video.is_historical_viral || category === 'historical_viral' || category === 'viral'
  const isDailyHot = video.is_daily_hot || category === 'daily_hot' || category === 'hot'
  if (isHistorical && isDailyHot) return '历史爆款 · 当日热门'
  if (isHistorical) return '历史爆款'
  if (isDailyHot) return '当日热门'
  return '普通'
}

export function categoryClass(category, video = {}) {
  const isHistorical = video.is_historical_viral || category === 'historical_viral' || category === 'viral'
  const isDailyHot = video.is_daily_hot || category === 'daily_hot' || category === 'hot'
  if (isHistorical && isDailyHot) return 'daily-hot'
  if (isHistorical) return 'historical'
  if (isDailyHot) return 'daily-hot'
  return 'dark'
}
