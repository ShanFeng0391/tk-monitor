<template>

  <div class="page">

    <div class="tm-card">

      <div class="tm-card-header"><span class="title">热门影视剧排行</span></div>

      <div class="tm-card-body" style="padding-top:0">

        <el-table

          :data="dramas"

          v-loading="loading"

          stripe

          @row-click="row => $router.push(`/dramas/${encodeURIComponent(row.drama_name)}`)"

          style="cursor:pointer"

        >

          <el-table-column prop="drama_name" label="影视剧名称" width="480" show-overflow-tooltip />

          <el-table-column prop="drama_type" label="类型" min-width="300" class-name="col-drama-type" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.drama_type" class="type-tag" :title="row.drama_type">{{ row.drama_type }}</span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>

          <el-table-column prop="total_videos" label="关联视频" width="100" />

          <el-table-column prop="total_views" label="总播放量" width="120">

            <template #default="{ row }">{{ formatNum(row.total_views) }}</template>

          </el-table-column>

          <el-table-column prop="viral_videos" label="爆款数" width="80" />

          <el-table-column prop="trend_direction" label="趋势" width="100">

            <template #default="{ row }">

              <span class="tm-tag" :class="row.trend_direction === 'rising' ? 'daily-hot' : 'dark'">

                {{ { rising: '上升', stable: '稳定', decline: '下降' }[row.trend_direction] || row.trend_direction }}

              </span>

            </template>

          </el-table-column>

        </el-table>

      </div>

    </div>

  </div>

</template>



<script setup>

import { ref, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import api from '@/utils/api'
import { formatNum } from '@/utils/format'
import { useCategoryFilterStore } from '@/stores/categoryFilter'

const categoryStore = useCategoryFilterStore()
const { selectedGroupId } = storeToRefs(categoryStore)



const dramas = ref([])

const loading = ref(false)



async function loadDramas() {
  loading.value = true
  try {
    const params = categoryStore.apiParams()
    const { data } = await api.get('/dramas/trending', { params })
    dramas.value = data.length ? data : (await api.get('/dramas', { params })).data
  } finally {
    loading.value = false
  }
}

onMounted(loadDramas)
watch(selectedGroupId, loadDramas)

</script>

<style scoped>
.page { animation: fadeIn 0.4s ease; }

.type-tag {
  display: inline-block;
  max-width: 100%;
  padding: 2px 10px;
  border-radius: 8px;
  background: rgba(107, 140, 255, 0.12);
  color: var(--tm-blue);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}

.muted {
  color: var(--tm-text-muted);
}

:deep(.col-drama-type .cell) {
  white-space: nowrap;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>