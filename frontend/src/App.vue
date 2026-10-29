<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from './components/AppShell.vue'
import Icon from './components/Icon.vue'
import { resolveConfirm, store } from './store'

const route = useRoute()
const bare = computed(() => route.meta.bare)
</script>

<template>
  <router-view v-if="bare" />
  <AppShell v-else>
    <router-view />
  </AppShell>

  <div class="toastwrap">
    <div v-for="t in store.toasts" :key="t.id" class="toast" :class="{ err: t.type === 'err' }">
      <Icon :name="t.type === 'err' ? 'close' : 'check'" :size="13" />
      {{ t.message }}
    </div>
  </div>

  <template v-if="store.confirm">
    <div class="scrim" @click="resolveConfirm(false)" />
    <div class="modal" style="width: 400px">
      <div class="modal-head">
        <h2>{{ store.confirm.title }}</h2>
      </div>
      <div class="modal-body">
        <p class="muted" style="font-size: 12.5px; line-height: 1.65">{{ store.confirm.message }}</p>
      </div>
      <div class="modal-foot">
        <button class="btn" @click="resolveConfirm(false)">{{ store.confirm.cancelText }}</button>
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
