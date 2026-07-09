import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    // Listen on every network interface so other devices on the LAN can
    // open the development site through this computer's IPv4 address.
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 20 * 60 * 1000,
        proxyTimeout: 20 * 60 * 1000,
      },
    },
    fs: {
      strict: false
    },
  },
})
