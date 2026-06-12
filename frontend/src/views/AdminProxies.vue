<template>
  <div class="page">
    <div class="stats-row">
      <div v-for="item in statCards" :key="item.label" class="stat-card">
        <div class="stat-value">{{ item.value }}</div>
        <div class="stat-label">{{ item.label }}</div>
      </div>
    </div>

    <div class="tm-card reco-card">
      <div class="tm-card-header">
        <span class="title">代理池建议</span>
        <div class="header-actions">
          <button
            class="tm-btn-ghost sm"
            :disabled="pruning || !canPrune"
            @click="pruneBad"
          >
            {{ pruning ? '处理中…' : '删除高失败率节点' }}
          </button>
        </div>
      </div>
      <div class="tm-card-body reco-body">
        <ul v-if="stats?.recommendations?.length" class="reco-list">
          <li v-for="(msg, i) in stats.recommendations" :key="i">{{ msg }}</li>
        </ul>
        <div class="proxy-summary">
          启用 {{ stats?.enabled ?? 0 }} 条 · 健康 {{ stats?.healthy ?? 0 }} 条 ·
          建议最少 {{ stats?.suggested_min_proxies ?? '—' }} 条 ·
          可用 {{ stats?.healthy_available ?? '—' }} 条
        </div>
        <el-table
          v-if="highFailure.length"
          :data="highFailure"
          size="small"
          stripe
          class="fail-table"
        >
          <el-table-column prop="label" label="备注" min-width="90">
            <template #default="{ row }">{{ row.label || '—' }}</template>
          </el-table-column>
          <el-table-column prop="masked_url" label="地址" min-width="180" />
          <el-table-column label="失败率" width="90">
            <template #default="{ row }">
              <span class="rate-bad">{{ formatFailureRate(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="成功/失败" width="110">
            <template #default="{ row }">{{ row.success_count }} / {{ row.fail_count }}</template>
          </el-table-column>
          <el-table-column prop="last_error" label="最近错误" min-width="160">
            <template #default="{ row }">
              <span class="error-text">{{ row.last_error || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" @click="removeProxyById(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <p v-else class="empty-tip">暂无高失败率代理节点。</p>
      </div>
    </div>

    <div class="tm-card">
      <div class="tm-card-header">
        <span class="title">代理池</span>
        <div class="header-actions">
          <button class="tm-btn-ghost" :disabled="reloadingGateway" @click="reloadGateway">
            {{ reloadingGateway ? '重载中…' : '重载网关' }}
          </button>
          <button class="tm-btn-ghost" :disabled="checkingAll" @click="checkAll">
            {{ checkingAll ? '检测中…' : '全部健康检查' }}
          </button>
          <button class="tm-btn-primary" @click="openCreate">添加代理</button>
        </div>
      </div>
      <div class="tm-card-body table-body">
        <el-table :data="proxies" v-loading="loading" stripe>
          <el-table-column prop="label" label="备注" min-width="100">
            <template #default="{ row }">{{ row.label || '—' }}</template>
          </el-table-column>
          <el-table-column prop="protocol" label="类型" width="90">
            <template #default="{ row }">
              <span class="tm-tag dark">{{ (row.protocol || 'socks5').toUpperCase() }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="masked_url" label="地址" min-width="220" />
          <el-table-column prop="enabled" label="启用" width="80">
            <template #default="{ row }">
              <span class="tm-tag" :class="row.enabled ? 'blue' : 'daily-hot'">
                {{ row.enabled ? '是' : '否' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="health_status" label="健康" width="110">
            <template #default="{ row }">
              <span class="tm-tag" :class="healthClass(row)">{{ healthLabel(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="失败率" width="90">
            <template #default="{ row }">
              <span :class="{ 'rate-bad': row.failure_rate >= 0.4 && row.fail_count >= 5 }">
                {{ formatFailureRate(row) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="统计" width="120">
            <template #default="{ row }">
              成功 {{ row.success_count }} / 失败 {{ row.fail_count }}
            </template>
          </el-table-column>
          <el-table-column prop="last_check_at" label="最近检测" min-width="150">
            <template #default="{ row }">{{ formatTime(row.last_check_at) }}</template>
          </el-table-column>
          <el-table-column prop="last_error" label="最近错误" min-width="160">
            <template #default="{ row }">
              <span class="error-text">{{ row.last_error || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" :loading="checkingId === row.id" @click="checkOne(row)">
                检测
              </el-button>
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="removeProxy(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog
      v-model="showForm"
      :title="editing ? '编辑代理' : '添加代理'"
      width="560px"
      append-to-body
    >
      <el-form label-width="100px">
        <el-form-item v-if="!editing" label="快捷导入">
          <div class="import-row">
            <el-input
              v-model="form.share_uri"
              type="textarea"
              :rows="3"
              placeholder="socks5://user:pass@host:1080&#10;vmess://...&#10;vless://uuid@host:443?..."
              @input="applyShareUri"
              @paste="onPasteShareUri"
            />
            <div class="import-actions">
              <input
                ref="qrInputRef"
                type="file"
                accept="image/*"
                class="qr-file-input"
                @change="onQrFileChange"
              />
              <el-button :loading="decodingQr" @click="triggerQrUpload">识别二维码</el-button>
            </div>
          </div>
          <p class="form-tip">支持粘贴链接或识别二维码；兼容 v2rayN 的 socks://、JSON、Base64 等格式。</p>
        </el-form-item>
        <el-alert
          v-if="parsedPreview"
          :title="parsedPreview.title"
          type="success"
          :closable="false"
          show-icon
          class="parse-preview"
        >
          <template #default>
            <div>{{ parsedPreview.remote }}</div>
            <div v-if="parsedPreview.convert">{{ parsedPreview.convert }}</div>
          </template>
        </el-alert>
        <el-form-item v-if="editing && isGatewayProtocol(editing)" label="更换链接">
          <el-input
            v-model="form.share_uri"
            type="textarea"
            :rows="2"
            placeholder="留空则不修改 vmess/vless 链接"
          />
        </el-form-item>
        <el-form-item v-if="showManualFields" label="主机">
          <el-input v-model="form.host" placeholder="1.2.3.4 或 proxy.example.com" />
        </el-form-item>
        <el-form-item v-if="showManualFields" label="端口">
          <el-input-number v-model="form.port" :min="1" :max="65535" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="showManualFields" label="用户名">
          <el-input v-model="form.username" placeholder="选填" />
        </el-form-item>
        <el-form-item v-if="showManualFields" :label="editing ? '新密码' : '密码'">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="editing ? '留空则不修改' : '选填'"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.label" placeholder="例如：美国 VPS #1" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveProxy">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api'
import { decodeQrFromFile } from '@/utils/qrDecode'
import { normalizeShareLink } from '@/utils/shareLinkNormalize'

const loading = ref(false)
const saving = ref(false)
const checkingAll = ref(false)
const checkingId = ref(null)
const reloadingGateway = ref(false)
const pruning = ref(false)
const decodingQr = ref(false)
const qrInputRef = ref(null)
const proxies = ref([])
const stats = ref(null)
const showForm = ref(false)
const editing = ref(null)
const form = ref(emptyForm())
const detectedProtocol = ref('socks5')

const highFailure = computed(() => stats.value?.high_failure_proxies || [])
const canPrune = computed(() => (stats.value?.prune_candidate_ids || []).length > 0)

function emptyForm() {
  return {
    share_uri: '',
    host: '',
    port: 1080,
    username: '',
    password: '',
    label: '',
    enabled: true,
  }
}

function isGatewayProtocol(row) {
  const p = (row?.protocol || 'socks5').toLowerCase()
  return p === 'vmess' || p === 'vless'
}

const showManualFields = computed(() => {
  if (editing.value && isGatewayProtocol(editing.value) && !form.value.share_uri?.trim()) {
    return false
  }
  const uri = form.value.share_uri?.trim().toLowerCase() || ''
  if (uri.startsWith('vmess://') || uri.startsWith('vless://')) return false
  return true
})

const statCards = computed(() => {
  const s = stats.value || {}
  const gwLabel = s.gateway_running
    ? `运行中 (${s.gateway_nodes ?? 0})`
    : s.gateway_nodes
      ? '异常'
      : '—'
  return [
    { label: '总数', value: s.total ?? 0 },
    { label: '已启用', value: s.enabled ?? 0 },
    { label: '健康', value: s.healthy ?? 0 },
    { label: '异常', value: s.unhealthy ?? 0 },
    { label: '冷却中', value: s.cooldown ?? 0 },
    { label: '网关', value: gwLabel },
    { label: '调度后端', value: s.backend === 'redis' ? 'Redis' : '内存' },
  ]
})

function formatFailureRate(row) {
  const total = (row.success_count || 0) + (row.fail_count || 0)
  if (!total && row.failure_rate == null) return '—'
  const rate = row.failure_rate != null ? row.failure_rate : row.fail_count / total
  return `${Math.round(rate * 100)}%`
}

function healthLabel(row) {
  if (row.in_cooldown) return '冷却'
  const map = {
    healthy: '健康',
    unhealthy: '异常',
    checking: '检测中',
    unknown: '未检测',
  }
  return map[row.health_status] || row.health_status || '未检测'
}

function healthClass(row) {
  if (row.in_cooldown) return 'daily-hot'
  if (row.health_status === 'healthy') return 'blue'
  if (row.health_status === 'unhealthy') return 'daily-hot'
  if (row.health_status === 'checking') return 'purple'
  return 'dark'
}

function formatTime(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

const parsedPreview = computed(() => {
  const raw = form.value.share_uri?.trim()
  if (!raw) return null
  const lower = raw.toLowerCase()
  if (lower.startsWith('vless://') || lower.startsWith('vmess://')) {
    const info = parseGatewayUri(raw)
    if (!info) return { title: '链接格式可能有误', remote: '请检查 vless/vmess 链接是否完整', convert: '' }
    return {
      title: `已识别 ${info.protocol.toUpperCase()} 节点`,
      remote: `远程：${info.host}:${info.port}${info.label ? `（${info.label}）` : ''}`,
      convert: '保存后将自动转为本地 SOCKS5，由 sing-box 转发（端口在列表中显示）',
    }
  }
  if (lower.startsWith('socks5://')) {
    const info = parseSocks5Uri(raw)
    if (!info?.host) return null
    return {
      title: '已识别 SOCKS5 节点',
      remote: `地址：${info.host}:${info.port}`,
      convert: '',
    }
  }
  return null
})

function parseGatewayUri(raw) {
  const lower = raw.trim().toLowerCase()
  if (lower.startsWith('vless://')) {
    try {
      const parsed = new URL(raw.trim())
      return {
        protocol: 'vless',
        host: parsed.hostname || '',
        port: Number(parsed.port) || 443,
        label: parsed.hash ? decodeURIComponent(parsed.hash.slice(1)) : '',
      }
    } catch {
      return null
    }
  }
  if (lower.startsWith('vmess://')) {
    try {
      const b64 = raw.trim().slice(8).split('?')[0].split('#')[0]
      const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4)
      const data = JSON.parse(atob(padded.replace(/-/g, '+').replace(/_/g, '/')))
      return {
        protocol: 'vmess',
        host: String(data.add || ''),
        port: Number(data.port) || 443,
        label: String(data.ps || ''),
      }
    } catch {
      return null
    }
  }
  return null
}

function parseSocks5Uri(raw) {
  try {
    const parsed = new URL(raw.trim())
    return {
      host: parsed.hostname || '',
      port: Number(parsed.port) || 1080,
    }
  } catch {
    return null
  }
}

function onPasteShareUri() {
  setTimeout(applyShareUri, 0)
}

function triggerQrUpload() {
  qrInputRef.value?.click()
}

async function onQrFileChange(event) {
  const file = event.target?.files?.[0]
  event.target.value = ''
  if (!file) return
  decodingQr.value = true
  try {
    const text = await decodeQrFromFile(file)
    const normalized = normalizeShareLink(text)
    if (!normalized.ok) {
      ElMessage.warning(normalized.reason || '二维码内容不是代理链接')
      return
    }
    form.value.share_uri = normalized.uri
    applyShareUri()
    ElMessage.success('二维码已识别')
  } catch (err) {
    ElMessage.error(err.message || '二维码识别失败')
  } finally {
    decodingQr.value = false
  }
}

function applyShareUri() {
  const raw = form.value.share_uri?.trim()
  if (!raw) {
    detectedProtocol.value = 'socks5'
    return
  }
  const normalized = normalizeShareLink(raw)
  if (normalized.ok && normalized.uri !== raw) {
    form.value.share_uri = normalized.uri
  }
  const effective = normalized.ok ? normalized.uri : raw
  const lower = effective.toLowerCase()
  if (lower.startsWith('vmess://') || lower.startsWith('vless://')) {
    detectedProtocol.value = lower.startsWith('vmess://') ? 'vmess' : 'vless'
    const info = parseGatewayUri(effective)
    if (info) {
      form.value.host = info.host
      form.value.port = info.port
      if (info.label && !form.value.label?.trim()) {
        form.value.label = info.label
      }
    }
    return
  }
  if (!lower.startsWith('socks5://')) return
  detectedProtocol.value = 'socks5'
  try {
    const parsed = new URL(effective)
    form.value.host = parsed.hostname || ''
    form.value.port = Number(parsed.port) || 1080
    form.value.username = decodeURIComponent(parsed.username || '')
    form.value.password = decodeURIComponent(parsed.password || '')
    if (parsed.hash && parsed.hash.length > 1 && !form.value.label?.trim()) {
      form.value.label = decodeURIComponent(parsed.hash.slice(1))
    }
  } catch {
    ElMessage.warning('无法解析 SOCKS5 链接')
  }
}

async function loadData() {
  loading.value = true
  try {
    const [listRes, statsRes] = await Promise.all([
      api.get('/admin/proxies'),
      api.get('/admin/proxies/stats'),
    ])
    proxies.value = listRes.data
    stats.value = statsRes.data
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '加载代理池失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  detectedProtocol.value = 'socks5'
  form.value = emptyForm()
  showForm.value = true
}

function openEdit(row) {
  editing.value = row
  detectedProtocol.value = row.protocol || 'socks5'
  form.value = {
    share_uri: '',
    host: row.host,
    port: row.port,
    username: row.username || '',
    password: '',
    label: row.label || '',
    enabled: row.enabled,
  }
  showForm.value = true
}

async function saveProxy() {
  applyShareUri()
  const shareUri = form.value.share_uri?.trim()
  const normalized = normalizeShareLink(shareUri)
  const effectiveUri = normalized.ok ? normalized.uri : shareUri
  const isGateway = effectiveUri && (effectiveUri.toLowerCase().startsWith('vmess://') || effectiveUri.toLowerCase().startsWith('vless://'))
  if (!effectiveUri && !form.value.host?.trim()) {
    ElMessage.warning('请粘贴分享链接或填写主机')
    return
  }
  if (shareUri && !normalized.ok) {
    ElMessage.warning(normalized.reason || '链接格式无法识别')
    return
  }
  if (isGateway && !parseGatewayUri(effectiveUri)) {
    ElMessage.warning('无法解析 vmess/vless 链接，请检查是否完整')
    return
  }
  saving.value = true
  try {
    const payload = {
      label: form.value.label?.trim() || '',
      enabled: form.value.enabled,
    }
    if (effectiveUri) {
      payload.share_uri = effectiveUri
    } else {
      payload.host = form.value.host.trim()
      payload.port = form.value.port
      payload.username = form.value.username?.trim() || ''
    }
    if (editing.value) {
      if (form.value.password) payload.password = form.value.password
      await api.put(`/admin/proxies/${editing.value.id}`, payload)
      ElMessage.success('已更新')
    } else {
      if (!effectiveUri) payload.password = form.value.password || ''
      await api.post('/admin/proxies', payload)
      ElMessage.success('已添加')
    }
    showForm.value = false
    await loadData()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function pruneBad() {
  const ids = stats.value?.prune_candidate_ids || []
  if (!ids.length) {
    ElMessage.info('当前没有建议删除的代理节点')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将删除 ${ids.length} 条高失败率/异常代理，确定继续？`,
      '删除代理',
      { type: 'warning' },
    )
    pruning.value = true
    await api.post('/admin/proxies/prune', { mode: 'high_failure', ids: [] })
    ElMessage.success('已删除问题代理')
    await loadData()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.response?.data?.detail || '删除失败')
    }
  } finally {
    pruning.value = false
  }
}

async function removeProxyById(id) {
  const row = proxies.value.find((p) => p.id === id) || highFailure.value.find((p) => p.id === id)
  if (!row) return
  await removeProxy(row)
}

async function reloadGateway() {
  reloadingGateway.value = true
  try {
    await api.post('/admin/proxies/reload-gateway')
    ElMessage.success('网关已重载')
    await loadData()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '网关重载失败')
  } finally {
    reloadingGateway.value = false
  }
}

async function removeProxy(row) {
  try {
    await ElMessageBox.confirm(`确定删除 ${row.masked_url} ？`, '删除代理', { type: 'warning' })
    await api.delete(`/admin/proxies/${row.id}`)
    ElMessage.success('已删除')
    await loadData()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.response?.data?.detail || '删除失败')
    }
  }
}

async function checkOne(row) {
  checkingId.value = row.id
  try {
    const { data } = await api.post(`/admin/proxies/${row.id}/check`)
    const idx = proxies.value.findIndex((p) => p.id === row.id)
    if (idx >= 0) proxies.value[idx] = data
    await loadData()
    ElMessage.success(data.health_status === 'healthy' ? '连接正常' : '连接异常')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '检测失败')
  } finally {
    checkingId.value = null
  }
}

async function checkAll() {
  checkingAll.value = true
  try {
    const { data } = await api.post('/admin/proxies/check-all')
    proxies.value = data
    await loadData()
    ElMessage.success('全部检测完成')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '检测失败')
  } finally {
    checkingAll.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.reco-card .reco-body {
  padding: 16px;
}
.reco-list {
  margin: 0 0 12px;
  padding-left: 20px;
  line-height: 1.7;
  font-size: 14px;
}
.proxy-summary {
  font-size: 13px;
  color: #666;
  margin-bottom: 12px;
}
.fail-table {
  margin-top: 4px;
}
.empty-tip {
  color: #888;
  font-size: 13px;
  margin: 0;
}
.rate-bad {
  color: #dc2626;
  font-weight: 600;
}
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
}

.stat-card {
  background: #fff;
  border: 1px solid #ececec;
  border-radius: 12px;
  padding: 14px 16px;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: #111;
}

.stat-label {
  margin-top: 4px;
  font-size: 12px;
  color: #666;
}

.table-body {
  padding-top: 0;
}

.error-text {
  color: #b42318;
  font-size: 12px;
  word-break: break-all;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.form-tip {
  margin: 6px 0 0;
  font-size: 12px;
  color: #888;
  line-height: 1.4;
}

.parse-preview {
  margin-bottom: 12px;
}

.parse-preview :deep(.el-alert__content) {
  font-size: 13px;
  line-height: 1.5;
}

.import-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.import-actions {
  display: flex;
  justify-content: flex-end;
}

.qr-file-input {
  display: none;
}
</style>
