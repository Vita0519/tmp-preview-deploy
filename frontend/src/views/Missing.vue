<script setup>
import Icon from '../components/Icon.vue'
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <header class="topbar">
    <h1>页面不存在</h1>
  </header>
  <div class="content">
    <div class="panel">
      <div class="empty">
        <div class="ico"><Icon name="search" :size="16" /></div>
        <h3>这个地址没有对应页面</h3>
        <p>检查一下链接，或者回到项目管理页。</p>
        <button class="btn primary" @click="router.replace('/')">返回项目</button>
      </div>
    </div>
  </div>
</template>
