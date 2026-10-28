import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { defineConfig } from 'vite'

/** 开发期与预览期都走同源代理；正式环境由 Nginx 提供静态文件并代理 /api。 */
const apiProxy = {
  '/api': {
    target: process.env.UAMS_BACKEND_URL || 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
}

// 仅允许指定的 Cloudflare Tunnel 域名（开发临时隧道）
const allowedHosts = ['.trycloudflare.com']

export default defineConfig({
  plugins: [
    vue(),
    // 按需自动导入 Element Plus，避免全量引入
    AutoImport({ resolvers: [ElementPlusResolver()] }),
    Components({ resolvers: [ElementPlusResolver()] }),
  ],

  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },

  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts,
    proxy: apiProxy,
  },

  preview: {
    host: '0.0.0.0',
    port: 4173,
    allowedHosts,
    proxy: apiProxy,
  },

  // 说明：页面已按路由动态加载。曾尝试用 Rolldown codeSplitting 把
  // Element Plus 拆成多个 vendor chunk，但触发 vendor 初始化顺序的运行时错误
  // （TypeError），因此不启用自定义拆包；构建体积警告作为已知限制记录，
  // 不通过提高警告阈值或强行拆包来掩盖。
})
