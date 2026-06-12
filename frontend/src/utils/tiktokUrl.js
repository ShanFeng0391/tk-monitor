const TIKTOK_VIDEO_URL_RE = /^https?:\/\/(?:www\.)?tiktok\.com\/@([^/]+)\/video\/(\d+)/i

export function normalizeTikTokUsername(username) {
  return (username || '').trim().replace(/^@/, '')
}

export function buildTikTokVideoUrl(username, videoId) {
  const user = normalizeTikTokUsername(username)
  const id = String(videoId || '').trim()
  if (!user || !id) return ''
  return `https://www.tiktok.com/@${user}/video/${id}`
}

export function resolveTikTokVideoUrl(video) {
  if (!video) return ''
  const preferredUser = normalizeTikTokUsername(video.source_username || video.creator_username)
  const built = buildTikTokVideoUrl(preferredUser, video.video_id)
  const stored = (video.video_url || '').trim()
  if (!stored) return built

  const match = stored.match(TIKTOK_VIDEO_URL_RE)
  if (!match) return built || stored

  const [, storedUser, storedId] = match
  if (preferredUser && storedUser.toLowerCase() !== preferredUser.toLowerCase()) {
    return buildTikTokVideoUrl(preferredUser, storedId)
  }
  if (video.video_id && storedId !== String(video.video_id)) {
    return buildTikTokVideoUrl(storedUser, video.video_id)
  }
  return stored
}

export function openTikTokVideo(video) {
  const url = resolveTikTokVideoUrl(video)
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}
