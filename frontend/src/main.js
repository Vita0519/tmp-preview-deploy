import { createApp } from 'vue'
import App from './App.vue'
import { router, ensureUser } from './router'
import { store } from './store'
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
    // 自定义站点图标同样在首屏换掉，免得标签页闪一下旧图标
    applySiteIcon(meta?.site_icon || null)
  } catch {}
  await ensureUser()
  app.mount('#app')
}

boot()
