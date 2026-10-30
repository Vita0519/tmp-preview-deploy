import { createApp } from 'vue'
import App from './App.vue'
import { router, ensureUser } from './router'
import { store } from './store'
import { applyPalette } from './theme'
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
  } catch {}
  await ensureUser()
  app.mount('#app')
}

boot()
