<template>

  <div class="page">

    <div class="tm-card">

      <div class="tm-card-header">

        <span class="title">共享给我的数据</span>

        <span class="count">{{ shares.length }} 条</span>

      </div>

      <div class="tm-card-body" style="padding-top:0">

        <el-table :data="shares" v-loading="loading" stripe>

          <el-table-column label="封面" width="80">

            <template #default="{ row }">

              <img :src="row.video?.cover_url" class="thumb" />

            </template>

          </el-table-column>

          <el-table-column prop="video.title" label="标题" show-overflow-tooltip />

          <el-table-column label="播放量" width="110">

            <template #default="{ row }">{{ formatNum(row.video?.view_count) }}</template>

          </el-table-column>

          <el-table-column label="分类" width="100">

            <template #default="{ row }">

              <span v-if="row.video" class="tm-tag" :class="catClass(row.video)">

                {{ catLabel(row.video) }}

              </span>

            </template>

          </el-table-column>

          <el-table-column prop="shared_at" label="分享时间" width="170">

            <template #default="{ row }">{{ formatDate(row.shared_at) }}</template>

          </el-table-column>

          <el-table-column label="操作" width="90">

            <template #default="{ row }">

              <el-button link type="primary" @click="$router.push(`/videos/${row.video.id}`)">查看</el-button>

            </template>

          </el-table-column>

        </el-table>

        <div v-if="!loading && !shares.length" class="empty-hint">

          <div class="empty-icon">◎</div>

          <p>暂无共享数据</p>

        </div>

      </div>

    </div>

  </div>

</template>



<script setup>

import { ref, onMounted } from 'vue'

import api from '@/utils/api'

import { formatNum, formatDate, categoryLabel, categoryClass } from '@/utils/format'



const shares = ref([])

const loading = ref(false)



function catLabel(v) { return categoryLabel(v.category, v) }

function catClass(v) { return categoryClass(v.category, v) }



onMounted(async () => {

  loading.value = true

  try {

    const { data } = await api.get('/shares/received')

    shares.value = data

  } finally {

    loading.value = false

  }

})

</script>



<style scoped>

.page { animation: fadeIn 0.4s ease; }

.count { font-size: 13px; color: var(--tm-text-muted); }

.thumb { width: 50px; height: 70px; object-fit: cover; border-radius: 8px; }

.empty-hint { text-align: center; padding: 48px 20px; color: var(--tm-text-muted); }

.empty-icon { font-size: 32px; color: var(--tm-blue); margin-bottom: 10px; }

@keyframes fadeIn {

  from { opacity: 0; transform: translateY(8px); }

  to { opacity: 1; transform: translateY(0); }

}

</style>

