/** 跨模块导航与筛选 query 构建 */

export function dramaPath(name) {
  if (!name) return '/dramas'
  return `/dramas/${encodeURIComponent(name)}`
}

export function videoPath(id) {
  return `/videos/${id}`
}

export function historicalViralLink(query = {}) {
  return { path: '/viral', query: cleanQuery(query) }
}

export function dailyHotLink(query = {}) {
  return { path: '/daily-hot', query: cleanQuery(query) }
}

export function videosLink(query = {}) {
  return { path: '/viral', query: cleanQuery(query) }
}

export function creatorVideosLink(creatorId, creatorUsername) {
  if (creatorId) return historicalViralLink({ creator_id: creatorId })
  if (creatorUsername) {
    return historicalViralLink({ creator_username: creatorUsername.replace(/^@/, '') })
  }
  return historicalViralLink()
}

function cleanQuery(q) {
  const out = {}
  Object.entries(q).forEach(([k, v]) => {
    if (v != null && v !== '') out[k] = String(v)
  })
  return out
}
