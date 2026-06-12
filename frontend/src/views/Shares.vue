<template>

  <div class="page">

    <div class="tm-card">

      <div class="tm-card-header">

        <span class="title">分享数据</span>

      </div>

      <div class="tm-card-body">

        <div class="tm-search-bar" style="margin-bottom:0">

          <div class="tm-field">

            <label>目标用户</label>

            <el-select v-model="form.target_user_id" placeholder="选择用户" style="width:160px">

              <el-option v-for="u in users" :key="u.id" :label="u.username" :value="u.id" />

            </el-select>

          </div>

          <div class="tm-field">

            <label>视频 ID</label>

            <input v-model.number="form.video_id" type="number" placeholder="输入视频 ID" />

          </div>

          <button class="tm-btn-primary" @click="handleShare">分享</button>

        </div>

      </div>

    </div>



    <div class="tm-card" style="margin-top:16px">

      <div class="tm-card-header">

        <span class="title">分享记录</span>

        <span class="count">{{ shares.length }} 条</span>

      </div>

      <div class="tm-card-body" style="padding-top:0">

        <el-table :data="shares" stripe v-loading="loading">

          <el-table-column label="封面" width="80">

            <template #default="{ row }">

              <img :src="row.video?.cover_url" class="thumb" />

            </template>

          </el-table-column>

          <el-table-column prop="video.title" label="视频标题" show-overflow-tooltip />

          <el-table-column prop="target_username" label="分享给" width="120" />

          <el-table-column prop="shared_at" label="分享时间" width="170">

            <template #default="{ row }">{{ formatDate(row.shared_at) }}</template>

          </el-table-column>

          <el-table-column label="操作" width="120">

            <template #default="{ row }">

              <el-button link type="primary" @click="$router.push(`/videos/${row.video.id}`)">查看</el-button>

              <el-button link type="danger" @click="handleDelete(row)">取消</el-button>

            </template>

          </el-table-column>

        </el-table>

        <div v-if="!loading && !shares.length" class="empty-hint">暂无分享记录</div>

      </div>

    </div>

  </div>

</template>



<script setup>

import { ref, onMounted } from 'vue'

import { ElMessage } from 'element-plus'

import api from '@/utils/api'

import { formatDate } from '@/utils/format'



const users = ref([])

const shares = ref([])

const loading = ref(false)

const form = ref({ target_user_id: null, video_id: null })



async function loadData() {

  loading.value = true

  try {

    const [u, s] = await Promise.all([api.get('/users'), api.get('/shares')])

    users.value = u.data.filter(x => x.role !== 'super_admin' && x.role !== 'admin')

    shares.value = s.data

  } finally {

    loading.value = false

  }

}



async function handleShare() {

  if (!form.value.target_user_id || !form.value.video_id) {

    ElMessage.warning('请选择用户并填写视频 ID')

    return

  }

  await api.post('/shares', form.value)

  ElMessage.success('分享成功')

  form.value = { target_user_id: null, video_id: null }

  await loadData()

}



async function handleDelete(row) {

  await api.delete(`/shares/${row.id}`)

  ElMessage.success('已取消分享')

  await loadData()

}



onMounted(loadData)

</script>



<style scoped>

.page { animation: fadeIn 0.4s ease; }

.count { font-size: 13px; color: var(--tm-text-muted); }

.thumb { width: 50px; height: 70px; object-fit: cover; border-radius: 8px; }

.empty-hint { text-align: center; padding: 32px; color: var(--tm-text-muted); font-size: 14px; }

@keyframes fadeIn {

  from { opacity: 0; transform: translateY(8px); }

  to { opacity: 1; transform: translateY(0); }

}

</style>

