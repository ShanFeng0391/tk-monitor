<template>
  <div class="app-layout" :class="{ 'app-layout--fill': isFillPage }">
    <aside class="sidebar">
      <div class="brand">
        <svg class="brand-icon" width="20" height="20" viewBox="0 0 24 24" fill="none">
          <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5L12 2Z" fill="#111"/>
        </svg>
        <span>TikTok Monitor</span>
      </div>

      <nav class="nav">
        <router-link
          v-for="item in visibleNavItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
        >
          <span class="dot" :class="item.accent"></span>
          <span>{{ item.label }}</span>
        </router-link>

        <template v-if="auth.isUserManager">
          <div class="nav-divider">管理</div>
          <router-link
            v-for="item in visibleAdminItems"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="{ active: isActive(item.path) }"
          >
            <span class="dot" :class="item.accent"></span>
            <span>{{ item.label }}</span>
          </router-link>
        </template>
      </nav>

      <div class="sidebar-footer">
        <div class="user-chip">
          <span class="avatar">{{ auth.user?.username?.[0]?.toUpperCase() || 'U' }}</span>
          <div>
            <div class="name">{{ auth.user?.username }}</div>
            <div class="role">{{ auth.roleLabel }}</div>
          </div>
        </div>
        <button class="logout-btn" @click="handleLogout">退出</button>
      </div>
    </aside>

    <div
      class="content-area"
      :class="{
        'content-area--fill': isFillPage,
        'content-area--scroll': isFillPage && route.name === 'VideoDetail',
      }"
    >
      <header class="topbar">
        <div class="topbar-main">
          <h1>{{ pageTitle }}</h1>
        </div>
        <CategorySlider v-if="showCategoryFilter" />
      </header>
      <main class="page-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useCategoryFilterStore } from '@/stores/categoryFilter'
import CategorySlider from '@/components/CategorySlider.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const categoryStore = useCategoryFilterStore()

const showCategoryFilter = computed(() => {
  const path = route.path
  return path === '/dashboard' || path === '/viral' || path === '/daily-hot' || path === '/dramas'
})

onMounted(() => {
  categoryStore.loadGroups()
})

const visibleNavItems = computed(() =>
  navItems.filter((item) => !(item.hideForAdmin && auth.isUserManager))
)

const visibleAdminItems = computed(() => {
  if (!(auth.canAccessMonitorAdmin || auth.isTierAdmin)) return []
  return adminItems.filter((item) => !item.superAdminOnly || auth.isSuperAdmin)
})

const navItems = [
  { path: '/dashboard', label: '仪表盘', accent: 'purple' },
  { path: '/viral', label: '爆款视频', accent: 'purple' },
  { path: '/daily-hot', label: '当日热门', accent: 'orange' },
  { path: '/monitor', label: '监控管理', accent: 'dark', hideForAdmin: true },
  { path: '/dramas', label: '影视剧数据', accent: 'blue' },
  { path: '/favorites', label: '我的收藏', accent: 'dark' },
]

const adminItems = [
  { path: '/monitor', label: '监控管理', accent: 'purple' },
  { path: '/admin/users', label: '用户管理', accent: 'blue' },
  { path: '/admin/proxies', label: '代理池', accent: 'orange', superAdminOnly: true },
  { path: '/admin/cluster', label: '集群监控', accent: 'purple', superAdminOnly: true },
]

const titles = {
  '/dashboard': '仪表盘',
  '/viral': '爆款视频',
  '/daily-hot': '当日热门',
  '/monitor': '监控管理',
  '/dramas': '影视剧数据',
  '/favorites': '我的收藏',
  '/admin/users': '用户管理',
  '/admin/proxies': '代理池',
  '/admin/cluster': '集群监控',
}

const pageTitle = computed(() => {
  if (route.path.startsWith('/videos/') && route.name === 'VideoDetail') return '视频详情'
  if (route.path.startsWith('/dramas/')) return '影视剧详情'
  if (route.path.match(/^\/collections\/\d+\/hot/)) return '合集热门'
  return titles[route.path] || 'TikTok Monitor'
})

const isFillPage = computed(() => {
  const name = route.name
  return name === 'VideoDetail' || name === 'Viral' || name === 'MonitorManagement'
})

function isActive(path) {
  if (path === '/viral') {
    if (route.name === 'VideoDetail') return false
    return route.path === '/viral' || route.path === '/historical-viral' || route.path === '/videos'
  }
  if (path === '/daily-hot') {
    return route.path === '/daily-hot' || route.path === '/hot'
  }
  return route.path === path || route.path.startsWith(path + '/')
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.app-layout {
  display: flex;
  width: 100%;
  min-height: 100vh;
  background: var(--tm-bg);
  padding: 16px;
  gap: 16px;
  box-sizing: border-box;
  align-items: stretch;
}

.sidebar {
  width: 240px;
  flex-shrink: 0;
  background: var(--tm-surface);
  border-radius: var(--tm-radius-lg);
  box-shadow: var(--tm-shadow-sm);
  display: flex;
  flex-direction: column;
  padding: 20px 14px;
  min-height: 0;
  overflow: hidden;
  align-self: stretch;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px 20px;
  font-size: 15px;
  font-weight: 700;
  color: var(--tm-text);
  letter-spacing: -0.02em;
}

.brand-icon {
  animation: starSpin 10s linear infinite;
}

.nav {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  text-decoration: none;
  color: var(--tm-text-secondary);
  font-size: 14px;
  transition: background 0.2s, color 0.2s;
}

.nav-item:hover {
  background: var(--tm-surface-muted);
  color: var(--tm-text);
}

.nav-item.active {
  background: var(--tm-black);
  color: #fff;
}

.nav-item.active .dot.purple { background: #c89de0; }
.nav-item.active .dot.orange { background: #ffb07a; }
.nav-item.active .dot.blue { background: #6b8cff; }
.nav-item.active .dot.dark { background: #aaa; }

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot.purple { background: var(--tm-purple); }
.dot.orange { background: var(--tm-orange); }
.dot.blue { background: var(--tm-blue); }
.dot.dark { background: #ccc; }

.nav-divider {
  margin: 14px 12px 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--tm-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.sidebar-footer {
  border-top: 1px solid var(--tm-border);
  padding-top: 14px;
  margin-top: auto;
  flex-shrink: 0;
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 8px 12px;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--tm-purple);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 14px;
}

.name {
  font-size: 14px;
  font-weight: 600;
  color: var(--tm-text);
}

.role {
  font-size: 12px;
  color: var(--tm-text-muted);
}

.logout-btn {
  width: 100%;
  height: 38px;
  border: 1.5px solid var(--tm-border);
  border-radius: var(--tm-radius-pill);
  background: transparent;
  color: var(--tm-text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.logout-btn:hover {
  border-color: var(--tm-text);
  color: var(--tm-text);
}

.app-layout--fill {
  height: 100vh;
  max-height: 100vh;
  min-height: 100vh;
  overflow: hidden;
  align-items: stretch;
}

.app-layout--fill .sidebar,
.app-layout--fill .content-area {
  min-height: 0;
  align-self: stretch;
}

.content-area {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.content-area--fill .topbar {
  padding: 18px 24px;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.content-area--fill .page-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.content-area--fill.content-area--scroll .page-content {
  overflow: auto;
}

.content-area--fill {
  overflow: hidden;
  min-height: 0;
}

.topbar {
  background: var(--tm-surface);
  border-radius: var(--tm-radius-lg);
  box-shadow: var(--tm-shadow-sm);
  padding: 18px 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.topbar-main {
  min-width: 0;
  flex: 1;
}

.topbar h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.03em;
}

.page-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

@keyframes starSpin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 960px) {
  .app-layout {
    flex-direction: column;
    padding: 10px;
    min-height: 100vh;
    height: auto;
  }
  .app-layout--fill {
    height: auto;
    max-height: none;
    min-height: 100vh;
  }
  .sidebar {
    width: 100%;
  }
  .nav {
    flex-direction: row;
    flex-wrap: wrap;
  }
}
</style>
