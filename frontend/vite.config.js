import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api/': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        // 禁用代理响应缓冲，确保 SSE 流式事件实时传递
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            // 告诉后端不要压缩响应（压缩会导致缓冲）
            proxyReq.setHeader('Accept-Encoding', 'identity')
          })
        },
      },
    },
  },
})
