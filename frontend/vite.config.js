import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const target = process.env.PV_API || 'http://127.0.0.1:8010'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target, changeOrigin: true },
      '/p': { target, changeOrigin: true },
      '/v': { target, changeOrigin: true },
      '/download': { target, changeOrigin: true },
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
