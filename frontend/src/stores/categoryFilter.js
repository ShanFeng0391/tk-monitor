import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/utils/api'

export const useCategoryFilterStore = defineStore('categoryFilter', () => {
  const groups = ref([])
  const selectedGroupId = ref(null)
  const loaded = ref(false)

  async function loadGroups() {
    if (loaded.value) return
    try {
      const { data } = await api.get('/groups')
      groups.value = data || []
      loaded.value = true
    } catch {
      groups.value = []
    }
  }

  function setGroupId(id) {
    selectedGroupId.value = id || null
  }

  function apiParams() {
    return selectedGroupId.value ? { group_id: selectedGroupId.value } : {}
  }

  return { groups, selectedGroupId, loaded, loadGroups, setGroupId, apiParams }
})
