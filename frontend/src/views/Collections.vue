<template>
  <div class="page">
    <div class="tm-card">
      <div class="tm-card-header">
        <span class="title">监控合集</span>
        <button class="tm-btn-primary" @click="openCreate">新建合集</button>
      </div>
      <div class="tm-card-body">
        <div v-if="loading" class="loading">加载中...</div>
        <div v-else-if="!collections.length" class="empty">
          <p>还没有监控合集，创建一个并设置专属阈值</p>
          <button class="tm-btn-primary" @click="openCreate">创建第一个合集</button>
        </div>

        <div v-else class="collection-list">
          <article v-for="col in collections" :key="col.id" class="collection-card">
            <div class="col-head">
              <div>
                <h3>{{ col.name }}</h3>
                <p>{{ col.description || '暂无描述' }}</p>
              </div>
              <div class="col-actions">
                <button class="tm-btn-ghost" @click="openEdit(col)">编辑阈值</button>
                <button class="tm-btn-ghost" @click="openAddCreator(col)">添加博主</button>
                <button class="tm-btn-ghost danger" @click="removeCollection(col)">删除</button>
              </div>
            </div>

            <div class="thresholds">
              <span>历史爆款 ≥ {{ formatNum(col.historical_view_threshold) }}</span>
              <span>平均增速 ≥ {{ formatVelocity(col.daily_hot_avg_growth_threshold) }}/分</span>
              <span>博主 {{ col.creator_count }}/{{ col.max_creators }}</span>
            </div>

            <div v-if="creatorsMap[col.id]?.length" class="creators-table-wrap">
              <table class="creators-table">
                <thead>
                  <tr>
                    <th>博主</th>
                    <th>视频</th>
                    <th>数据采集</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="c in creatorsMap[col.id]" :key="c.id">
                    <td>@{{ c.tiktok_username }}</td>
                    <td>{{ c.video_count }}</td>
                    <td>
                      <CreatorCollectionStatus :creator="c" :scraping="isScraping(c.id)" />
                    </td>
                    <td class="actions-cell">
                      <CreatorScrapeBtn
                        v-if="canManage(c)"
                        :creator-id="c.id"
                        :scraping-historical="isScraping(c.id, 'historical')"
                        :scrape-url="`/collections/${col.id}/creators/${c.id}/scrape/historical`"
                        @start="() => trackScrape(c, 'historical')"
                        @done="(data) => onScrapeDone(c.id, data)"
                        @background="onScrapeBackground(c.id)"
                      />
                      <button
                        v-if="canManage(c)"
                        class="icon-btn"
                        title="移除博主"
                        @click="removeCreator(col.id, c.id)"
                      >×</button>
                      <span v-if="!canManage(c)" class="readonly-hint">仅可查看</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <router-link :to="`/collections/${col.id}/hot`" class="view-hot">
              查看合集内当日热门 →
            </router-link>
          </article>
        </div>
      </div>
    </div>

    <!-- 创建/编辑合集 -->
    <el-dialog v-model="showForm" :title="editing ? '编辑合集' : '新建合集'" width="480px">
      <el-form label-width="120px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" /></el-form-item>
        <el-form-item label="历史爆款阈值"><el-input-number v-model="form.historical_view_threshold" :min="1000" :step="10000" /></el-form-item>
        <el-form-item label="平均流量增速">
          <el-input-number v-model="form.daily_hot_avg_growth_threshold" :min="0" :step="10" :precision="1" />
          <span class="unit">播放/分钟</span>
        </el-form-item>
        <el-form-item label="博主上限"><el-input-number v-model="form.max_creators" :min="1" :max="100" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveCollection">保存</el-button>
      </template>
    </el-dialog>

    <!-- 添加博主 -->
    <el-dialog v-model="showCreator" title="添加博主" width="400px">
      <el-input v-model="newUsername" placeholder="@username" @keyup.enter="addCreator" />
      <p class="hint">须以 @ 开头，例如 @tiktok</p>
      <template #footer>
        <el-button @click="showCreator = false">取消</el-button>
        <el-button type="primary" :loading="addingCreator" @click="addCreator">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api'
import { formatNum, formatVelocity } from '@/utils/format'
import CreatorScrapeBtn from '@/components/CreatorScrapeBtn.vue'
import CreatorCollectionStatus from '@/components/CreatorCollectionStatus.vue'
import { useCreatorScrapePolling } from '@/composables/useCreatorScrapePolling'
import { validateCreatorUsername } from '@/utils/creatorUsername'
import { canManageCreator } from '@/utils/creatorPermissions'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const collections = ref([])
const creatorsMap = ref({})
const loading = ref(false)
const showForm = ref(false)
const showCreator = ref(false)
const editing = ref(null)
const activeColId = ref(null)
const saving = ref(false)
const newUsername = ref('')
const addingCreator = ref(false)

const defaultForm = () => ({
  name: '',
  description: '',
  historical_view_threshold: 100000,
  daily_hot_avg_growth_threshold: 50,
  max_creators: 10,
})
const form = ref(defaultForm())

function canManage(creator) {
  return canManageCreator(creator)
}

async function loadAll(opts = {}) {
  if (!opts.silent) loading.value = true
  try {
    const { data } = await api.get('/collections')
    collections.value = data
    const map = {}
    await Promise.all(data.map(async (col) => {
      const res = await api.get(`/collections/${col.id}/creators`)
      map[col.id] = res.data
    }))
    creatorsMap.value = map
  } finally {
    if (!opts.silent) loading.value = false
  }
}

function findCreator(id) {
  for (const list of Object.values(creatorsMap.value)) {
    const found = list.find((c) => c.id === id)
    if (found) return found
  }
  return undefined
}

const { isScraping, trackScrape, onScrapeDone, onScrapeBackground } = useCreatorScrapePolling({
  refresh: loadAll,
  findCreator,
})

function openCreate() {
  editing.value = null
  form.value = defaultForm()
  showForm.value = true
}

function openEdit(col) {
  editing.value = col
  form.value = { ...col }
  showForm.value = true
}

async function saveCollection() {
  if (!form.value.name.trim()) return
  saving.value = true
  try {
    if (editing.value) {
      await api.put(`/collections/${editing.value.id}`, form.value)
      ElMessage.success('已更新')
    } else {
      await api.post('/collections', form.value)
      ElMessage.success('合集已创建')
    }
    showForm.value = false
    await loadAll()
  } finally {
    saving.value = false
  }
}

async function removeCollection(col) {
  await ElMessageBox.confirm(`删除合集「${col.name}」？`, '确认')
  await api.delete(`/collections/${col.id}`)
  ElMessage.success('已删除')
  await loadAll()
}

function openAddCreator(col) {
  activeColId.value = col.id
  newUsername.value = ''
  showCreator.value = true
}

async function addCreator() {
  const check = validateCreatorUsername(newUsername.value)
  if (!check.ok) {
    ElMessage.warning(check.message)
    return
  }
  addingCreator.value = true
  try {
    await api.post(`/collections/${activeColId.value}/creators`, {
      tiktok_username: check.value,
    })
    ElMessage.success('博主已添加')
    showCreator.value = false
    await loadAll()
  } finally {
    addingCreator.value = false
  }
}

async function removeCreator(colId, creatorId) {
  try {
    await api.delete(`/collections/${colId}/creators/${creatorId}`)
    ElMessage.success('已移除')
    await loadAll()
  } catch (e) {
    const msg = e.response?.data?.detail || '移除失败'
    ElMessage.error(typeof msg === 'string' ? msg : '无权移除该博主')
  }
}

onMounted(loadAll)
</script>

<style scoped>
.collection-list { display: flex; flex-direction: column; gap: 16px; }

.collection-card {
  border: 1px solid var(--tm-border);
  border-radius: var(--tm-radius-md);
  padding: 20px;
  background: var(--tm-surface-muted);
}

.col-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.col-head h3 { margin: 0; font-size: 17px; }
.col-head p { margin: 6px 0 0; font-size: 13px; color: var(--tm-text-muted); }

.col-actions { display: flex; gap: 8px; flex-wrap: wrap; }

.thresholds {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 14px;
  font-size: 12px;
  color: var(--tm-text-secondary);
}

.thresholds span {
  background: var(--tm-surface);
  padding: 4px 10px;
  border-radius: var(--tm-radius-pill);
}

.creators-table-wrap { margin-top: 14px; overflow-x: auto; }
.creators-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.creators-table th,
.creators-table td {
  padding: 10px 8px;
  text-align: left;
  border-bottom: 1px solid var(--tm-border);
}
.creators-table th { color: var(--tm-text-muted); font-weight: 600; font-size: 12px; }
.actions-cell { display: flex; align-items: center; gap: 8px; }
.icon-btn {
  border: none;
  background: none;
  cursor: pointer;
  color: var(--tm-text-muted);
  font-size: 18px;
  line-height: 1;
}
.status { font-size: 12px; font-weight: 600; }
.status.ok { color: var(--tm-purple); }
.status.pending { color: var(--tm-orange); }
.status.running { color: #2563eb; animation: scrape-pulse 1.5s ease-in-out infinite; }

@keyframes scrape-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

.readonly-hint {
  font-size: 12px;
  color: var(--tm-text-muted);
}

.view-hot {
  display: inline-block;
  margin-top: 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--tm-blue);
  text-decoration: none;
}

.view-hot:hover { text-decoration: underline; }

.danger:hover { border-color: #e55 !important; color: #e55 !important; }

.loading, .empty {
  text-align: center;
  padding: 40px;
  color: var(--tm-text-muted);
}

.empty button { margin-top: 16px; }

.hint {
  margin-top: 10px;
  font-size: 12px;
  color: var(--tm-text-muted);
}
</style>
