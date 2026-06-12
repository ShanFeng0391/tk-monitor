/**
 * 将 v2rayN / 小火箭等客户端二维码内容规范为 socks5 / vmess / vless 链接。
 */

function padBase64(input) {
  const raw = (input || '').trim().replace(/-/g, '+').replace(/_/g, '/')
  return raw + '='.repeat((4 - (raw.length % 4)) % 4)
}

function decodeBase64Text(input) {
  try {
    return atob(padBase64(input))
  } catch {
    return ''
  }
}

function buildSocks5Url(host, port, username = '', password = '', label = '') {
  const user = encodeURIComponent(username || '')
  const pass = encodeURIComponent(password || '')
  let url = ''
  if (username && password) {
    url = `socks5://${user}:${pass}@${host}:${port}`
  } else if (username) {
    url = `socks5://${user}@${host}:${port}`
  } else {
    url = `socks5://${host}:${port}`
  }
  if (label) {
    url += `#${encodeURIComponent(label)}`
  }
  return url
}

function expandSocksAuth(username, password) {
  if (password || !username) {
    return { username: username || '', password: password || '' }
  }
  const decoded = decodeBase64Text(username)
  if (!decoded) {
    return { username, password: '' }
  }
  if (decoded.includes('@') && !decoded.includes('://')) {
    const auth = decoded.split('@')[0]
    if (auth.includes(':')) {
      const idx = auth.indexOf(':')
      return { username: auth.slice(0, idx), password: auth.slice(idx + 1) }
    }
  }
  if (decoded.includes(':') && !decoded.includes('@')) {
    const idx = decoded.indexOf(':')
    return { username: decoded.slice(0, idx), password: decoded.slice(idx + 1) }
  }
  return { username, password: '' }
}

function parseSocks5Scheme(uri) {
  try {
    const trimmed = uri.trim()
    const parsed = new URL(trimmed)
    const label = parsed.hash ? decodeURIComponent(parsed.hash.slice(1)) : ''
    const { username, password } = expandSocksAuth(
      decodeURIComponent(parsed.username || ''),
      decodeURIComponent(parsed.password || ''),
    )
    const host = parsed.hostname || ''
    const port = Number(parsed.port)
    if (!host || !port) return null
    return buildSocks5Url(host, port, username, password, label)
  } catch {
    return null
  }
}

function parseSocksPayload(payload, label = '') {
  const raw = (payload || '').trim()
  if (!raw) return null

  if (raw.includes('://')) {
    const nested = normalizeShareLink(raw)
    return nested.ok ? nested.uri : null
  }

  if (raw.includes('@')) {
    return `socks5://${raw}${label ? `#${encodeURIComponent(label)}` : ''}`
  }

  const colonParts = raw.split(':')
  if (colonParts.length >= 4) {
    const [host, portRaw, username, ...passParts] = colonParts
    const port = Number(portRaw)
    if (host && port > 0) {
      return buildSocks5Url(host, port, username, passParts.join(':'), label)
    }
  }

  if (colonParts.length === 2 && Number(colonParts[1]) > 0) {
    return buildSocks5Url(colonParts[0], Number(colonParts[1]), '', '', label)
  }

  return null
}

function parseSocksScheme(uri) {
  const trimmed = uri.trim()
  const lower = trimmed.toLowerCase()
  if (!lower.startsWith('socks://')) return null

  const hashIdx = trimmed.indexOf('#')
  const label = hashIdx >= 0 ? decodeURIComponent(trimmed.slice(hashIdx + 1)) : ''
  const body = trimmed.slice(8).split('#')[0].split('?')[0].trim()

  if (body.includes('@') && !body.match(/^[A-Za-z0-9+/=_-]+$/)) {
    return `socks5://${body}${label ? `#${encodeURIComponent(label)}` : ''}`
  }

  const decoded = decodeBase64Text(body)
  if (decoded) {
    const normalized = parseSocksPayload(decoded, label)
    if (normalized) return normalized
  }

  return parseSocksPayload(body, label)
}

function parseJsonShare(text) {
  let obj
  try {
    obj = JSON.parse(text)
  } catch {
    return null
  }
  if (!obj || typeof obj !== 'object') return null

  const label = String(obj.ps || obj.remark || obj.name || '').trim()
  const type = String(obj.type || obj.protocol || '').toLowerCase()

  if (type.includes('vmess') && obj.add && obj.port && obj.id) {
    const payload = {
      v: '2',
      ps: label,
      add: String(obj.add),
      port: String(obj.port),
      id: String(obj.id),
      aid: String(obj.aid || '0'),
      net: String(obj.net || 'tcp'),
      type: String(obj.headerType || 'none'),
      host: String(obj.host || ''),
      path: String(obj.path || ''),
      tls: String(obj.tls || ''),
      sni: String(obj.sni || ''),
    }
    const b64 = btoa(JSON.stringify(payload))
    return `vmess://${b64}${label ? `#${encodeURIComponent(label)}` : ''}`
  }

  if (type.includes('vless') && (obj.add || obj.server) && obj.port && (obj.id || obj.uuid)) {
    const host = obj.add || obj.server
    const uuid = obj.id || obj.uuid
    return `vless://${encodeURIComponent(uuid)}@${host}:${obj.port}${label ? `#${encodeURIComponent(label)}` : ''}`
  }

  if (type.includes('sock')) {
    const host = String(obj.add || obj.server || obj.address || obj.host || '').trim()
    const port = Number(obj.port)
    const username = String(obj.username || obj.user || obj.id || '').trim()
    const password = String(obj.password || obj.pass || obj.pwd || '').trim()
    if (host && port > 0) {
      return buildSocks5Url(host, port, username, password, label)
    }
  }

  return null
}

function parseCsvShare(text) {
  const parts = text.split(',').map((part) => part.trim())
  if (parts.length < 3) return null
  const proto = parts[0].toLowerCase()
  if (!proto.includes('sock')) return null
  const [host, portRaw, username, password] = parts.slice(1)
  const port = Number(portRaw)
  if (!host || port <= 0) return null
  return buildSocks5Url(host, port, username || '', password || '')
}

/**
 * @returns {{ ok: true, uri: string } | { ok: false, reason: string }}
 */
export function normalizeShareLink(text) {
  const raw = (text || '').trim()
  if (!raw) {
    return { ok: false, reason: '内容为空' }
  }

  const lower = raw.toLowerCase()
  if (lower.startsWith('socks5://')) {
    const uri = parseSocks5Scheme(raw)
    if (uri) return { ok: true, uri }
  }
  if (lower.startsWith('vmess://') || lower.startsWith('vless://')) {
    return { ok: true, uri: raw }
  }

  if (lower.startsWith('socks://')) {
    const uri = parseSocksScheme(raw)
    if (uri) return { ok: true, uri: parseSocks5Scheme(uri) || uri }
  }

  const jsonUri = parseJsonShare(raw)
  if (jsonUri) return { ok: true, uri: jsonUri }

  const csvUri = parseCsvShare(raw)
  if (csvUri) return { ok: true, uri: csvUri }

  if (/^[A-Za-z0-9+/=_-]+$/.test(raw) && raw.length > 8) {
    const decoded = decodeBase64Text(raw)
    if (decoded) {
      if (decoded.trim().startsWith('{')) {
        const nested = parseJsonShare(decoded.trim())
        if (nested) return { ok: true, uri: nested }
      }
      const payloadUri = parseSocksPayload(decoded.trim())
      if (payloadUri) {
        return { ok: true, uri: parseSocks5Scheme(payloadUri) || payloadUri }
      }
      if (decoded.includes('://')) {
        return normalizeShareLink(decoded.trim())
      }
    }
  }

  const payloadUri = parseSocksPayload(raw)
  if (payloadUri) {
    return { ok: true, uri: parseSocks5Scheme(payloadUri) || payloadUri }
  }

  return {
    ok: false,
    reason: '无法识别为 socks5 / vmess / vless，v2rayN 的 socks:// 或 JSON 格式也可尝试手动粘贴',
  }
}

export function isShareLink(text) {
  return normalizeShareLink(text).ok
}
