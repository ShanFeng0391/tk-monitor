<template>
  <div class="page">
    <div class="toolbar">
      <span class="refresh-hint">每 15 秒自动刷新 · 当前查看自：{{ status?.current_node_label || '—' }}</span>
      <button class="tm-btn-ghost sm" :disabled="loading" @click="loadData">
        {{ loading ? '刷新中…' : '立即刷新' }}
      </button>
    </div>

    <div v-if="status?.overall_status" class="overall-banner" :class="overallClass">
      <strong>{{ overallTitle }}</strong>
      <span v-if="!status.alerts?.length">各节点与数据层运行正常。</span>
    </div>

    <div v-if="status?.alerts?.length" class="alert-box">
      <div class="alert-title">需要关注</div>
      <ul>
        <li v-for="(msg, idx) in status.alerts" :key="idx">{{ msg }}</li>
      </ul>
    </div>

    <div class="node-grid">
      <div
        v-for="node in status?.nodes || []"
        :key="node.node_id"
        class="node-card tm-card"
        :class="{ 'node-card--current': node.is_current_node }"
      >
        <div class="node-head">
          <span class="node-name">{{ node.label }}</span>
          <span class="tm-tag" :class="nodeOnlineClass(node)">{{ nodeOnlineLabel(node) }}</span>
        </div>
        <div class="node-meta" v-if="node.is_current_node">（当前浏览器连的是这台 API）</div>
        <div class="node-rows">
          <div class="row">
            <span>Worker 在线</span>
            <strong :class="workerClass(node)">{{ node.worker_online }} / {{ node.worker_expected }}</strong>
          </div>
          <div class="row">
            <span>Beat 调度</span>
            <strong>{{ beatLabel(node) }}</strong>
          </div>
          <div class="row">
            <span>sing-box 网关</span>
            <strong>{{ node.singbox_running ? '运行中' : '未运行' }}</strong>
          </div>
          <div class="row">
            <span>最近心跳</span>
            <strong>{{ heartbeatLabel(node) }}</strong>
          </div>
        </div>
      </div>
    </div>

    <div class="tm-card section-card">
      <div class="tm-card-header">
        <span class="title">数据层（轻量 #1）</span>
      </div>
      <div class="tm-card-body data-layer">
        <div class="dl-item">
          <span>PostgreSQL</span>
          <span class="tm-tag" :class="tagClass(status?.data_layer?.database)">{{ status?.data_layer?.database || '—' }}</span>
        </div>
        <div class="dl-item">
          <span>Redis</span>
          <span class="tm-tag" :class="tagClass(status?.data_layer?.redis)">{{ status?.data_layer?.redis || '—' }}</span>
        </div>
        <div class="dl-item">
          <span>Celery 总 Worker</span>
          <strong>{{ status?.celery?.total_workers_online ?? 0 }}</strong>
        </div>
        <div class="dl-item">
          <span>对端 API</span>
          <span>{{ peerLabel }}</span>
        </div>
      </div>
    </div>

    <div class="tm-card section-card deploy-card">
      <div class="tm-card-header">
        <span class="title">代码更新（本节点）</span>
        <div class="header-actions">
          <button
            class="tm-btn-primary sm"
            :disabled="!deploy.enabled || deployRunning || deploying"
            @click="confirmDeploy"
          >
            {{ deploying ? '提交中…' : deployRunning ? '更新中…' : '一键更新本节点' }}
          </button>
        </div>
      </div>
      <div class="tm-card-body deploy-body">
        <p v-if="!deploy.enabled" class="deploy-hint warn">
          Web 一键更新未开启。在服务器 <code>.env</code> 中设置
          <code>WEB_DEPLOY_UPDATE_ENABLED=true</code> 并重启 API 后可在此操作。
          也可继续用脚本：<code>{{ deploy.script_hint || '.\\scripts\\update.ps1' }}</code>
        </p>
        <template v-else>
          <p class="deploy-hint">
            更新<strong>当前浏览器所连的这台 API</strong>（{{ deploy.node_label || '—' }}）：
            拉代码 → 构建 → 重启。约 1～3 分钟，期间页面可能短暂断开。
          </p>
          <p class="deploy-hint muted">{{ deploy.peer_hint }}</p>
          <div class="deploy-options">
            <label><input v-model="deployOpts.backendOnly" type="checkbox" :disabled="deployRunning" /> 仅后端</label>
            <label><input v-model="deployOpts.frontendOnly" type="checkbox" :disabled="deployRunning" /> 仅前端</label>
            <label><input v-model="deployOpts.skipGitPull" type="checkbox" :disabled="deployRunning" /> 不 git pull</label>
          </div>
          <div v-if="deploy.state !== 'idle'" class="deploy-status">
            <span class="tm-tag" :class="deployStateClass">{{ deployStateLabel }}</span>
            <span>{{ deploy.message }}</span>
          </div>
          <pre v-if="deploy.log_tail" class="deploy-log">{{ deploy.log_tail }}</pre>
        </template>
      </div>
    </div>

    <p class="cluster-footnote">
      代理池用量与失败率请在
      <router-link to="/admin/proxies">代理池</router-link>
      页面查看与处理。
    </p>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api'

const loading = ref(false)
const status = ref(null)
const deploy = ref({
  enabled: false,
  state: 'idle',
  message: '',
  log_tail: '',
  node_label: '',
  script_hint: '',
  peer_hint: '',
})
const deployOpts = ref({
  backendOnly: false,
  frontendOnly: false,
  skipGitPull: false,
})
const deploying = ref(false)
let timer = null
let deployPollTimer = null

const deployRunning = computed(() => deploy.value.state === 'running')

const deployStateClass = computed(() => {
  const s = deploy.value.state
  if (s === 'success') return 'blue'
  if (s === 'failed') return 'daily-hot'
  if (s === 'running') return 'purple'
  return 'dark'
})

const deployStateLabel = computed(() => {
  const map = {
    idle: '空闲',
    running: '进行中',
    success: '成功',
    failed: '失败',
  }
  return map[deploy.value.state] || deploy.value.state
})

const overallClass = computed(() => {
  const s = status.value?.overall_status
  if (s === 'healthy') return 'ok'
  if (s === 'degraded') return 'warn'
  return 'bad'
})

const overallTitle = computed(() => {
  const map = { healthy: '整体正常', degraded: '部分异常', critical: '严重异常' }
  return map[status.value?.overall_status] || '未知'
})

const peerLabel = computed(() => {
  const p = status.value?.peer_api
  if (!p?.configured) return '未配置（可选）'
  if (p.reachable) return `可达 · ${p.status || 'ok'}`
  return `不可达 · ${p.detail || ''}`
})

function tagClass(v) {
  return v === 'ok' ? 'blue' : 'daily-hot'
}

function nodeOnlineClass(node) {
  if (!node.online) return 'daily-hot'
  return node.worker_status === 'ok' ? 'blue' : 'purple'
}

function nodeOnlineLabel(node) {
  if (!node.online) return '离线'
  if (node.worker_status === 'ok') return '在线'
  if (node.worker_status === 'low') return 'Worker 偏少'
  return '异常'
}

function workerClass(node) {
  if (node.worker_status === 'offline') return 'text-bad'
  if (node.worker_status === 'low') return 'text-warn'
  return 'text-ok'
}

function beatLabel(node) {
  if (!node.beat_should_run) return '本节点不需要'
  return node.beat_online ? '运行中' : '未运行（需处理）'
}

function heartbeatLabel(node) {
  if (!node.online) return '无心跳'
  const sec = node.last_seen_seconds_ago
  if (sec == null) return '刚刚'
  if (sec < 60) return `${sec} 秒前`
  return `${Math.floor(sec / 60)} 分钟前`
}

async function loadDeployStatus() {
  try {
    const { data } = await api.get('/admin/cluster/deploy-update', { skipErrorToast: true })
    deploy.value = data
    if (data.state === 'running' && !deployPollTimer) {
      deployPollTimer = setInterval(loadDeployStatus, 4000)
    }
    if (data.state !== 'running' && deployPollTimer) {
      clearInterval(deployPollTimer)
      deployPollTimer = null
      if (data.state === 'success') {
        loadData()
      }
    }
  } catch {
    /* 旧版 API 无此接口时忽略 */
  }
}

async function confirmDeploy() {
  if (deployOpts.value.backendOnly && deployOpts.value.frontendOnly) {
    ElMessage.warning('不能同时选「仅后端」和「仅前端」')
    return
  }
  try {
    await ElMessageBox.confirm(
      '将更新并重启本节点 API（及 Worker/Beat）。期间管理页可能短暂无法访问，确定继续？',
      '一键更新本节点',
      { type: 'warning', confirmButtonText: '开始更新', cancelButtonText: '取消' },
    )
    deploying.value = true
    await api.post('/admin/cluster/deploy-update', {
      confirm: true,
      backend_only: deployOpts.value.backendOnly,
      frontend_only: deployOpts.value.frontendOnly,
      skip_git_pull: deployOpts.value.skipGitPull,
      quick: true,
    })
    ElMessage.success('更新已在后台启动，请稍候…')
    await loadDeployStatus()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.response?.data?.detail || '启动更新失败')
    }
  } finally {
    deploying.value = false
  }
}

async function loadData() {
  loading.value = true
  try {
    const { data } = await api.get('/admin/cluster/status')
    status.value = data
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '加载集群状态失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
  loadDeployStatus()
  timer = setInterval(loadData, 15000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (deployPollTimer) clearInterval(deployPollTimer)
})
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.refresh-hint {
  font-size: 13px;
  color: var(--tm-muted);
}
.overall-banner {
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 14px;
}
.overall-banner.ok {
  background: #ecfdf5;
  color: #065f46;
}
.overall-banner.warn {
  background: #fffbeb;
  color: #92400e;
}
.overall-banner.bad {
  background: #fef2f2;
  color: #991b1b;
}
.alert-box {
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  padding: 12px 16px;
}
.alert-title {
  font-weight: 600;
  margin-bottom: 8px;
}
.alert-box ul {
  margin: 0;
  padding-left: 20px;
  line-height: 1.6;
}
.node-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}
.node-card {
  padding: 16px;
}
.node-card--current {
  outline: 2px solid #6366f1;
}
.node-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.node-name {
  font-weight: 600;
  font-size: 16px;
}
.node-meta {
  font-size: 12px;
  color: var(--tm-muted);
  margin-bottom: 12px;
}
.node-rows .row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid var(--tm-border);
  font-size: 14px;
}
.text-ok {
  color: #059669;
}
.text-warn {
  color: #d97706;
}
.text-bad {
  color: #dc2626;
}
.section-card .tm-card-body {
  padding: 16px;
}
.data-layer {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.dl-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 14px;
}
.cluster-footnote {
  font-size: 13px;
  color: #666;
  margin: 0;
}
.cluster-footnote a {
  color: #6366f1;
  text-decoration: none;
}
.deploy-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.deploy-hint {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #444;
}
.deploy-hint.warn {
  color: #92400e;
  background: #fffbeb;
  padding: 10px 12px;
  border-radius: 8px;
}
.deploy-hint.muted {
  color: #888;
  font-size: 12px;
}
.deploy-hint code {
  font-size: 12px;
  background: #f3f4f6;
  padding: 1px 4px;
  border-radius: 4px;
}
.deploy-options {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 13px;
}
.deploy-options label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
.deploy-status {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.deploy-log {
  margin: 0;
  max-height: 160px;
  overflow: auto;
  background: #111;
  color: #e5e7eb;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
}
.header-actions {
  display: flex;
  gap: 8px;
}
</style>
