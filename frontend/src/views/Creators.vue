<template>
  <div class="page">
  <div class="page page--fill">
      <div class="card-top">
        <div class="top-main">
          <h2 class="title">监控博主</h2>
          <p class="policy-line">
            <span class="policy-label">采集策略</span>
            已采集不重复 · 历史采集自动拉取博主全部视频并按播放阈值入库 · 10 天内每 3 天增量更新
            · {{ auth.isSuperAdmin ? '超级管理员可管理全部博主' : '可查看全部博主，仅可删除/采集自己添加的' }}
          </p>
        </div>
        <button class="tm-btn-primary" @click="openAddDialog">添加博主</button>
      </div>

      <div class="table-wrap">
        <el-table :data="creators" v-loading="loading">
          <el-table-column prop="tiktok_username" label="博主" min-width="140">
            <template #default="{ row }">@{{ row.tiktok_username }}</template>
          </el-table-column>
          <el-table-column prop="owner_username" label="所属账号" width="120">
            <template #default="{ row }">{{ row.owner_username || '-' }}</template>
          </el-table-column>
          <el-table-column prop="video_count" label="视频数" width="90" />
          <el-table-column label="数据采集" width="120">
            <template #default="{ row }">
              <CreatorCollectionStatus :creator="row" :scraping="isScraping(row.id)" />
            </template>
          </el-table-column>
          <el-table-column label="最近采集" width="170">
            <template #default="{ row }">
              {{ row.last_scraped_at ? formatDate(row.last_scraped_at) : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="操作" min-width="300" fixed="right">
            <template #default="{ row }">
              <div class="row-actions">
                <CreatorScrapeBtn
                  v-if="canManage(row)"
                  :creator-id="row.id"
                  :scraping-historical="isScraping(row.id, 'historical')"
                  :scraping-daily="isScraping(row.id, 'daily')"
                  :scrape-url="`/creators/${row.id}/scrape/historical`"
                  :daily-url="`/creators/${row.id}/scrape`"
                  show-daily
                  @start="(mode) => trackScrape(row, mode)"
                  @done="(data) => onScrapeDone(row.id, data)"
                  @background="onScrapeBackground(row.id)"
                />
                <router-link
                  :to="videosLink({ creator_id: row.id })"
                  class="tm-btn-ghost sm"
                >视频</router-link>
                <button
                  v-if="canManage(row)"
                  type="button"
                  class="tm-btn-danger sm"
                  @click="handleDelete(row)"
                >删除</button>
                <span v-if="!canManage(row)" class="readonly-hint">仅可查看</span>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="total > 0" class="table-pager">
          <span class="pager-total">共 {{ total }} 条</span>
          <el-pagination
          <el-table-column label="操作" min-width="300">
            background
            small
            layout="prev, pager, next"
            :total="total"
            :page-size="pageSize"
            :current-page="page"
            @current-change="onPageChange"
          />
        </div>
      </div>
    </div>

    <el-dialog v-model="showAdd" title="添加监控博主" width="560px" @closed="resetAddDialog">
      <el-form label-width="0">
        <el-form-item>
          <el-input
            v-model="pasteText"
            type="textarea"
            :rows="7"
            placeholder="粘贴博主列表、分享文案或 TikTok 链接，支持多个 @username&#10;也可每行一个 @username 直接添加"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="parsing" @click="handleParsePaste">AI 提取博主</el-button>
          <span class="parse-hint">自动识别 @username 与 tiktok.com/@username 链接</span>
        </el-form-item>

        <div v-if="extractedUsernames.length" class="extract-preview">
          <div class="preview-head">
            <span>已识别 {{ extractedUsernames.length }} 个博主</span>
            <button type="button" class="clear-btn" @click="extractedUsernames = []">清空</button>
          </div>
          <div class="username-tags">
            <span v-for="(name, idx) in extractedUsernames" :key="`${name}-${idx}`" class="username-tag">
              {{ name }}
              <button type="button" class="tag-remove" @click="removeExtracted(idx)">×</button>
            </span>
          </div>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="showAdd = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="handleBatchAdd">
          {{ addButtonLabel }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api'
import { formatDate } from '@/utils/format'
import CreatorScrapeBtn from '@/components/CreatorScrapeBtn.vue'
import CreatorCollectionStatus from '@/components/CreatorCollectionStatus.vue'
import { useCreatorScrapePolling } from '@/composables/useCreatorScrapePolling'
import { validateCreatorUsername, extractUsernamesFromText } from '@/utils/creatorUsername'
import { canManageCreator } from '@/utils/creatorPermissions'
import { videosLink } from '@/utils/navLinks'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const creators = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const showAdd = ref(false)
const pasteText = ref('')
const extractedUsernames = ref([])
const parsing = ref(false)
const adding = ref(false)

const addButtonLabel = computed(() => {
  const count = extractedUsernames.value.length || collectUsernames().length
  return count > 1 ? `批量添加 (${count})` : '确认添加'
})

function canManage(row) {
  return canManageCreator(row)
}

function openAddDialog() {
  resetAddDialog()
  showAdd.value = true
}

function resetAddDialog() {
  pasteText.value = ''
  extractedUsernames.value = []
}

function removeExtracted(index) {
  extractedUsernames.value = extractedUsernames.value.filter((_, i) => i !== index)
}

function collectUsernames() {
  if (extractedUsernames.value.length) return [...extractedUsernames.value]
  const fromText = extractUsernamesFromText(pasteText.value)
  if (fromText.length) return fromText
  const check = validateCreatorUsername(pasteText.value.trim())
  return check.ok ? [check.value] : []
}

            placeholder="粘贴博主列表、分享文案或 TikTok 链接&#10;每行一个 username，无需加 @，系统会自动补全"
  if (!opts.silent) loading.value = true
  try {
    const { data } = await api.get('/creators', {
      params: { page: page.value, page_size: pageSize.value },
    })
    creators.value = data.items || []
    total.value = data.total || 0
  } finally {
    if (!opts.silent) loading.value = false
          <span class="parse-hint">支持 username、@username 或 tiktok.com/@username 链接</span>
}

const { isScraping, trackScrape, onScrapeDone, onScrapeBackground } = useCreatorScrapePolling({
  refresh: loadCreators,
  findCreator: (id) => creators.value.find((c) => c.id === id),
})

async function handleParsePaste() {
  const text = pasteText.value?.trim()
  if (!text) {
    ElMessage.warning('请先粘贴博主信息')
    return
  }
  parsing.value = true
  try {
    const { data } = await api.post('/creators/parse-paste', { pasted_text: text })
    extractedUsernames.value = data.usernames || []
    ElMessage.success(`已提取 ${extractedUsernames.value.length} 个博主`)
  } catch (err) {
    const local = extractUsernamesFromText(text)
    if (local.length) {
      extractedUsernames.value = local
      ElMessage.success(`已从文本识别 ${local.length} 个博主`)
    } else {
      ElMessage.error(err?.response?.data?.detail || err?.message || '提取失败')
    }
  } finally {
    parsing.value = false
  }
}

async function handleBatchAdd() {
  const list = collectUsernames()
  if (!list.length) {
    ElMessage.warning('请输入或提取至少一个 @username')
    return
  }

  adding.value = true
  try {
    if (list.length === 1) {
      await api.post('/creators', { tiktok_username: list[0] })
      ElMessage.success('添加成功，可点击「采集数据」开始拉取')
    } else {
      const { data } = await api.post('/creators/batch', { tiktok_usernames: list })
      if (data.succeeded && data.failed) {
        ElMessage.warning(`成功 ${data.succeeded} 个，失败 ${data.failed} 个`)
      } else if (data.succeeded) {
        ElMessage.success(`已成功添加 ${data.succeeded} 个博主`)
      } else {
        ElMessage.error('全部添加失败，请检查账号是否有效或已存在')
      }
    }
    showAdd.value = false
    page.value = 1
    await loadCreators()
  } finally {
    adding.value = false
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除 @${row.tiktok_username}？`, '确认')
  try {
    await api.delete(`/creators/${row.id}`)
    ElMessage.success('已删除')
    if (creators.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    await loadCreators()
  } catch (e) {
    const msg = e.response?.data?.detail || '删除失败'
    ElMessage.error(typeof msg === 'string' ? msg : '无权删除该博主')
  }
}

function onPageChange(p) {
  page.value = p
  loadCreators()
}

onMounted(loadCreators)
</script>

<style scoped>
.creators-card {
  box-shadow: var(--tm-shadow-sm);
}

.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 22px 24px 18px;
  border-bottom: 1px solid var(--tm-border);
  background: var(--tm-surface);
}

.top-main {
  min-width: 0;
}

.title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--tm-text);
}

.policy-line {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--tm-text-muted);
}

.policy-label {
  display: inline-block;
  margin-right: 6px;
  padding: 2px 8px;
  border-radius: var(--tm-radius-pill);
  background: var(--tm-surface-muted);
  color: var(--tm-text-secondary);
  font-weight: 600;
  font-size: 11px;
}

.table-wrap {
  padding: 0;
  background: var(--tm-surface);
}

.table-pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 24px 16px;
  border-top: 1px solid var(--tm-border);
}

.pager-total {
  font-size: 12px;
  color: var(--tm-text-muted);
  font-weight: 500;
}

.parse-hint {
  margin-left: 10px;
  font-size: 12px;
  color: var(--tm-text-muted);
}

.extract-preview {
  margin-top: 4px;
  padding: 12px 14px;
  border-radius: var(--tm-radius-md);
  background: #f8f7fb;
  border: 1px solid rgba(123, 67, 151, 0.12);
}

.preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--tm-text-secondary);
}

.clear-btn {
  border: none;
  background: transparent;
  color: var(--tm-purple);
  font-size: 12px;
  cursor: pointer;
}

.username-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.username-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px 4px 10px;
  border-radius: var(--tm-radius-pill);
  background: var(--tm-surface);
  border: 1px solid var(--tm-border);
  font-size: 12px;
  font-weight: 600;
  color: var(--tm-text);
}

.tag-remove {
  width: 18px;
  height: 18px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--tm-text-muted);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
}

.tag-remove:hover {
  background: rgba(0, 0, 0, 0.06);
  color: var(--tm-text);
}

.row-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.tm-btn-danger.sm {
  height: 32px;
  padding: 0 14px;
  border: 1.5px solid rgba(220, 60, 60, 0.3);
  border-radius: var(--tm-radius-pill);
  background: transparent;
  color: #c0392b;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
  flex-shrink: 0;
  white-space: nowrap;
}

.tm-btn-danger.sm:hover {
  background: rgba(220, 60, 60, 0.08);
  border-color: rgba(220, 60, 60, 0.5);
}

.tm-btn-ghost.sm {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 14px;
  border-radius: var(--tm-radius-pill);
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
    ElMessage.warning('请输入或提取至少一个博主用户名')
  border: 1.5px solid var(--tm-border);
  background: transparent;
  flex-shrink: 0;
}

.readonly-hint {
  font-size: 12px;
  color: var(--tm-text-muted);
}

.creators-card :deep(.el-table) {
  --el-table-border-color: transparent;
  --el-table-header-bg-color: var(--tm-surface);
  --el-table-tr-bg-color: var(--tm-surface);
  --el-table-row-hover-bg-color: #fafafa;
  --el-table-bg-color: var(--tm-surface);
  box-shadow: none;
  background: transparent;
}
      const { data } = await api.post('/creators/batch', { tiktok_usernames: list }, { timeout: 180000 })
.creators-card :deep(.el-table__inner-wrapper::before),
.creators-card :deep(.el-table__border-left-patch),
.creators-card :deep(.el-table__border-right-patch) {
  display: none;
}

.creators-card :deep(.el-table th.el-table__cell) {
  padding: 14px 0 14px 24px;
  font-size: 12px;
  font-weight: 600;
  color: var(--tm-text-muted);
  border-bottom: 1px solid var(--tm-border);
  background: var(--tm-surface);
}

.creators-card :deep(.el-table td.el-table__cell) {
  padding: 16px 0 16px 24px;
  border-bottom: 1px solid #f2f2f2;
  background: var(--tm-surface);
}

.creators-card :deep(.el-table .el-table__cell:last-child) {
  padding-right: 24px;
}

.creators-card :deep(.el-table__body tr:last-child td.el-table__cell) {
  border-bottom: none;
}

.creators-card :deep(.el-table__fixed-right-patch) {
  background: var(--tm-surface);
}
</style>

