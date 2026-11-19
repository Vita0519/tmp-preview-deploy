/*
 * tmp-preview（临时预览站）
 * Copyright (C) 2026 Vita0519<https://github.com/Vita0519/tmp-preview-deploy>
 * AGPL-3.0-only：全文见仓库根目录 LICENSE，署名要求见 NOTICE。保留本声明。
 */
import { createApp } from 'vue'
import App from './App.vue'
import { router, ensureUser } from './router'
import { store, applyTagRules } from './store'
import { applyPalette, applySiteIcon } from './theme'
import './styles.css'

const app = createApp(App)
app.use(router)

async function boot() {
  try {
    const meta = await fetch('/api/meta').then((r) => (r.ok ? r.json() : null))
    if (meta?.site_title) {
      store.siteTitle = meta.site_title
      document.title = `${meta.site_title} · 控制台`
    }
    // 主色跟着站点走，别让人先看到一屏墨绿再跳成蓝色
    if (meta?.theme) applyPalette(meta.theme)
    // 标签上限是管理员可调的，界面上的 (n/上限) 得跟后端的裁判口径一致
    applyTagRules(meta?.tags)
    // 自定义站点图标同样在首屏换掉，免得标签页闪一下旧图标
    applySiteIcon(meta?.site_icon || null)
    // 署名跟着仓库走：fork 了要改就改后端 config，前端不另设一份
    store.version = meta?.version || ''
    if (meta?.project) store.project = { ...store.project, ...meta.project }
  } catch {}
  await ensureUser()
  app.mount('#app')
}

boot()
