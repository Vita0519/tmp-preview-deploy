import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const target = process.env.PV_API || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 注意：键是前缀匹配，写 '/p' 会把前端路由 /projects 一起吃进后端，
      // 于是项目页拿到的是 dist 里的旧 HTML。用 ^/p/ 锚定到真正的预览路径。
      '/api': { target, changeOrigin: true },
      '^/p/': { target, changeOrigin: true },
      '^/v/': { target, changeOrigin: true },
      '^/download/': { target, changeOrigin: true },
      '^/$': { target, changeOrigin: true },
      '/portal': { target, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    chunkSizeWarningLimit: 600,
  },
})
