<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from './components/AppShell.vue'
import Icon from './components/Icon.vue'
import { api } from './api'
import { resolveConfirm, store } from './store'

const route = useRoute()
const bare = computed(() => route.meta.bare)

// 管理员登录后自动检查一次新版本；出站失败就静默跳过，不打扰使用
const update = ref(null)
const SKIP_KEY = 'tp_skip_version'

function skipVersion() {
  try { localStorage.setItem(SKIP_KEY, update.value?.latest || '') } catch (e) {}
  update.value = null
}

async function checkUpdate() {
  try {
    const d = await api.get('/api/settings/version')
    if (!d?.ok || !d.has_update) return
    let skipped = ''
    try { skipped = localStorage.getItem(SKIP_KEY) || '' } catch (e) {}
    if (skipped === d.latest) return
    update.value = d
  } catch (e) {
    /* 检查失败不用提示 */
  }
}

// 登录页就挂载了，等角色变成 admin 再查（登录后才会发生）
watch(
  () => store.user?.role,
  (role) => { if (role === 'admin') checkUpdate() },
  { immediate: true }
)
</script>

<template>
  <router-view v-if="bare" />
  <AppShell v-else>
    <router-view />
  </AppShell>

  <div class="toastwrap">
    <div v-for="t in store.toasts" :key="t.id" class="toast" :class="{ err: t.type === 'err' }">
      <Icon :name="t.type === 'err' ? 'close' : 'check'" :size="16" />
      {{ t.message }}
    </div>
  </div>

  <template v-if="update">
    <div class="scrim" @click="update = null" />
    <div class="modal sm">
      <div class="modal-head">
        <h2>发现新版本 {{ update.latest }}</h2>
      </div>
      <div class="modal-body">
        <p class="muted" style="font-size: 12.5px; margin-bottom: 10px">
          当前版本 {{ update.current }}，最新版本 {{ update.latest }}。
        </p>
        <pre v-if="update.notes" class="upd-notes">{{ update.notes }}</pre>
      </div>
      <div class="modal-foot">
        <button class="btn ghost cancel" @click="skipVersion">跳过此版本</button>
        <button class="btn" @click="update = null">稍后</button>
        <a
          class="btn primary"
          :href="update.url"
          target="_blank"
          rel="noopener"
          @click="update = null"
        >去更新</a>
      </div>
    </div>
  </template>

  <template v-if="store.confirm">
    <div class="scrim" @click="resolveConfirm(false)" />
    <div class="modal sm">
      <div class="modal-head">
        <h2>{{ store.confirm.title }}</h2>
      </div>
      <div class="modal-body">
        <p class="muted" style="font-size: 12.5px; line-height: 1.65">{{ store.confirm.message }}</p>
      </div>
      <div class="modal-foot">
        <button class="btn ghost cancel" @click="resolveConfirm(false)">{{ store.confirm.cancelText }}</button>
        <button
          class="btn"
          :class="store.confirm.danger ? 'danger' : 'primary'"
          @click="resolveConfirm(true)"
        >
          {{ store.confirm.confirmText }}
        </button>
      </div>
    </div>
  </template>
</template>
