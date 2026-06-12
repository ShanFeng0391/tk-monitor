<template>
  <div class="page">
    <div class="tm-card">
      <div class="tm-card-header">
        <span class="title">监控分组</span>
        <button class="tm-btn-primary" @click="openCreate">新建分组</button>
      </div>
      <div class="tm-card-body">
        <div class="collection-list">
          <article v-for="group in groups" :key="group.id" class="collection-card">
            <div class="col-head">
              <div>
                <h3>{{ group.name }}</h3>
                <p>{{ group.description || '管理员监控分组' }}</p>
              </div>
              <div class="col-actions">
                <button class="tm-btn-ghost" @click="openEdit(group)">编辑</button>
                <button class="tm-btn-ghost" @click="openAddCreator(group)">添加博主</button>
                <button class="tm-btn-ghost danger" @click="removeGroup(group)">删除</button>
              </div>
            </div>
            <div class="thresholds">
              <span>历史 ≥ {{ formatNum(group.historical_view_threshold) }}</span>
              <span>平均增速 ≥ {{ formatVelocity(group.daily_hot_avg_growth_threshold) }}/分</span>
              <span>博主 {{ group.creator_count }}/{{ group.max_creators }}</span>
            </div>
            <div v-if="creatorsMap[group.id]?.length" class="creators-table-wrap">
              <table class="creators-table">
                <thead>
                  <tr><th>博主</th><th>视频</th><th>数据采集</th><th>操作</th></tr>
                </thead>
                <tbody>
                  <tr v-for="c in creatorsMap[group.id]" :key="c.id">
                    <td>@{{ c.tiktok_username }}</td>
                    <td>{{ c.video_count }}</td>
                    <td>
                      <CreatorCollectionStatus :creator="c" :scraping="isScraping(c.id)" />
                    </td>
                    <td class="actions-cell">
                      <CreatorScrapeBtn
                        :creator-id="c.id"
                        :scraping-historical="isScraping(c.id, 'historical')"
                        :scrape-url="`/groups/${group.id}/creators/${c.id}/scrape/historical`"
                        @start="() => trackScrape(c, 'historical')"
                        @done="(data) => onScrapeDone(c.id, data)"
                        @background="onScrapeBackground(c.id)"
                      />
                      <button class="icon-btn" @click="removeCreator(group.id, c.id)">×</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        </div>
      </div>
    </div>

    <el-dialog v-model="showForm" :title="editing ? '编辑分组' : '新建分组'" width="480px">
      <el-form label-width="120px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" /></el-form-item>
        <el-form-item label="历史爆款阈值"><el-input-number v-model="form.historical_view_threshold" :min="1000" :step="10000" /></el-form-item>
        <el-form-item label="平均流量增速">
          <el-input-number v-model="form.daily_hot_avg_growth_threshold" :min="0" :step="10" :precision="1" />
          <span class="unit">播放/分钟</span>
        </el-form-item>
        <el-form-item label="采集窗口 h"><el-input-number v-model="form.scrape_window_hours" :min="1" /></el-form-item>
        <el-form-item label="博主上限"><el-input-number v-model="form.max_creators" :min="1" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveGroup">保存</el-button>
      </template>
    </el-dialog>

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

const groups = ref([])
const creatorsMap = ref({})
const showForm = ref(false)
const showCreator = ref(false)
const editing = ref(null)
const activeGroupId = ref(null)
const saving = ref(false)
const newUsername = ref('')
const addingCreator = ref(false)

const defaultForm = () => ({
  name: '',
  description: '',
  historical_view_threshold: 100000,
  daily_hot_avg_growth_threshold: 50,
  growth_window_minutes: 30,
  scrape_window_hours: 30,
  max_creators: 999,
})
const form = ref(defaultForm())

async function loadAll(opts = {}) {
  const { data } = await api.get('/groups')
  groups.value = data
  const map = {}
  await Promise.all(data.map(async (g) => {
    const res = await api.get(`/groups/${g.id}/creators`)
    map[g.id] = res.data
  }))
  creatorsMap.value = map
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

function openEdit(group) {
  editing.value = group
  form.value = { ...group }
  showForm.value = true
}

async function saveGroup() {
  saving.value = true
  try {
    if (editing.value) {
      await api.put(`/groups/${editing.value.id}`, form.value)
    } else {
      await api.post('/groups', form.value)
    }
    ElMessage.success('已保存')
    showForm.value = false
    await loadAll()
  } finally {
    saving.value = false
  }
}

async function removeGroup(group) {
  await ElMessageBox.confirm(`删除分组「${group.name}」？`, '确认')
  await api.delete(`/groups/${group.id}`)
  await loadAll()
}

function openAddCreator(group) {
  activeGroupId.value = group.id
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
    await api.post(`/groups/${activeGroupId.value}/creators`, { tiktok_username: check.value })
    ElMessage.success('已添加')
    showCreator.value = false
    await loadAll()
  } finally {
    addingCreator.value = false
  }
}

async function removeCreator(groupId, creatorId) {
  await api.delete(`/groups/${groupId}/creators/${creatorId}`)
  await loadAll()
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
.col-head { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.col-head h3 { margin: 0; font-size: 17px; }
.col-head p { margin: 6px 0 0; font-size: 13px; color: var(--tm-text-muted); }
.col-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.thresholds { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 14px; font-size: 12px; color: var(--tm-text-secondary); }
.thresholds span { background: var(--tm-surface); padding: 4px 10px; border-radius: var(--tm-radius-pill); }
.creators-table-wrap { margin-top: 14px; overflow-x: auto; }
.creators-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.creators-table th, .creators-table td { padding: 10px 8px; text-align: left; border-bottom: 1px solid var(--tm-border); }
.creators-table th { color: var(--tm-text-muted); font-weight: 600; font-size: 12px; }
.actions-cell { display: flex; align-items: center; gap: 8px; }
.icon-btn { border: none; background: none; cursor: pointer; color: var(--tm-text-muted); font-size: 18px; }
.status { font-size: 12px; font-weight: 600; }
.status.ok { color: var(--tm-purple); }
.status.pending { color: var(--tm-orange); }
.status.running { color: #2563eb; animation: scrape-pulse 1.5s ease-in-out infinite; }

@keyframes scrape-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}
.danger:hover { border-color: #e55 !important; color: #e55 !important; }

.hint {
  margin-top: 10px;
  font-size: 12px;
  color: var(--tm-text-muted);
}
</style>
