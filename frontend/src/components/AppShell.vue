<script setup>
import { computed } from 'vue'
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
])

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
</script>

<template>
  <div class="shell">
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
      </div>

      <nav v-if="nav.some((n) => n.show)" class="nav">
        <div class="nav-label">工作区</div>
        <router-link
          v-for="item in nav.filter((n) => n.show)"
          :key="item.name"
          :to="{ name: item.name }"
          class="nav-item"
          @click="closeNav"
        >
          <span class="ico"><Icon :name="item.icon" /></span>
          {{ item.label }}
        </router-link>
      </nav>

      <div class="sidebar-foot">
        <a class="nav-item" href="/portal" target="_blank" rel="noopener">
          <span class="ico"><Icon name="eye" /></span>
          访客门户
          <span class="ico" style="margin-left: auto"><Icon name="external" :size="13" /></span>
        </a>
        <button class="userchip" @click="logout" title="退出登录">
          <span class="avatar">{{ (user?.display_name || user?.username || '?').slice(0, 1) }}</span>
          <span class="who">
            <b>{{ user?.display_name || user?.username }}</b>
            <span>{{ roleLabel }}</span>
          </span>
          <span style="margin-left: auto; color: var(--ink-4)"><Icon name="logout" :size="14" /></span>
        </button>
      </div>
    </aside>

    <main class="main">
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
