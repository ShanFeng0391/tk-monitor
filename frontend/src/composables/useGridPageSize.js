import { ref, onMounted, onUnmounted } from 'vue'

/** 根据视口高度计算 3 列网格行数，填满列表区、避免底部大块空白 */
const LAYOUT = {
  reservedHeight: 300,
  rowHeight: 92,
  minRows: 4,
  maxRows: 7,
}

export function useGridPageSize() {
  const pageSize = ref(12)

  function sync() {
    const w = window.innerWidth
    const h = window.innerHeight

    let cols = 3
    if (w <= 640) cols = 1
    else if (w <= 1180) cols = 2

    const available = Math.max(h - LAYOUT.reservedHeight, LAYOUT.rowHeight * LAYOUT.minRows)
    let rows = Math.floor(available / LAYOUT.rowHeight)
    rows = Math.max(LAYOUT.minRows, Math.min(LAYOUT.maxRows, rows))

    pageSize.value = rows * cols
  }

  onMounted(() => {
    sync()
    window.addEventListener('resize', sync)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', sync)
  })

  return pageSize
}
