<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { store, toast } from '../store'
import BrandMark from '../components/BrandMark.vue'

const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const busy = ref(false)
const err = ref('')
const pwInput = ref(null)

async function submit() {
  if (!username.value || !password.value) {
    err.value = '请填写账号和密码'
    return
  }
  busy.value = true
  err.value = ''
  try {
    const d = await api.login(username.value.trim(), password.value)
    store.user = d.user
    toast(`欢迎回来，${d.user.display_name}`)
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/'
    router.replace(next)
  } catch (e) {
    err.value = e.message || '登录失败'
  } finally {
    busy.value = false
  }
}

onMounted(() => pwInput.value?.focus())
</script>

<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="brand">
        <BrandMark :size="30" />
        <div class="brand-text">
          <b>{{ store.siteTitle }}</b>
          <span>临时预览 · 控制台</span>
        </div>
      </div>
      <h1>登录</h1>
      <p class="sub">管理员看全部项目，成员只看自己的。</p>
      <div v-if="err" class="err">{{ err }}</div>
      <form class="form" @submit.prevent="submit">
        <div class="frow">
          <label>账号</label>
          <input v-model="username" class="input" autocomplete="username" placeholder="用户名" />
        </div>
        <div class="frow">
          <label>密码</label>
          <input
            ref="pwInput"
            v-model="password"
            class="input"
            type="password"
            autocomplete="current-password"
            placeholder="密码"
          />
        </div>
        <button class="btn primary" type="submit" :disabled="busy" style="height: 34px; margin-top: 4px">
          {{ busy ? '登录中…' : '进入控制台' }}
        </button>
      </form>

      <!-- AGPL-3.0 §7(b) 附加条款要求的署名，别删 -->
      <a
        class="credit"
        :href="store.project.url"
        target="_blank"
        rel="noopener"
        :title="`${store.project.name} · ${store.project.license} · 作者 ${store.project.author}`"
      >
        Powered by {{ store.project.name }} · {{ store.project.license }}
      </a>
    </div>
  </div>
</template>
