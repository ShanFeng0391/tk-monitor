<template>
  <div v-if="groups.length" class="category-slider-wrap">
    <span class="category-slider-label">类别</span>
    <el-radio-group
      v-model="selected"
      size="small"
      class="category-slider"
    >
      <el-radio-button value="all">全部</el-radio-button>
      <el-radio-button
        v-for="group in groups"
        :key="group.id"
        :value="String(group.id)"
      >
        {{ group.name }}
      </el-radio-button>
    </el-radio-group>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useCategoryFilterStore } from '@/stores/categoryFilter'

const categoryStore = useCategoryFilterStore()
const { groups, selectedGroupId } = storeToRefs(categoryStore)

const selected = computed({
  get() {
    return selectedGroupId.value ? String(selectedGroupId.value) : 'all'
  },
  set(val) {
    categoryStore.setGroupId(val === 'all' ? null : Number(val))
  },
})
</script>

<style scoped>
.category-slider-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.category-slider-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--tm-text-muted);
  white-space: nowrap;
}

.category-slider :deep(.el-radio-button__inner) {
  border-color: var(--tm-border);
  background: var(--tm-surface);
  color: var(--tm-text);
  font-weight: 600;
  padding: 7px 14px;
  box-shadow: none;
}

.category-slider :deep(.el-radio-button:first-child .el-radio-button__inner) {
  border-radius: 999px 0 0 999px;
}

.category-slider :deep(.el-radio-button:last-child .el-radio-button__inner) {
  border-radius: 0 999px 999px 0;
}

.category-slider :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: var(--tm-black);
  border-color: var(--tm-black);
  color: #fff;
  box-shadow: none;
}

.category-slider :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner:hover) {
  color: #fff;
}
</style>
