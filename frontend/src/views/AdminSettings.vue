<template>

  <div v-loading="loading" class="page">

    <el-row :gutter="16">

      <el-col :span="12">

        <div class="tm-card">

          <div class="tm-card-header">

            <span class="title">核心阈值</span>

            <div class="header-actions">
              <span class="tm-tag purple">功能 1 & 2</span>
              <button class="tm-btn-primary" :disabled="saving" @click="saveSettings">
                {{ saving ? '保存中...' : '保存设置' }}
              </button>
            </div>

          </div>

          <div class="tm-card-body">

            <el-form label-width="150px" class="settings-form">

              <el-form-item label="历史爆款播放阈值">

                <el-input-number v-model="settings.historical_view" :min="1000" :step="10000" />

              </el-form-item>

              <el-form-item label="平均流量增速阈值">

                <el-input-number v-model="settings.daily_hot_avg_growth" :min="0" :step="10" :precision="1" />

                <span class="unit">播放/分钟</span>

              </el-form-item>

              <el-form-item label="B 线默认间隔(分钟)">

                <el-input-number v-model="settings.growth_window" :min="5" :step="5" />

              </el-form-item>

              <el-form-item label="近期视频天数">

                <el-input-number v-model="settings.recent_video_days" :min="1" />

              </el-form-item>

              <el-form-item label="近期更新间隔(天)">

                <el-input-number v-model="settings.recent_video_update_days" :min="1" />

              </el-form-item>

            </el-form>

            <p class="hint">当日热门：平均流量增速 ≥ 阈值（播放/分钟 = 播放量 ÷ 发布至今分钟数）。<strong>热门更新 B 线</strong>按分组在「监控管理 → 分组设置」配置分时段周期（北京时间，须覆盖 24 小时）；<strong>热门入库 A 线</strong>与 Daily 增量各有独立闹钟。A 线完成后自动串联 B 线（B 运行中则跳过）。瞬时增速优先使用 B 线快照。博主 Daily 增量由下方全局「Daily 采集闹钟」或各分组 Daily 闹钟触发。</p>

          </div>

        </div>

      </el-col>



      <el-col :span="12">

        <div class="tm-card">

          <div class="tm-card-header">

            <span class="title">豆包标注辅助</span>

            <span class="tm-tag blue">粘贴提取</span>

          </div>

          <div class="tm-card-body">

            <p class="settings-hint">标注者在豆包中识别 TikTok 封面后，复制完整结果粘贴到视频标注框，由 AI 提取片名/类型/演员等；动漫类型自动走 Bangumi 补充海报与链接，其它类型走 TMDB。</p>

            <el-form label-width="120px" class="settings-form">

              <el-form-item label="启用豆包 API">

                <el-switch v-model="settings.doubao_enabled" />

              </el-form-item>

              <el-form-item label="日预算(元)">

                <el-input-number v-model="settings.daily_budget" :min="1" />

              </el-form-item>

            </el-form>



            <div v-if="recStats" class="rec-stats">

              <div class="tm-stat-grid">

                <div class="tm-stat purple">

                  <div class="tm-stat-value">{{ recStats.total }}</div>

                  <div class="tm-stat-label">总计</div>

                </div>

                <div class="tm-stat blue">

                  <div class="tm-stat-value">{{ recStats.success }}</div>

                  <div class="tm-stat-label">成功</div>

                </div>

                <div class="tm-stat orange">

                  <div class="tm-stat-value">{{ recStats.failed }}</div>

                  <div class="tm-stat-label">失败</div>

                </div>

              </div>

              <p class="cost-line">

                今日费用 ¥{{ recStats.daily_cost?.toFixed(4) }} / ¥{{ recStats.daily_budget }}

              </p>

            </div>

          </div>

        </div>

      </el-col>

    </el-row>



    <div class="tm-card" style="margin-top:16px">

      <div class="tm-card-header">

        <span class="title">博主采集闹钟</span>

        <span class="tm-tag blue">仅管理员</span>

      </div>

      <div class="tm-card-body">

        <p class="hint schedule-hint">支持每日定点采集，或设置单次定时采集。到达时间后对所有活跃博主执行增量采集（{{ settings.recent_video_days }} 天内每 {{ settings.recent_video_update_days }} 天更新策略）。时区默认 Asia/Shanghai。</p>

        <el-form inline class="schedule-form">

          <el-form-item label="名称">

            <el-input v-model="scheduleForm.name" placeholder="可选" style="width:120px" />

          </el-form-item>

          <el-form-item label="类型">

            <el-select v-model="scheduleForm.schedule_type" style="width:100px">

              <el-option label="每日" value="daily" />

              <el-option label="单次" value="once" />

            </el-select>

          </el-form-item>

          <el-form-item v-if="scheduleForm.schedule_type === 'daily'" label="时间">

            <el-time-picker v-model="scheduleForm.run_time_picker" format="HH:mm" value-format="HH:mm" placeholder="选择时间" />

          </el-form-item>

          <el-form-item v-else label="执行时间">

            <el-date-picker

              v-model="scheduleForm.run_at_picker"

              type="datetime"

              placeholder="选择日期时间"

              format="YYYY-MM-DD HH:mm"

            />

          </el-form-item>

          <el-form-item>

            <el-button type="primary" :loading="scheduleSaving" @click="addSchedule">添加闹钟</el-button>

          </el-form-item>

        </el-form>

        <el-table :data="schedules" size="small" empty-text="尚未配置采集闹钟">

          <el-table-column prop="name" label="名称" min-width="100">

            <template #default="{ row }">{{ row.name || '-' }}</template>

          </el-table-column>

          <el-table-column label="类型" width="80">

            <template #default="{ row }">{{ row.schedule_type === 'daily' ? '每日' : '单次' }}</template>

          </el-table-column>

          <el-table-column label="计划" min-width="160">

            <template #default="{ row }">

              <span v-if="row.schedule_type === 'daily'">每天 {{ row.run_time }} ({{ row.timezone }})</span>

              <span v-else>{{ formatDate(row.run_at) }}</span>

            </template>

          </el-table-column>

          <el-table-column label="状态" width="100">

            <template #default="{ row }">

              <span v-if="row.schedule_type === 'once' && row.executed" class="tm-tag">已执行</span>

              <span v-else-if="row.enabled" class="tm-tag blue">启用</span>

              <span v-else class="tm-tag daily-hot">停用</span>

            </template>

          </el-table-column>

          <el-table-column label="上次执行" width="150">

            <template #default="{ row }">{{ row.last_run_at ? formatDate(row.last_run_at) : '-' }}</template>

          </el-table-column>

          <el-table-column label="操作" width="140" fixed="right">

            <template #default="{ row }">

              <el-button

                v-if="!(row.schedule_type === 'once' && row.executed)"

                link

                type="primary"

                @click="toggleSchedule(row)"

              >{{ row.enabled ? '停用' : '启用' }}</el-button>

              <el-button link type="danger" @click="removeSchedule(row)">删除</el-button>

            </template>

          </el-table-column>

        </el-table>

      </div>

    </div>



    <div class="tm-card" style="margin-top:16px">

      <div class="tm-card-header">

        <span class="title">系统健康</span>

        <div class="header-actions">

          <button class="tm-btn-ghost" :disabled="scraping" @click="triggerHotRefresh">触发 B 线协调</button>

          <button class="tm-btn-primary" :disabled="scraping" @click="triggerScrape">

            {{ scraping ? '执行中...' : '手动博主采集' }}

          </button>

        </div>

      </div>

      <div class="tm-card-body">

        <div v-if="health" class="health-grid">

          <div class="health-item">

            <span class="label">状态</span>

            <span class="tm-tag" :class="health.status === 'healthy' ? 'blue' : 'daily-hot'">

              {{ health.status }}

            </span>

          </div>

          <div class="health-item">

            <span class="label">数据库</span>

            <span>{{ health.database }}</span>

          </div>

          <div class="health-item">

            <span class="label">Redis</span>

            <span>{{ health.redis }}</span>

          </div>

          <div class="health-item">

            <span class="label">Celery</span>

            <span>{{ health.celery }}</span>

          </div>

          <div class="health-item">

            <span class="label">检查时间</span>

            <span>{{ formatDate(health.timestamp) }}</span>

          </div>

        </div>

      </div>

    </div>

  </div>

</template>



<script setup>

import { ref, onMounted } from 'vue'

import { ElMessage, ElMessageBox } from 'element-plus'

import api from '@/utils/api'

import { formatDate } from '@/utils/format'



const settings = ref({

  historical_view: 100000,

  daily_hot_avg_growth: 50,

  growth_window: 30,

  scrape_interval: 1440,

  recent_video_days: 10,

  recent_video_update_days: 3,

  doubao_enabled: true,

  daily_budget: 50,

  confidence: 60,

})

const health = ref(null)

const recStats = ref(null)

const scraping = ref(false)

const saving = ref(false)

const loading = ref(false)

const schedules = ref([])

const scheduleSaving = ref(false)

const scheduleForm = ref({

  name: '',

  schedule_type: 'daily',

  run_time_picker: '09:00',

  run_at_picker: null,

})



async function loadSchedules() {

  const { data } = await api.get('/system/collection-schedules')

  schedules.value = data

}



async function addSchedule() {

  const form = scheduleForm.value

  const payload = {

    name: form.name,

    schedule_type: form.schedule_type,

    timezone: 'Asia/Shanghai',

    enabled: true,

  }

  if (form.schedule_type === 'daily') {

    if (!form.run_time_picker) {

      ElMessage.warning('请选择每日执行时间')

      return

    }

    payload.run_time = form.run_time_picker

  } else {

    if (!form.run_at_picker) {

      ElMessage.warning('请选择单次执行时间')

      return

    }

    payload.run_at = new Date(form.run_at_picker).toISOString()

  }

  scheduleSaving.value = true

  try {

    await api.post('/system/collection-schedules', payload)

    ElMessage.success('采集闹钟已添加')

    scheduleForm.value.run_at_picker = null

    await loadSchedules()

  } finally {

    scheduleSaving.value = false

  }

}



async function toggleSchedule(row) {

  await api.put(`/system/collection-schedules/${row.id}`, { enabled: !row.enabled })

  await loadSchedules()

}



async function removeSchedule(row) {

  await ElMessageBox.confirm('确定删除该采集闹钟？', '确认')

  await api.delete(`/system/collection-schedules/${row.id}`)

  ElMessage.success('已删除')

  await loadSchedules()

}



async function loadSettings() {

  loading.value = true

  try {

    const { data } = await api.get('/system/settings')

    settings.value = { ...settings.value, ...data }

  } catch {

    ElMessage.error('加载系统设置失败')

  } finally {

    loading.value = false

  }

}



async function saveSettings() {

  saving.value = true

  try {

    const { data } = await api.put('/system/settings', settings.value)

    settings.value = { ...settings.value, ...data }

    ElMessage.success('设置已保存')

  } catch {

    ElMessage.error('保存失败')

  } finally {

    saving.value = false

  }

}



onMounted(async () => {

  try {

    await loadSettings()

    await loadSchedules()

    const [h, r] = await Promise.all([

      api.get('/system/health'),

      api.get('/recognition/stats'),

    ])

    health.value = h.data

    recStats.value = r.data

  } catch {}

})



async function triggerHotRefresh() {

  scraping.value = true

  try {

    const { data } = await api.post('/system/tasks/hot_update_coordinator/trigger')

    ElMessage.success(data.message || '热门更新 B 线协调任务已执行')

  } finally {

    scraping.value = false

  }

}



async function triggerScrape() {

  scraping.value = true

  try {

    await api.post('/system/tasks/scrape_all/trigger')

    ElMessage.success('采集任务已触发')

  } finally {

    scraping.value = false

  }

}

</script>



<style scoped>

.page { animation: fadeIn 0.4s ease; }

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.unit {
  margin-left: 8px;
  font-size: 12px;
  color: var(--tm-text-muted);
}

.settings-form :deep(.el-form-item) { margin-bottom: 18px; }

.schedule-hint { margin-bottom: 16px; }

.schedule-form { margin-bottom: 16px; flex-wrap: wrap; }

.hint { margin-top: 8px; font-size: 12px; color: var(--tm-text-muted); }

.rec-stats { margin-top: 8px; }

.cost-line { margin-top: 14px; font-size: 13px; color: var(--tm-text-secondary); }

.health-grid {

  display: grid;

  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));

  gap: 16px;

}

.health-item {

  background: var(--tm-surface-muted);

  border-radius: var(--tm-radius-md);

  padding: 16px 18px;

}

.health-item .label {

  display: block;

  font-size: 12px;

  color: var(--tm-text-muted);

  margin-bottom: 8px;

}

.health-item span:last-child { font-size: 14px; font-weight: 600; color: var(--tm-text); }

.settings-hint {
  font-size: 13px;
  color: var(--tm-text-muted);
  line-height: 1.5;
  margin: 0 0 16px;
}

@keyframes fadeIn {

  from { opacity: 0; transform: translateY(8px); }

  to { opacity: 1; transform: translateY(0); }

}

</style>

