import { createRouter, createWebHistory } from 'vue-router'
import { api, setUnauthorizedHandler } from './api'
import { store } from './store'

const routes = [
  { path: '/login', name: 'login', component: () => import('./views/Login.vue'), meta: { bare: true } },
  { path: '/', name: 'projects', component: () => import('./views/Projects.vue') },
  { path: '/agents', name: 'agents', component: () => import('./views/Agents.vue'), meta: { admin: true } },
  { path: '/settings', name: 'settings', component: () => import('./views/Settings.vue'), meta: { admin: true } },
  { path: '/:pathMatch(.*)*', name: 'missing', component: () => import('./views/Missing.vue') },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

let booted = false
export async function ensureUser() {
  if (store.user) return store.user
  try {
    const d = await api.me()
    store.user = d.user
    if (d.api_key) store.apiKey = d.api_key
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
