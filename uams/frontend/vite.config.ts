/*
import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { defineConfig } from 'vite'

/** 开发期与预览期都走同源代理，避免跨域；生产由 Nginx 等反向代理承担。
 *
 * 代理是「服务端 → 服务端」的转发，因此局域网用户用 `http://<服务器IP>:<前端端口>`
 * 访问时，浏览器只会请求同源的 `/api/*`，不会出现把 127.0.0.1 指向用户自己电脑的问题
 * （FIX-007 §十七）。 
const apiProxy = {
  '/api': {
    target: process.env.UAMS_BACKEND_URL || 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [
    vue(),
    // 按需自动导入，避免全量引入 Element Plus 拖慢首屏
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
    proxy: apiProxy,
  },
  preview: {
    // 生产构建后的静态服务（`npm run build && npm run preview`），同样支持 LAN 访问
    host: '0.0.0.0',
    port: 4173,
    proxy: apiProxy,
  },
})
*/


import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { defineConfig } from 'vite'

/** 开发期与预览期都走同源代理，避免跨域；生产由 Nginx 等反向代理承担。 */
const apiProxy = {
  '/api': {
    target: process.env.UAMS_BACKEND_URL || 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
}

// 仅允许指定的 Cloudflare Tunnel 域名
//const allowedHosts = [
//  'elatives-active-janet-concord.trycloudflare.com',
//]
const allowedHosts = [
  '.trycloudflare.com',
]


export default defineConfig({
  plugins: [
    vue(),
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
})
