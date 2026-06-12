<template>
  <div class="page page--fill">
    <div class="tm-card main-card">
      <div class="card-top">
        <el-radio-group v-if="auth.isSuperAdmin" v-model="activeTab" size="small" class="tab-switch">
          <el-radio-button value="creators">博主列表</el-radio-button>
          <el-radio-button value="groups">分组设置</el-radio-button>
        </el-radio-group>
        <div v-else class="card-top-spacer" />
        <div class="top-actions">
          <button v-if="activeTab === 'creators'" class="tm-btn-primary" @click="openAddDialog">添加博主</button>
          <button v-if="activeTab === 'groups' && auth.isSuperAdmin" class="tm-btn-primary" @click="openCreateGroup">新建分组</button>
        </div>
      </div>

      <!-- 博主列表 -->
      <div v-show="activeTab === 'creators'" class="table-wrap">
        <div class="filter-bar">
          <el-select v-model="filterGroupId" clearable placeholder="全部类别" style="width: 180px" @change="onFilterChange">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </div>
        <el-table :data="creators" v-loading="loading">
          <el-table-column prop="tiktok_username" label="博主" min-width="130">
            <template #default="{ row }">@{{ row.tiktok_username }}</template>
          </el-table-column>
          <el-table-column label="博主类别" width="150">
            <template #default="{ row }">
              <el-select
                v-if="canManage(row)"
                :model-value="row.group_id"
                size="small"
                placeholder="选择类别"
                @change="(val) => changeCategory(row, val)"
              >
                <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
              </el-select>
              <span v-else>{{ row.group_name || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="owner_username" label="所属账号" width="110">
            <template #default="{ row }">{{ row.owner_username || '-' }}</template>
          </el-table-column>
          <el-table-column prop="video_count" label="视频数" width="88" class-name="col-video-count" label-class-name="col-video-count" />
          <el-table-column label="数据采集" width="110">
            <template #default="{ row }">
              <CreatorCollectionStatus :creator="row" :scraping="isScraping(row.id)" />
            </template>
          </el-table-column>
          <el-table-column label="Daily 增量" width="148">
            <template #default="{ row }">
              {{ row.last_scraped_at ? formatDate(row.last_scraped_at) : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="热门入库 A" width="148">
            <template #default="{ row }">
              {{ row.last_hot_ingest_at ? formatDate(row.last_hot_ingest_at) : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="热门更新 B" width="148">
            <template #default="{ row }">
              {{ row.last_hot_update_at ? formatDate(row.last_hot_update_at) : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="操作" min-width="280">
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
                <router-link :to="videosLink({ creator_id: row.id })" class="tm-btn-ghost sm">视频</router-link>
                <button v-if="canManage(row)" type="button" class="tm-btn-danger sm" @click="handleDelete(row)">删除</button>
                <span v-if="!canManage(row)" class="readonly-hint">仅可查看</span>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="total > 0" class="table-pager">
          <span class="pager-total">共 {{ total }} 条</span>
          <el-pagination
            v-if="total > pageSize"
            background small layout="prev, pager, next"
            :total="total" :page-size="pageSize" :current-page="page"
            @current-change="onPageChange"
          />
        </div>
      </div>

      <!-- 分组设置（管理员） -->
      <div v-show="activeTab === 'groups' && auth.isSuperAdmin" class="groups-wrap">
        <div class="groups-toolbar">
          <span class="coordinator-hint">
            B 线协调器每 {{ collectionStatus.coordinator?.check_interval_minutes || 1 }} 分钟检查 · 瞬时增速优先 B 线快照
          </span>
          <button class="tm-btn-ghost sm" :disabled="collectionStatusLoading" @click="loadCollectionStatus">
            {{ collectionStatusLoading ? '刷新中…' : '刷新状态' }}
          </button>
        </div>

        <div v-if="!groups.length" class="empty-hint">暂无分组，请先新建分组作为博主类别</div>
        <article v-for="group in groups" :key="group.id" class="group-card">
          <div class="group-head">
            <div>
              <h3>{{ group.name }}</h3>
            </div>
            <div class="group-actions">
              <button
                class="tm-btn-ghost sm"
                :disabled="hotTriggerLoading[`a-${group.id}`]"
                @click="triggerHotIngest(group)"
              >
                {{ hotTriggerLoading[`a-${group.id}`] ? 'A 线中…' : '手动 A 线' }}
              </button>
              <button
                class="tm-btn-ghost sm"
                :disabled="hotTriggerLoading[`b-${group.id}`]"
                @click="triggerHotUpdate(group)"
              >
                {{ hotTriggerLoading[`b-${group.id}`] ? 'B 线中…' : '手动 B 线' }}
              </button>
              <button class="tm-btn-ghost sm" @click="openEditGroup(group)">编辑阈值</button>
              <button class="tm-btn-ghost sm" @click="openAddToGroup(group)">添加博主</button>
              <button class="tm-btn-ghost sm danger" @click="removeGroup(group)">删除</button>
            </div>
          </div>

          <div class="collection-panel">
            <div class="collection-panel-head">
              <span>采集状态 & 闹钟</span>
            </div>
            <div class="status-grid" v-loading="collectionStatusLoading">
              <template v-if="statusForGroup(group.id)">
                <div class="status-item">
                  <span class="status-label">当前 B 时段</span>
                  <span class="status-value">
                    <template v-if="statusForGroup(group.id).current_segment">
                      {{ statusForGroup(group.id).current_segment.start_time }}–{{ statusForGroup(group.id).current_segment.end_time }}
                      · {{ statusForGroup(group.id).current_segment.interval_minutes }} 分
                    </template>
                    <span v-else class="muted">未配置</span>
                  </span>
                </div>
                <div class="status-item">
                  <span class="status-label">最近 A 线</span>
                  <span class="status-value">
                    {{ statusForGroup(group.id).last_hot_ingest_at ? formatDate(statusForGroup(group.id).last_hot_ingest_at) : '-' }}
                  </span>
                </div>
                <div class="status-item">
                  <span class="status-label">最近 B 线</span>
                  <span class="status-value">
                    {{ statusForGroup(group.id).last_hot_update_at ? formatDate(statusForGroup(group.id).last_hot_update_at) : '-' }}
                  </span>
                </div>
                <div class="status-item">
                  <span class="status-label">运行状态</span>
                  <span class="status-value">
                    <span v-if="statusForGroup(group.id).hot_update_running" class="tm-tag blue">B 运行中</span>
                    <span v-else-if="statusForGroup(group.id).b_due_now" class="tm-tag daily-hot">待 B</span>
                    <span v-else class="tm-tag">正常</span>
                  </span>
                </div>
              </template>
              <p v-else class="mini-hint status-empty">状态加载中…</p>
            </div>

            <div class="alarms-grid">
              <div class="alarm-col">
                <div class="schedule-head">
                  <span>Daily 增量闹钟</span>
                  <button class="tm-btn-ghost sm" @click="openScheduleForm(group, 'daily')">添加</button>
                </div>
                <div v-if="dailySchedulesMap[group.id]?.length" class="schedule-list">
                  <div v-for="s in dailySchedulesMap[group.id]" :key="s.id" class="schedule-row">
                    <span>{{ s.name || 'Daily 增量' }}</span>
                    <span>{{ s.schedule_type === 'daily' ? `每日 ${s.run_time}` : `单次 ${formatDate(s.run_at)}` }}</span>
                    <el-switch :model-value="s.enabled" size="small" @change="toggleSchedule(group.id, s)" />
                    <button class="icon-btn" @click="removeSchedule(group.id, s)">×</button>
                  </div>
                </div>
                <p v-else class="mini-hint">未配置</p>
              </div>
              <div class="alarm-col">
                <div class="schedule-head">
                  <span>热门入库 A 线闹钟</span>
                  <button class="tm-btn-ghost sm" @click="openScheduleForm(group, 'hot_ingest')">添加</button>
                </div>
                <div v-if="hotIngestSchedulesMap[group.id]?.length" class="schedule-list">
                  <div v-for="s in hotIngestSchedulesMap[group.id]" :key="s.id" class="schedule-row">
                    <span>{{ s.name || '热门入库' }}</span>
                    <span>{{ s.schedule_type === 'daily' ? `每日 ${s.run_time}` : `单次 ${formatDate(s.run_at)}` }}</span>
                    <el-switch :model-value="s.enabled" size="small" @change="toggleSchedule(group.id, s)" />
                    <button class="icon-btn" @click="removeSchedule(group.id, s)">×</button>
                  </div>
                </div>
                <p v-else class="mini-hint">未配置；执行 A 线后会串联 B 线</p>
              </div>
            </div>
          </div>

          <el-collapse class="segment-collapse">
            <el-collapse-item :name="String(group.id)">
              <template #title>
                <div class="segment-collapse-title">
                  <span class="segment-collapse-label">热门更新 B 线分时段</span>
                  <span class="segment-summary">{{ segmentSummary(group.id) }}</span>
                </div>
              </template>
              <div class="segment-panel">
                <div class="segment-toolbar">
                  <span class="mini-hint">北京时间，须覆盖 24 小时；跨午夜用结束 &lt; 开始，如 22:00–08:00</span>
                  <div class="segment-actions">
                    <template v-if="segmentEditing[group.id]">
                      <button class="tm-btn-ghost sm" @click="addSegmentRow(group.id)">加一行</button>
                      <button class="tm-btn-ghost sm" @click="cancelSegmentEdit(group.id)">取消</button>
                      <button class="tm-btn-primary sm" :disabled="segmentSaving[group.id]" @click="saveSegments(group)">
                        {{ segmentSaving[group.id] ? '保存中…' : '保存' }}
                      </button>
                    </template>
                    <button v-else class="tm-btn-ghost sm" @click="startSegmentEdit(group.id)">编辑</button>
                  </div>
                </div>
                <el-table :data="segmentEditing[group.id] ? segmentDraft[group.id] : hotSegmentsMap[group.id]" size="small" class="segment-table" empty-text="加载中…">
                  <el-table-column label="开始" width="120">
                    <template #default="{ row }">
                      <el-time-picker
                        v-if="segmentEditing[group.id]"
                        v-model="row.start_time_picker"
                        format="HH:mm"
                        value-format="HH:mm"
                        placeholder="开始"
                        style="width: 100%"
                      />
                      <span v-else>{{ row.start_time }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="结束" width="120">
                    <template #default="{ row }">
                      <el-time-picker
                        v-if="segmentEditing[group.id]"
                        v-model="row.end_time_picker"
                        format="HH:mm"
                        value-format="HH:mm"
                        placeholder="结束"
                        style="width: 100%"
                      />
                      <span v-else>{{ row.end_time }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="间隔（分钟）" min-width="130">
                    <template #default="{ row }">
                      <el-input-number
                        v-if="segmentEditing[group.id]"
                        v-model="row.interval_minutes"
                        :min="5"
                        :step="5"
                        controls-position="right"
                        style="width: 120px"
                      />
                      <span v-else>{{ row.interval_minutes }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column v-if="segmentEditing[group.id]" label="" width="56">
                    <template #default="{ $index }">
                      <button class="icon-btn" @click="removeSegmentRow(group.id, $index)">×</button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </el-collapse-item>
          </el-collapse>
        </article>
      </div>
    </div>

    <!-- 添加博主（博主列表 / 分组内共用） -->
    <el-dialog
      v-model="showAdd"
      :title="addGroupLocked ? '向分组添加博主' : '添加监控博主'"
      width="560px"
      @closed="resetAddDialog"
    >
      <el-form label-width="90px">
        <el-form-item v-if="!addGroupLocked" label="博主类别" required>
          <el-select v-model="addGroupId" placeholder="请选择类别" style="width: 100%">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
        <p v-else class="group-lock-hint">将自动归入「{{ addGroupName }}」类别</p>
        <el-form-item label="博主列表">
          <el-input
            v-model="pasteText"
            type="textarea"
            :rows="7"
            placeholder="粘贴博主列表、分享文案或 TikTok 链接&#10;每行一个 username，无需加 @，系统会自动补全"
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
        <el-button type="primary" :loading="adding" @click="handleBatchAdd">{{ addButtonLabel }}</el-button>
      </template>
    </el-dialog>

    <!-- 分组表单 -->
    <el-dialog
      v-model="showGroupForm"
      :title="editingGroup ? '编辑分组' : '新建分组'"
      width="520px"
      align-center
      class="group-form-dialog"
    >
      <el-form class="group-form" label-width="112px" label-position="right">
        <el-form-item label="名称">
          <div class="form-field-wrap">
            <el-input v-model="groupForm.name" placeholder="如：影视、动漫" />
            <span class="field-unit"></span>
          </div>
        </el-form-item>
        <div class="form-section-label">分组阈值</div>
        <el-form-item label="历史爆款阈值">
          <div class="form-field-wrap">
            <el-input-number v-model="groupForm.historical_view_threshold" :min="1000" :step="10000" controls-position="right" />
            <span class="field-unit"></span>
          </div>
        </el-form-item>
        <el-form-item label="平均流量增速">
          <div class="form-field-wrap">
            <el-input-number v-model="groupForm.daily_hot_avg_growth_threshold" :min="0" :step="10" :precision="1" controls-position="right" />
            <span class="field-unit">播放/分钟</span>
          </div>
        </el-form-item>
        <el-form-item label="B 线默认间隔">
          <div class="form-field-wrap">
            <el-input-number v-model="groupForm.growth_window_minutes" :min="5" :step="5" controls-position="right" />
            <span class="field-unit">分钟</span>
          </div>
        </el-form-item>
        <el-form-item label="热门采集窗口">
          <div class="form-field-wrap">
            <el-input-number v-model="groupForm.scrape_window_hours" :min="1" controls-position="right" />
            <span class="field-unit">小时</span>
          </div>
        </el-form-item>
        <el-form-item label="博主上限">
          <div class="form-field-wrap">
            <el-input-number v-model="groupForm.max_creators" :min="1" controls-position="right" />
            <span class="field-unit"></span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="group-form-footer">
          <el-button @click="showGroupForm = false">取消</el-button>
          <el-button type="primary" :loading="groupSaving" @click="saveGroup">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 分组删除：两次手动输入密码（禁用浏览器自动填充） -->
    <el-dialog
      v-model="showDeleteVerify"
      :title="deleteVerifyStep === 1 ? '第一次验证' : '第二次验证'"
      width="420px"
      append-to-body
      @opened="onDeleteVerifyOpened"
      @closed="resetDeleteVerify"
    >
      <p class="delete-verify-hint">
        {{ deleteVerifyStep === 1 ? '请输入管理员密码' : '请再次输入管理员密码' }}
      </p>
      <el-input
        v-if="deleteVerifyStep === 1"
        ref="deletePwdInputRef"
        v-model="deletePassword1"
        type="password"
        show-password
        placeholder="管理员密码"
        autocomplete="new-password"
        name="group-delete-verify-step1"
        :readonly="deletePwdReadonly"
        @focus="deletePwdReadonly = false"
        @keyup.enter="nextDeleteVerifyStep"
      />
      <el-input
        v-else
        ref="deletePwdInputRef"
        v-model="deletePassword2"
        type="password"
        show-password
        placeholder="再次输入管理员密码"
        autocomplete="new-password"
        name="group-delete-verify-step2"
        :readonly="deletePwdReadonly"
        @focus="deletePwdReadonly = false"
        @keyup.enter="confirmDeleteGroup"
      />
      <template #footer>
        <el-button @click="showDeleteVerify = false">取消</el-button>
        <el-button
          v-if="deleteVerifyStep === 1"
          type="primary"
          @click="nextDeleteVerifyStep"
        >
          下一步
        </el-button>
        <el-button
          v-else
          type="primary"
          :loading="deleteVerifySaving"
          @click="confirmDeleteGroup"
        >
          确认删除
        </el-button>
      </template>
    </el-dialog>

    <!-- 闹钟表单 -->
    <el-dialog v-model="showScheduleForm" :title="scheduleDialogTitle" width="420px">
      <el-form label-width="100px">
        <el-form-item label="名称"><el-input v-model="scheduleForm.name" placeholder="可选" /></el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="scheduleForm.schedule_type">
            <el-radio value="daily">每日定点</el-radio>
            <el-radio value="once">单次定时</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="scheduleForm.schedule_type === 'daily'" label="执行时间">
          <el-time-picker v-model="scheduleForm.run_time_picker" format="HH:mm" value-format="HH:mm" />
        </el-form-item>
        <el-form-item v-else label="执行时间">
          <el-date-picker v-model="scheduleForm.run_at_picker" type="datetime" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showScheduleForm = false">取消</el-button>
        <el-button type="primary" :loading="scheduleSaving" @click="saveSchedule">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
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
const activeTab = ref('creators')
const groups = ref([])
const dailySchedulesMap = ref({})
const hotIngestSchedulesMap = ref({})
const hotSegmentsMap = ref({})
const segmentEditing = ref({})
const segmentDraft = ref({})
const segmentSaving = ref({})
const hotTriggerLoading = ref({})
const collectionStatus = ref({ items: [], coordinator: {} })
const collectionStatusLoading = ref(false)
const creators = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const filterGroupId = ref(null)

const showAdd = ref(false)
const pasteText = ref('')
const extractedUsernames = ref([])
const parsing = ref(false)
const adding = ref(false)
const addGroupId = ref(null)
const addGroupLocked = ref(false)

const showGroupForm = ref(false)
const editingGroup = ref(null)
const groupSaving = ref(false)
const groupForm = ref(defaultGroupForm())

const showScheduleForm = ref(false)
const scheduleGroupId = ref(null)
const scheduleTaskType = ref('daily')
const scheduleSaving = ref(false)
const scheduleForm = ref({ name: '', schedule_type: 'daily', run_time_picker: '09:00', run_at_picker: null })

const scheduleDialogTitle = computed(() => (
  scheduleTaskType.value === 'hot_ingest' ? '添加热门入库 A 线闹钟' : '添加 Daily 增量闹钟'
))

const showDeleteVerify = ref(false)
const deleteVerifyStep = ref(1)
const deleteTargetGroup = ref(null)
const deletePassword1 = ref('')
const deletePassword2 = ref('')
const deletePwdReadonly = ref(true)
const deleteVerifySaving = ref(false)
const deletePwdInputRef = ref(null)

const addGroupName = computed(() => groups.value.find((g) => g.id === addGroupId.value)?.name || '')
const collectionStatusMap = computed(() => {
  const map = {}
  for (const item of collectionStatus.value.items || []) {
    map[item.group_id] = item
  }
  return map
})
const addButtonLabel = computed(() => {
  const count = extractedUsernames.value.length || collectUsernames().length
  return count > 1 ? `批量添加 (${count})` : '确认添加'
})

function defaultGroupForm() {
  return {
    name: '',
    historical_view_threshold: 100000,
    daily_hot_avg_growth_threshold: 50,
    growth_window_minutes: 30,
    scrape_window_hours: 30,
    max_creators: 999,
  }
}

function canManage(row) {
  return canManageCreator(row)
}

function statusForGroup(groupId) {
  return collectionStatusMap.value[groupId] || null
}

function segmentSummary(groupId) {
  const status = statusForGroup(groupId)
  const segCount = status?.segment_count ?? hotSegmentsMap.value[groupId]?.length ?? 0
  if (status?.current_segment) {
    const s = status.current_segment
    return `当前 ${s.start_time}–${s.end_time} · ${s.interval_minutes} 分 · ${segCount} 段`
  }
  if (segCount) return `${segCount} 个时段 · 北京时间`
  return '未配置'
}

async function loadGroups() {
  const { data } = await api.get('/groups')
  groups.value = data || []
  if (auth.isSuperAdmin) {
    const dailyMap = {}
    const hotMap = {}
    const segMap = {}
    await Promise.all(groups.value.map(async (g) => {
      const [dailyRes, hotRes, segRes] = await Promise.all([
        api.get(`/groups/${g.id}/schedules`, { params: { task_type: 'daily' } }),
        api.get(`/groups/${g.id}/schedules`, { params: { task_type: 'hot_ingest' } }),
        api.get(`/groups/${g.id}/hot-update-segments`),
      ])
      dailyMap[g.id] = dailyRes.data || []
      hotMap[g.id] = hotRes.data || []
      segMap[g.id] = segRes.data || []
    }))
    dailySchedulesMap.value = dailyMap
    hotIngestSchedulesMap.value = hotMap
    hotSegmentsMap.value = segMap
    await loadCollectionStatus()
  }
}

async function loadCollectionStatus() {
  if (!auth.isSuperAdmin) return
  collectionStatusLoading.value = true
  try {
    const { data } = await api.get('/dashboard/collection-status')
    collectionStatus.value = data || { items: [], coordinator: {} }
  } finally {
    collectionStatusLoading.value = false
  }
}

function cloneSegmentsForEdit(segments) {
  return (segments || []).map((s, idx) => ({
    start_time: s.start_time,
    end_time: s.end_time,
    interval_minutes: s.interval_minutes,
    sort_order: s.sort_order ?? idx,
    start_time_picker: s.start_time,
    end_time_picker: s.end_time,
  }))
}

function startSegmentEdit(groupId) {
  segmentDraft.value = {
    ...segmentDraft.value,
    [groupId]: cloneSegmentsForEdit(hotSegmentsMap.value[groupId]),
  }
  segmentEditing.value = { ...segmentEditing.value, [groupId]: true }
}

function cancelSegmentEdit(groupId) {
  segmentEditing.value = { ...segmentEditing.value, [groupId]: false }
  delete segmentDraft.value[groupId]
}

function addSegmentRow(groupId) {
  const rows = [...(segmentDraft.value[groupId] || [])]
  rows.push({
    start_time: '00:00',
    end_time: '01:00',
    interval_minutes: 30,
    sort_order: rows.length,
    start_time_picker: '00:00',
    end_time_picker: '01:00',
  })
  segmentDraft.value = { ...segmentDraft.value, [groupId]: rows }
}

function removeSegmentRow(groupId, index) {
  const rows = [...(segmentDraft.value[groupId] || [])]
  if (rows.length <= 1) {
    ElMessage.warning('至少保留一个时段')
    return
  }
  rows.splice(index, 1)
  segmentDraft.value = { ...segmentDraft.value, [groupId]: rows }
}

async function triggerHotIngest(group) {
  const key = `a-${group.id}`
  hotTriggerLoading.value = { ...hotTriggerLoading.value, [key]: true }
  try {
    const { data } = await api.post(`/groups/${group.id}/hot-ingest/trigger`, null, { timeout: 600000 })
    const chain = data?.result?.update_chain
    if (chain?.skipped) {
      ElMessage.success('A 线已完成；B 线正在运行已跳过')
    } else {
      ElMessage.success(data.message || 'A 线已完成')
    }
    await Promise.all([loadGroups(), loadCreators({ silent: true }), loadCollectionStatus()])
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || 'A 线触发失败')
  } finally {
    hotTriggerLoading.value = { ...hotTriggerLoading.value, [key]: false }
  }
}

async function triggerHotUpdate(group) {
  const key = `b-${group.id}`
  hotTriggerLoading.value = { ...hotTriggerLoading.value, [key]: true }
  try {
    const { data } = await api.post(`/groups/${group.id}/hot-update/trigger`, null, { timeout: 600000 })
    if (data?.result?.skipped) {
      ElMessage.warning('B 线正在运行，已跳过')
    } else {
      ElMessage.success(data.message || 'B 线已完成')
    }
    await Promise.all([loadGroups(), loadCreators({ silent: true }), loadCollectionStatus()])
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || 'B 线触发失败')
  } finally {
    hotTriggerLoading.value = { ...hotTriggerLoading.value, [key]: false }
  }
}

async function saveSegments(group) {
  const groupId = group.id
  const rows = segmentDraft.value[groupId] || []
  if (!rows.length) {
    ElMessage.warning('至少配置一个时段')
    return
  }
  const payload = {
    segments: rows.map((row, idx) => ({
      start_time: row.start_time_picker || row.start_time,
      end_time: row.end_time_picker || row.end_time,
      interval_minutes: row.interval_minutes,
      sort_order: idx,
    })),
  }
  segmentSaving.value = { ...segmentSaving.value, [groupId]: true }
  try {
    const { data } = await api.put(`/groups/${groupId}/hot-update-segments`, payload)
    hotSegmentsMap.value = { ...hotSegmentsMap.value, [groupId]: data || [] }
    cancelSegmentEdit(groupId)
    ElMessage.success('B 线分时段已保存')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    segmentSaving.value = { ...segmentSaving.value, [groupId]: false }
  }
}

async function loadCreators(opts = {}) {
  if (!opts.silent) loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (filterGroupId.value) params.group_id = filterGroupId.value
    const { data } = await api.get('/creators', { params })
    creators.value = data.items || []
    total.value = data.total || 0
  } finally {
    if (!opts.silent) loading.value = false
  }
}

const { isScraping, trackScrape, onScrapeDone, onScrapeBackground } = useCreatorScrapePolling({
  refresh: loadCreators,
  findCreator: (id) => creators.value.find((c) => c.id === id),
})

function openAddDialog() {
  if (!groups.value.length) {
    ElMessage.warning('请等待管理员创建博主类别')
    return
  }
  resetAddDialog()
  addGroupLocked.value = false
  addGroupId.value = filterGroupId.value || groups.value[0]?.id || null
  showAdd.value = true
}

function resetAddDialog() {
  pasteText.value = ''
  extractedUsernames.value = []
  addGroupLocked.value = false
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

async function handleParsePaste() {
  const text = pasteText.value?.trim()
  if (!text) { ElMessage.warning('请先粘贴博主信息'); return }
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
  if (!list.length) { ElMessage.warning('请输入或提取至少一个博主'); return }
  if (!addGroupId.value) { ElMessage.warning('请选择博主类别'); return }
  adding.value = true
  try {
    if (list.length === 1) {
      await api.post('/creators', { tiktok_username: list[0], group_id: addGroupId.value })
      ElMessage.success('添加成功')
    } else {
      const { data } = await api.post('/creators/batch', { tiktok_usernames: list, group_id: addGroupId.value }, { timeout: 180000 })
      if (data.succeeded && data.failed) {
        ElMessage.warning(`成功 ${data.succeeded} 个，失败 ${data.failed} 个`)
      } else if (data.succeeded) {
        ElMessage.success(`已成功添加 ${data.succeeded} 个博主`)
      } else {
        ElMessage.error('全部添加失败')
      }
    }
    showAdd.value = false
    page.value = 1
    await Promise.all([loadCreators(), loadGroups()])
  } finally {
    adding.value = false
  }
}

async function changeCategory(row, groupId) {
  if (!groupId || groupId === row.group_id) return
  try {
    await api.patch(`/creators/${row.id}`, { group_id: groupId })
    ElMessage.success('类别已更新，后续采集将按新分组阈值归类')
    await loadCreators()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '更新失败')
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除 @${row.tiktok_username}？`, '确认')
  try {
    await api.delete(`/creators/${row.id}`)
    ElMessage.success('已删除')
    if (creators.value.length === 1 && page.value > 1) page.value -= 1
    await Promise.all([loadCreators(), loadGroups()])
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

function onPageChange(p) { page.value = p; loadCreators() }
function onFilterChange() { page.value = 1; loadCreators() }

function openCreateGroup() {
  editingGroup.value = null
  groupForm.value = defaultGroupForm()
  showGroupForm.value = true
}

function openEditGroup(group) {
  editingGroup.value = group
  groupForm.value = { ...group }
  showGroupForm.value = true
}

async function saveGroup() {
  groupSaving.value = true
  try {
    if (editingGroup.value) {
      await api.put(`/groups/${editingGroup.value.id}`, groupForm.value)
    } else {
      await api.post('/groups', groupForm.value)
    }
    ElMessage.success('已保存')
    showGroupForm.value = false
    await loadGroups()
  } finally {
    groupSaving.value = false
  }
}

function resetDeleteVerify() {
  deleteVerifyStep.value = 1
  deleteTargetGroup.value = null
  deletePassword1.value = ''
  deletePassword2.value = ''
  deletePwdReadonly.value = true
  deleteVerifySaving.value = false
}

function onDeleteVerifyOpened() {
  deletePwdReadonly.value = true
  nextTick(() => deletePwdInputRef.value?.focus?.())
}

function nextDeleteVerifyStep() {
  if (!deletePassword1.value.trim()) {
    ElMessage.warning('请输入密码')
    return
  }
  deleteVerifyStep.value = 2
  deletePassword2.value = ''
  deletePwdReadonly.value = true
  nextTick(() => deletePwdInputRef.value?.focus?.())
}

async function confirmDeleteGroup() {
  if (!deletePassword2.value.trim()) {
    ElMessage.warning('请再次输入密码')
    return
  }
  const group = deleteTargetGroup.value
  if (!group) return
  deleteVerifySaving.value = true
  try {
    await api.delete(`/groups/${group.id}`, {
      data: { password: deletePassword1.value, confirm_password: deletePassword2.value },
    })
    ElMessage.success('分组已删除')
    showDeleteVerify.value = false
    await loadGroups()
  } catch (e) {
    const msg = e?.response?.data?.detail
    ElMessage.error(typeof msg === 'string' ? msg : '删除失败')
  } finally {
    deleteVerifySaving.value = false
  }
}

async function removeGroup(group) {
  try {
    await ElMessageBox.confirm(
      `确定删除分组「${group.name}」？删除后前端不再显示，数据库将保留 7 天。`,
      '删除确认',
      { type: 'warning' },
    )
    deleteTargetGroup.value = group
    deleteVerifyStep.value = 1
    deletePassword1.value = ''
    deletePassword2.value = ''
    deletePwdReadonly.value = true
    showDeleteVerify.value = true
  } catch (e) {
    if (e === 'cancel' || e === 'close') return
  }
}

function openAddToGroup(group) {
  resetAddDialog()
  addGroupLocked.value = true
  addGroupId.value = group.id
  showAdd.value = true
}

function openScheduleForm(group, taskType = 'daily') {
  scheduleGroupId.value = group.id
  scheduleTaskType.value = taskType
  scheduleForm.value = { name: '', schedule_type: 'daily', run_time_picker: '09:00', run_at_picker: null }
  showScheduleForm.value = true
}

async function saveSchedule() {
  const form = scheduleForm.value
  const payload = {
    name: form.name,
    task_type: scheduleTaskType.value,
    schedule_type: form.schedule_type,
    timezone: 'Asia/Shanghai',
    enabled: true,
  }
  if (form.schedule_type === 'daily') {
    if (!form.run_time_picker) { ElMessage.warning('请选择时间'); return }
    payload.run_time = form.run_time_picker
  } else {
    if (!form.run_at_picker) { ElMessage.warning('请选择时间'); return }
    payload.run_at = new Date(form.run_at_picker).toISOString()
  }
  scheduleSaving.value = true
  try {
    await api.post(`/groups/${scheduleGroupId.value}/schedules`, payload)
    ElMessage.success('闹钟已添加')
    showScheduleForm.value = false
    await loadGroups()
  } finally {
    scheduleSaving.value = false
  }
}

async function toggleSchedule(groupId, row) {
  await api.put(`/groups/${groupId}/schedules/${row.id}`, { enabled: !row.enabled })
  await loadGroups()
}

async function removeSchedule(groupId, row) {
  await ElMessageBox.confirm('确定删除该闹钟？', '确认')
  await api.delete(`/groups/${groupId}/schedules/${row.id}`)
  await loadGroups()
}

onMounted(async () => {
  await loadGroups()
  await loadCreators()
})
</script>

<style scoped>
.page--fill { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.main-card { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; box-shadow: var(--tm-shadow-sm); }
.card-top { flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 24px; border-bottom: 1px solid var(--tm-border); }
.card-top-spacer { flex: 1; }
.top-actions { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.tab-switch { margin-right: 0; }
.title { margin: 0; font-size: 18px; font-weight: 700; color: var(--tm-text); }
.table-wrap { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.filter-bar { display: flex; align-items: center; padding: 12px 24px; flex-shrink: 0; }
.table-pager { flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; padding: 12px 24px 16px; border-top: 1px solid var(--tm-border); }
.pager-total { font-size: 12px; color: var(--tm-text-muted); }
.groups-wrap { flex: 1; overflow-y: auto; padding: 16px 24px 24px; display: flex; flex-direction: column; gap: 16px; }
.groups-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border: 1px solid var(--tm-border);
  border-radius: var(--tm-radius-md);
  background: var(--tm-surface);
}
.coordinator-hint { font-size: 12px; color: var(--tm-text-muted); line-height: 1.5; }
.collection-panel {
  margin-top: 16px;
  padding: 14px 16px;
  border: 1px solid var(--tm-border);
  border-radius: var(--tm-radius-md);
  background: var(--tm-surface);
}
.collection-panel-head {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 12px;
  color: var(--tm-text);
}
.status-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px 16px;
  margin-bottom: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--tm-border);
}
.status-item { min-width: 0; }
.status-label {
  display: block;
  font-size: 11px;
  color: var(--tm-text-muted);
  margin-bottom: 4px;
}
.status-value { font-size: 12px; color: var(--tm-text-secondary); word-break: break-word; }
.status-empty { grid-column: 1 / -1; margin: 0; }
.alarms-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.alarm-col { min-width: 0; }
.segment-collapse {
  margin-top: 12px;
  border: none;
}
.segment-collapse :deep(.el-collapse-item__header) {
  height: auto;
  min-height: 40px;
  padding: 8px 12px;
  border: 1px solid var(--tm-border);
  border-radius: var(--tm-radius-md);
  background: var(--tm-surface);
  line-height: 1.4;
}
.segment-collapse :deep(.el-collapse-item__wrap) {
  border: none;
  background: transparent;
}
.segment-collapse :deep(.el-collapse-item__content) {
  padding: 0;
  background: transparent;
}
.segment-collapse-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding-right: 8px;
}
.segment-collapse-label { font-size: 13px; font-weight: 600; color: var(--tm-text); }
.segment-summary { font-size: 12px; font-weight: 400; color: var(--tm-text-muted); }
.segment-panel {
  margin-top: 8px;
  padding: 0;
  border: none;
  background: transparent;
}
.segment-table :deep(.el-table),
.segment-table :deep(.el-table__inner-wrapper),
.segment-table :deep(.el-table__body-wrapper),
.segment-table :deep(.el-table__header-wrapper),
.segment-table :deep(tr),
.segment-table :deep(th.el-table__cell),
.segment-table :deep(td.el-table__cell) {
  background: transparent;
}
.segment-table :deep(th.el-table__cell) {
  padding: 8px 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--tm-text-muted);
  border-bottom: 1px solid var(--tm-border);
}
.segment-table :deep(td.el-table__cell) {
  padding: 8px 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
}
.segment-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}
.muted { color: var(--tm-text-muted); font-size: 12px; }
.group-card { border: 1px solid var(--tm-border); border-radius: var(--tm-radius-md); padding: 18px 20px; background: var(--tm-surface-muted); }
.group-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.group-head h3 { margin: 0; font-size: 16px; }
.group-head p { margin: 4px 0 0; font-size: 12px; color: var(--tm-text-muted); }
.group-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.schedule-head { display: flex; align-items: center; justify-content: space-between; font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.schedule-list { display: flex; flex-direction: column; gap: 6px; }
.schedule-row { display: flex; align-items: center; gap: 12px; font-size: 12px; padding: 6px 0; }
.segment-actions { display: flex; gap: 6px; flex-wrap: wrap; flex-shrink: 0; }
.segment-table { margin-top: 0; }
.tm-btn-primary.sm {
  height: 28px;
  padding: 0 12px;
  border-radius: var(--tm-radius-pill);
  font-size: 12px;
  font-weight: 600;
  border: none;
  background: var(--tm-purple);
  color: #fff;
  cursor: pointer;
}
.tm-btn-primary.sm:disabled { opacity: 0.6; cursor: not-allowed; }
.icon-btn { border: none; background: none; cursor: pointer; color: var(--tm-text-muted); font-size: 16px; }
.mini-hint { font-size: 12px; color: var(--tm-text-muted); margin: 0; }
.empty-hint { text-align: center; padding: 40px; color: var(--tm-text-muted); font-size: 14px; }
.parse-hint { margin-left: 10px; font-size: 12px; color: var(--tm-text-muted); }
.extract-preview { margin-top: 4px; padding: 12px 14px; border-radius: var(--tm-radius-md); background: #f8f7fb; border: 1px solid rgba(123, 67, 151, 0.12); }
.preview-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; font-size: 12px; font-weight: 600; }
.clear-btn { border: none; background: transparent; color: var(--tm-purple); font-size: 12px; cursor: pointer; }
.username-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.username-tag { display: inline-flex; align-items: center; gap: 4px; padding: 4px 8px 4px 10px; border-radius: var(--tm-radius-pill); background: var(--tm-surface); border: 1px solid var(--tm-border); font-size: 12px; font-weight: 600; }
.tag-remove { width: 18px; height: 18px; padding: 0; border: none; border-radius: 50%; background: transparent; cursor: pointer; }
.row-actions { display: flex; align-items: center; gap: 8px; flex-wrap: nowrap; white-space: nowrap; }
.tm-btn-danger.sm, .tm-btn-ghost.sm {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 32px;
  padding: 0 14px;
  border-radius: var(--tm-radius-pill);
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
  box-sizing: border-box;
  vertical-align: middle;
}
.tm-btn-danger.sm { border: 1.5px solid rgba(220, 60, 60, 0.3); background: transparent; color: #c0392b; cursor: pointer; }
.tm-btn-ghost.sm { text-decoration: none; color: var(--tm-text-secondary); border: 1.5px solid var(--tm-border); background: transparent; cursor: pointer; }
.readonly-hint { font-size: 12px; color: var(--tm-text-muted); }
.unit { margin-left: 8px; font-size: 12px; color: var(--tm-text-muted); }
.group-lock-hint {
  margin: 0 0 12px 90px;
  font-size: 13px;
  color: var(--tm-text-secondary);
  font-weight: 600;
}

.delete-verify-hint { margin: 0 0 12px; font-size: 14px; color: var(--tm-text-secondary); }

.group-form-dialog :deep(.el-dialog__header) {
  padding: 20px 24px 12px;
  margin-right: 0;
  text-align: center;
}

.group-form-dialog :deep(.el-dialog__title) {
  font-size: 17px;
  font-weight: 700;
}

.group-form-dialog :deep(.el-dialog__body) {
  display: flex;
  justify-content: center;
  padding: 8px 28px 4px;
}

.group-form-dialog :deep(.el-dialog__footer) {
  padding: 12px 28px 22px;
}

.group-form {
  width: 428px;
  max-width: 100%;
  margin: 0 auto;
}

.group-form :deep(.el-form-item) {
  margin-bottom: 16px;
}

.group-form :deep(.el-form-item__label) {
  color: var(--tm-text-secondary);
  font-weight: 500;
  padding-right: 12px;
}

.group-form :deep(.el-form-item__content) {
  flex: 1;
  min-width: 0;
}

.form-section-label {
  margin: 4px 0 14px 112px;
  font-size: 12px;
  font-weight: 700;
  color: var(--tm-text-secondary);
  letter-spacing: 0.04em;
}

.form-field-wrap {
  display: grid;
  grid-template-columns: 240px 72px;
  gap: 8px;
  align-items: center;
  width: 100%;
}

.form-field-wrap :deep(.el-input),
.form-field-wrap :deep(.el-textarea),
.form-field-wrap :deep(.el-input-number) {
  width: 100%;
}

.form-field-wrap :deep(.el-input-number .el-input__wrapper) {
  width: 100%;
  box-sizing: border-box;
}

.field-unit {
  font-size: 12px;
  color: var(--tm-text-muted);
  white-space: nowrap;
  line-height: 1.3;
}

.field-unit:empty {
  visibility: hidden;
}

.group-form-footer {
  display: flex;
  justify-content: center;
  gap: 12px;
}
.main-card :deep(.el-table) { --el-table-border-color: transparent; background: transparent; }
.main-card :deep(.el-table th.el-table__cell) { padding: 14px 0 14px 24px; font-size: 12px; font-weight: 600; color: var(--tm-text-muted); border-bottom: 1px solid var(--tm-border); }
.main-card :deep(.col-video-count) { white-space: nowrap; }
.main-card :deep(.el-table td.el-table__cell) { padding: 12px 0 12px 24px; border-bottom: 1px solid #f2f2f2; }
</style>
