import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/login', name: 'Login', component: () => import('@/views/Login.vue'), meta: { public: true } },
  { path: '/register', name: 'Register', component: () => import('@/views/Register.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue') },
      {
        path: 'viral',
        name: 'Viral',
        component: () => import('@/views/HistoricalViral.vue'),
        meta: { navGroup: 'viral' },
      },
      {
        path: 'historical-viral',
        redirect: (to) => ({ path: '/viral', query: to.query }),
      },
      {
        path: 'videos',
        redirect: (to) => ({ path: '/viral', query: to.query }),
      },
      {
        path: 'daily-hot',
        name: 'DailyHot',
        component: () => import('@/views/DailyHotMarket.vue'),
        meta: { navGroup: 'daily-hot' },
      },
      { path: 'hot', redirect: (to) => ({ path: '/daily-hot', query: to.query }) },
      { path: 'collections', redirect: '/monitor' },
      { path: 'collections/:id/hot', name: 'CollectionHot', component: () => import('@/views/CollectionHot.vue') },
      { path: 'creators', redirect: '/monitor' },
      { path: 'monitor', name: 'MonitorManagement', component: () => import('@/views/MonitorManagement.vue') },
      { path: 'videos/:id', name: 'VideoDetail', component: () => import('@/views/VideoDetail.vue') },
      { path: 'favorites', name: 'Favorites', component: () => import('@/views/Favorites.vue') },
      { path: 'dramas', name: 'Dramas', component: () => import('@/views/Dramas.vue') },
      { path: 'dramas/:name', name: 'DramaDetail', component: () => import('@/views/DramaDetail.vue') },
      { path: 'admin/groups', redirect: '/monitor' },
      { path: 'admin/users', name: 'AdminUsers', component: () => import('@/views/AdminUsers.vue'), meta: { admin: true } },
      {
        path: 'admin/proxies',
        name: 'AdminProxies',
        component: () => import('@/views/AdminProxies.vue'),
        meta: { admin: true, superAdmin: true },
      },
      {
        path: 'admin/cluster',
        name: 'AdminCluster',
        component: () => import('@/views/AdminCluster.vue'),
        meta: { admin: true, superAdmin: true },
      },
      { path: 'admin/settings', redirect: '/monitor' },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, from, next) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isLoggedIn) {
    return next('/login')
  }
  if (auth.isLoggedIn && !auth.user) {
    await auth.fetchUser()
  }
  if (to.meta.admin && !auth.isUserManager) {
    return next('/dashboard')
  }
  if (to.meta.superAdmin && !auth.isSuperAdmin) {
    return next('/dashboard')
  }
  next()
})

export default router
