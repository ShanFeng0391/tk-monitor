<template>
  <div class="page">
    <div class="tm-card">
      <div class="tm-card-body favorites-body">
        <div class="favorites-toolbar">
          <span class="count">{{ favorites.length ? `${favorites.length} 条` : '暂无收藏' }}</span>
          <button
            type="button"
            class="batch-btn"
            :disabled="!selected.length"
            @click="batchRemove"
          >
            批量取消收藏
          </button>
        </div>

        <el-table
          :data="favorites"
          v-loading="loading"
          stripe
          class="favorites-table"
          @selection-change="sel => selected = sel"
        >
          <el-table-column type="selection" width="46" />
          <el-table-column label="封面" width="76" align="center">
            <template #default="{ row }">
              <img :src="row.video?.cover_url" class="thumb" alt="" />
            </template>
          </el-table-column>
          <el-table-column label="影视剧名称" width="132" show-overflow-tooltip>
            <template #default="{ row }">
              <router-link
                v-if="row.video?.drama_name"
                :to="dramaPath(row.video.drama_name)"
                class="drama-link"
                @click.stop
              >
                {{ row.video.drama_name }}
              </router-link>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="类型" min-width="220" class-name="col-type" show-overflow-tooltip>
            <template #default="{ row }">
              <span
                v-if="row.video?.drama_type"
                class="type-tag"
                :title="row.video.drama_type"
              >{{ row.video.drama_type }}</span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="博主粉丝量" width="104" align="right">
            <template #default="{ row }">
              {{ row.video?.creator_follower_count ? formatNum(row.video.creator_follower_count) : '—' }}
            </template>
          </el-table-column>
          <el-table-column label="播放量" width="92" align="right">
            <template #default="{ row }">
              {{ formatNum(row.video?.view_count) }}
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="260" class-name="col-note">
            <template #default="{ row }">
              <div class="note-cell">
                <div class="note-box">
                  <span v-if="row.note" class="note-text" :title="row.note">{{ row.note }}</span>
                  <span v-else class="note-empty">暂无备注</span>
                  <div class="note-actions">
                    <el-dropdown
                      v-if="row.note"
                      trigger="click"
                      @command="cmd => handleNoteCommand(cmd, row)"
                    >
                      <button type="button" class="note-btn icon-btn" title="备注操作">
                        <el-icon><EditPen /></el-icon>
                      </button>
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item command="edit">编辑备注</el-dropdown-item>
                          <el-dropdown-item command="delete" divided class="note-menu-delete">
                            删除备注
                          </el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                    <button
                      v-else
                      type="button"
                      class="note-btn icon-btn"
                      title="添加备注"
                      @click="openNoteDialog(row)"
                    >
                      <el-icon><EditPen /></el-icon>
                    </button>
                  </div>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="64" align="center">
            <template #default="{ row }">
              <el-button link type="primary" @click="$router.push(`/videos/${row.video.id}`)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog
      v-model="noteDialogVisible"
      :title="noteDialogTitle"
      width="480px"
      destroy-on-close
      @closed="resetNoteDialog"
    >
      <el-input
        v-model="noteDraft"
        type="textarea"
        :rows="4"
        maxlength="500"
        show-word-limit
        placeholder="输入收藏备注，便于后续检索与回顾"
      />
      <template #footer>
        <el-button @click="noteDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="noteSaving" @click="saveNote">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api'
import { formatNum } from '@/utils/format'
import { dramaPath } from '@/utils/navLinks'

const favorites = ref([])
const loading = ref(false)
const selected = ref([])

const noteDialogVisible = ref(false)
const noteDraft = ref('')
const noteSaving = ref(false)
const editingFavorite = ref(null)

const noteDialogTitle = computed(() => {
  const name = editingFavorite.value?.video?.drama_name || '收藏项'
  return editingFavorite.value?.note ? `编辑备注 · ${name}` : `添加备注 · ${name}`
})

async function loadFavorites() {
  loading.value = true
  selected.value = []
  try {
    const { data } = await api.get('/favorites')
    favorites.value = data
  } finally {
    loading.value = false
  }
}

async function batchRemove() {
  if (!selected.value.length) return
  const ids = selected.value.map(f => f.id)
  try {
    await api.delete('/favorites/batch', { data: { ids } })
    ElMessage.success('已取消收藏')
    await loadFavorites()
  } catch {
    /* 错误提示由 api 拦截器处理 */
  }
}

function openNoteDialog(row) {
  editingFavorite.value = row
  noteDraft.value = row.note || ''
  noteDialogVisible.value = true
}

function handleNoteCommand(command, row) {
  if (command === 'edit') openNoteDialog(row)
  else if (command === 'delete') clearNote(row)
}

function resetNoteDialog() {
  editingFavorite.value = null
  noteDraft.value = ''
}

async function saveNote() {
  if (!editingFavorite.value) return
  noteSaving.value = true
  try {
    const note = noteDraft.value.trim()
    const { data } = await api.patch(`/favorites/${editingFavorite.value.id}`, { note })
    const idx = favorites.value.findIndex(f => f.id === data.id)
    if (idx >= 0) favorites.value[idx] = data
    ElMessage.success(note ? '备注已保存' : '备注已清空')
    noteDialogVisible.value = false
  } finally {
    noteSaving.value = false
  }
}

async function clearNote(row) {
  await ElMessageBox.confirm('确定删除这条收藏备注吗？', '删除备注', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
  const { data } = await api.patch(`/favorites/${row.id}`, { note: '' })
  const idx = favorites.value.findIndex(f => f.id === data.id)
  if (idx >= 0) favorites.value[idx] = data
  ElMessage.success('备注已删除')
}

onMounted(loadFavorites)
</script>

<style scoped>
.page { animation: fadeIn 0.4s ease; }

.favorites-body {
  padding-top: 0;
}

.favorites-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 44px;
  padding: 8px 0 12px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--tm-border);
}

.batch-btn {
  flex-shrink: 0;
  height: 30px;
  padding: 0 14px;
  border: 1px solid rgba(245, 108, 108, 0.45);
  border-radius: var(--tm-radius-pill);
  background: rgba(245, 108, 108, 0.08);
  color: #e85d5d;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s, opacity 0.2s;
}

.batch-btn:hover:not(:disabled) {
  background: rgba(245, 108, 108, 0.16);
  border-color: #f56c6c;
}

.batch-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.count {
  font-size: 13px;
  color: var(--tm-text-muted);
  font-weight: 500;
}

.favorites-table :deep(.el-table__header th) {
  background: var(--tm-surface-muted);
  font-size: 12px;
  color: var(--tm-text-secondary);
}

.favorites-table :deep(.el-table__cell) {
  vertical-align: middle;
}

.favorites-table :deep(.col-type .cell) {
  line-height: 1.45;
}

.favorites-table :deep(.col-note .cell) {
  padding-top: 8px;
  padding-bottom: 8px;
}

.thumb {
  width: 44px;
  height: 58px;
  object-fit: cover;
  border-radius: 8px;
  display: block;
  margin: 0 auto;
}

.drama-link {
  color: var(--tm-purple);
  font-weight: 600;
  text-decoration: none;
}

.drama-link:hover {
  text-decoration: underline;
}

.type-tag {
  display: inline-block;
  max-width: 100%;
  padding: 4px 10px;
  border-radius: 8px;
  background: rgba(107, 140, 255, 0.12);
  color: var(--tm-blue);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.45;
  white-space: normal;
  word-break: break-word;
}

.note-cell {
  min-width: 0;
}

.note-box {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  padding: 6px 8px 6px 10px;
  border-radius: 10px;
  background: #f7f8fa;
  border: 1px solid #ebeef2;
}

.note-text {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--tm-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.note-empty {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--tm-text-muted);
}

.note-actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
}

.note-actions :deep(.el-dropdown) {
  line-height: 0;
}

.note-btn {
  border: none;
  cursor: pointer;
  box-shadow: none;
  -webkit-tap-highlight-color: transparent;
}

.note-btn.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--tm-text-secondary);
  font-size: 15px;
  transition: color 0.15s, background 0.15s;
}

.note-btn.icon-btn:hover {
  background: rgba(0, 47, 167, 0.08);
  color: var(--tm-blue);
}

.note-btn.icon-btn:focus,
.note-btn.icon-btn:focus-visible,
.note-btn.icon-btn:active {
  outline: none;
  box-shadow: none;
}

.note-actions :deep(.note-menu-delete) {
  color: #e85d5d;
}

.note-actions :deep(.note-menu-delete:hover) {
  color: #e85d5d;
  background: rgba(245, 108, 108, 0.1);
}

.muted {
  color: var(--tm-text-muted);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
