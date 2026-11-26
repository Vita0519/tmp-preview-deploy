<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { store, toast } from '../store'
import { api } from '../api'
import Icon from './Icon.vue'
import BrandMark from './BrandMark.vue'

const route = useRoute()
const router = useRouter()

const user = computed(() => store.user)
const isAdmin = computed(() => store.user?.role === 'admin')
const isViewer = computed(() => store.user?.role === 'viewer')
const roleLabel = computed(() => {
  const map = { viewer: '仅门户访客', publisher: '发布者', admin: '管理员' }
  return map[store.user?.role] || '发布者'
})
const nav = computed(() => [
  { name: 'projects', label: '项目', icon: 'folder', show: !isViewer.value },
  { name: 'agents', label: '成员', icon: 'users', show: isAdmin.value },
  { name: 'settings', label: '设置', icon: 'sliders', show: isAdmin.value },
  { name: 'logs', label: '日志', icon: 'clock', show: !isViewer.value },
])

// 侧栏折叠：只留图标（228px → 64px），选择记在本地，下次进来还是收起的
const mini = ref(localStorage.getItem('pv_nav_mini') === '1')
function toggleNav() {
  mini.value = !mini.value
  try {
    localStorage.setItem('pv_nav_mini', mini.value ? '1' : '0')
  } catch {
    /* 隐身模式下写不了，本次会话照样生效 */
  }
}

async function logout() {
  try {
    await api.logout()
  } catch {}
  store.user = null
  toast('已退出登录')
  router.replace('/login')
}

function closeNav() {
  store.mobileNav = false
}

// 新版本提醒：管理员进后台就查一次（后端 1 小时缓存），之后每 6 小时再查
const update = computed(() => store.update)
const dismissedVer = ref(localStorage.getItem('pv_upd_dismiss') || '')
const showUpd = computed(() => isAdmin.value && update.value?.latest && update.value.latest !== dismissedVer.value)
async function pollUpdate() {
  if (!isAdmin.value) return
  try {
    const d = await api.get('/api/settings/version')
    store.update = d?.ok && d.has_update ? d : null
  } catch {
    /* 网络不通就算了，不打扰 */
  }
}
function dismissUpd() {
  dismissedVer.value = update.value?.latest || ''
  try { localStorage.setItem('pv_upd_dismiss', dismissedVer.value) } catch {}
}
let updTimer = null
onMounted(() => {
  pollUpdate()
  updTimer = setInterval(pollUpdate, 6 * 3600 * 1000)
})
onUnmounted(() => clearInterval(updTimer))
</script>

<template>
  <div class="shell" :class="{ mini: mini }">
    <button class="mobile-toggle" aria-label="菜单" @click="store.mobileNav = !store.mobileNav">
      <Icon name="menu" :size="16" />
    </button>
    <div v-if="store.mobileNav" class="navscrim" @click="store.mobileNav = false" />
    <aside class="sidebar" :class="{ open: store.mobileNav }">
      <div class="brand">
        <BrandMark :size="30" />
        <div class="brand-text">
          <b>{{ store.siteTitle }}</b>
          <span>临时预览 · 控制台</span>
        </div>
        <button
          class="navtoggle"
          :title="mini ? '展开侧栏' : '收起侧栏'"
          :aria-label="mini ? '展开侧栏' : '收起侧栏'"
          :aria-expanded="!mini"
          @click="toggleNav"
        >
          <Icon name="chevron" :size="12" />
        </button>
      </div>

      <nav v-if="nav.some((n) => n.show)" class="nav">
        <div class="nav-label">工作区</div>
        <router-link
          v-for="item in nav.filter((n) => n.show)"
          :key="item.name"
          :to="{ name: item.name }"
          class="nav-item"
          :title="item.label"
          @click="closeNav"
        >
          <span class="ico"><Icon :name="item.icon" /></span>
          <span class="lbl">{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="sidebar-foot">
        <a class="nav-item" href="/portal" target="_blank" rel="noopener" title="访客门户（新窗口打开）">
          <span class="ico"><Icon name="eye" /></span>
          <span class="lbl">访客门户</span>
          <span class="ico out"><Icon name="external" :size="13" /></span>
        </a>
        <button class="userchip" :title="`${user?.display_name || user?.username} · ${roleLabel}（点击退出）`" @click="logout">
          <span class="avatar">{{ (user?.display_name || user?.username || '?').slice(0, 1) }}</span>
          <span class="who">
            <b>{{ user?.display_name || user?.username }}</b>
            <span>{{ roleLabel }}</span>
          </span>
          <span class="ico out" :style="{ color: 'var(--ink-4)' }"><Icon name="logout" :size="14" /></span>
        </button>
      </div>
    </aside>

    <main class="main">
      <div v-if="showUpd" class="updbar">
        <span>发现新版本 <b>v{{ update.latest }}</b>（当前 v{{ update.current }}）</span>
        <a v-if="update.url" :href="update.url" target="_blank" rel="noopener">查看更新内容</a>
        <router-link :to="{ name: 'settings', hash: '#about' }">去设置</router-link>
        <span class="grow" />
        <button class="x" title="这个版本不再提示" @click="dismissUpd">×</button>
      </div>
      <template v-if="isViewer">
        <header class="topbar">
          <h1>受限账号</h1>
          <span class="sub">仅可浏览访客门户</span>
        </header>
        <div class="content">
          <div class="panel" style="padding: 34px 24px; text-align: center">
            <div class="avatar" style="width: 42px; height: 42px; margin: 0 auto 12px; font-size: 16px">
              {{ (user?.display_name || user?.username || '?').slice(0, 1) }}
            </div>
            <h2 style="margin: 0 0 6px; font-size: 15px">这个账号只能看门户</h2>
            <p class="muted" style="margin: 0 auto 18px; max-width: 380px; font-size: 12.5px">
              你的角色是「仅门户访客」，可以浏览已发布的内容，但没有上传、管理项目的权限。需要发布请联系管理员调整角色。
            </p>
            <a class="btn primary" href="/portal" target="_blank" rel="noopener">
              <Icon name="eye" :size="13" /> 打开访客门户
            </a>
          </div>
        </div>
      </template>
      <slot v-else />
    </main>
  </div>
</template>

<style scoped>
.updbar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  margin: 12px 20px 0; padding: 9px 14px; border-radius: 9px; font-size: 12.5px;
  background: rgba(var(--ink-rgb, 0, 0, 0), 0.04); border: 1px solid var(--line, #ddd);
  border-left: 3px solid var(--brand, #4a7);
}
.updbar a { color: var(--brand); }
.updbar .grow { flex: 1; }
.updbar .x { background: none; border: 0; font-size: 16px; cursor: pointer; color: var(--ink-3, var(--ink-4)); }
</style>
