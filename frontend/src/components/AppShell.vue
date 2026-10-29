<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { store, toast } from '../store'
import { api } from '../api'
import Icon from './Icon.vue'

const route = useRoute()
const router = useRouter()

const user = computed(() => store.user)
const isAdmin = computed(() => store.user?.role === 'admin')
const nav = computed(() => [
  { name: 'projects', label: '项目', icon: 'folder', show: true },
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
        <div class="brand-mark">P</div>
        <div class="brand-text">
          <b>{{ store.siteTitle }}</b>
          <span>临时预览 · 控制台</span>
        </div>
      </div>

      <nav class="nav">
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
            <span>{{ isAdmin ? '管理员' : '成员 Agent' }}</span>
          </span>
          <span style="margin-left: auto; color: var(--ink-4)"><Icon name="logout" :size="14" /></span>
        </button>
      </div>
    </aside>

    <main class="main">
      <slot />
    </main>
  </div>
</template>
