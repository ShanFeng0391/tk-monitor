<template>
  <div class="page">
    <div class="tm-card">
      <div class="tm-card-body">
        <VideoGrid
          :videos="videos"
          :loading="loading"
          :total="total"
          :page="page"
          :page-size="pageSize"
          empty-text="该合集今日暂无热门视频"
          @page-change="onPageChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/utils/api'
import VideoGrid from '@/components/VideoGrid.vue'

const route = useRoute()
const videos = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)

async function loadVideos() {
  loading.value = true
  try {
    const { data } = await api.get(`/core/collections/${route.params.id}/daily-hot`, {
      params: { page: page.value, page_size: pageSize },
    })
    videos.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onPageChange(p) {
  page.value = p
  loadVideos()
}

onMounted(loadVideos)
watch(() => route.params.id, () => { page.value = 1; loadVideos() })
</script>
