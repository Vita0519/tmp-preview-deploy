import { createRouter, createWebHistory } from 'vue-router'
import { api, setUnauthorizedHandler } from './api'
import { store } from './store'

const routes = [
  { path: '/login', name: 'login', component: () => import('./views/Login.vue'), meta: { bare: true } },
  { path: '/', name: 'projects', component: () => import('./views/Projects.vue') },
  { path: '/logs', name: 'logs', component: () => import('./views/Logs.vue') },
  { path: '/agents', name: 'agents', component: () => import('./views/Agents.vue'), meta: { admin: true } },
  { path: '/settings', name: 'settings', component: () => import('./views/Settings.vue'), meta: { admin: true } },
  { path: '/:pathMatch(.*)*', name: 'missing', component: () => import('./views/Missing.vue') },
]

export const router = createRouter({
  // v2.6.0：后台挂在 /admin 下，根路径留给访客门户；静态资源仍是 /assets（vite base 不变）
  history: createWebHistory('/admin/'),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

let booted = false
export async function ensureUser() {
  if (store.user) return store.user
  try {
    const d = await api.me()
    store.user = d.user
    booted = true
    return store.user
  } catch {
    store.user = null
    return null
  }
}

setUnauthorizedHandler(() => {
  store.user = null
  if (router.currentRoute.value.name !== 'login') {
    router.replace({ name: 'login', query: { next: router.currentRoute.value.fullPath } })
  }
})

router.beforeEach(async (to) => {
  if (to.meta.bare) return true
  const user = await ensureUser()
  if (!user) return { name: 'login', query: to.fullPath !== '/' ? { next: to.fullPath } : {} }
  if (to.meta.admin && user.role !== 'admin') return { name: 'projects' }
  return true
})
