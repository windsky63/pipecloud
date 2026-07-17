import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

function readPositiveInteger(value, fallback) {
  const parsed = Number.parseInt(value, 10)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback
}

export default defineConfig(({ mode }) => {
  // Vite 自动加载 .env 文件；这里只读取 VITE_ 前缀，避免意外暴露服务端密钥。
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const proxyTimeout = readPositiveInteger(env.VITE_PROXY_TIMEOUT_MS, 20 * 60 * 1000)

  return {
    plugins: [vue()],
    server: {
      // 默认允许局域网开发访问，部署差异通过环境变量覆盖。
      host: env.VITE_DEV_HOST || '0.0.0.0',
      port: readPositiveInteger(env.VITE_DEV_PORT, 5173),
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
          timeout: proxyTimeout,
          proxyTimeout,
        },
      },
      fs: {
        strict: true,
      },
    },
  }
})
