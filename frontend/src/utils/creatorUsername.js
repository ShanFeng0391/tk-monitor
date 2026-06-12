const USERNAME_RE = /^@[A-Za-z0-9_.]{1,49}$/

const PLAIN_USERNAME_RE = /^[A-Za-z0-9_.]{1,49}$/

const TIKTOK_URL_RE = /tiktok\.com\/@([A-Za-z0-9_.]{1,49})/gi

const AT_USERNAME_RE = /@([A-Za-z0-9_.]{1,49})\b/g

const SKIP_PLAIN = new Set(['none', '无', '未知', 'null', 'n/a'])



function appendUsername(found, seen, username) {

  const token = String(username || '').trim().replace(/^@/, '')

  if (!token || !PLAIN_USERNAME_RE.test(token)) return

  if (SKIP_PLAIN.has(token.toLowerCase())) return

  const key = token.toLowerCase()

  if (seen.has(key)) return

  seen.add(key)

  found.push(`@${token}`)

}



export function validateCreatorUsername(input) {

  const value = formatCreatorInput(input)

  if (!value) {

    return { ok: false, message: '请输入博主用户名' }

  }

  if (!USERNAME_RE.test(value)) {

    return { ok: false, message: '用户名格式不正确，示例：username 或 @username' }

  }

  return { ok: true, value }

}



export function formatCreatorInput(input) {

  const trimmed = (input || '').trim()

  if (!trimmed) return ''

  const token = trimmed.replace(/^@/, '')

  if (!PLAIN_USERNAME_RE.test(token)) return ''

  return `@${token}`

}



export function extractUsernamesFromText(text) {

  const found = []

  const seen = new Set()

  const raw = String(text || '')



  for (const match of raw.matchAll(TIKTOK_URL_RE)) {

    appendUsername(found, seen, match[1])

  }



  AT_USERNAME_RE.lastIndex = 0

  for (const match of raw.matchAll(AT_USERNAME_RE)) {

    appendUsername(found, seen, match[1])

  }



  for (const chunk of raw.split(/[\n\r,;、]+/)) {

    const token = chunk.trim().replace(/^["']|["']$/g, '').replace(/^@/, '')

    if (!token) continue

    appendUsername(found, seen, token.split(/\s+/)[0])

  }



  return found.filter((name) => USERNAME_RE.test(name))

}


