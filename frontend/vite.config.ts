import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // 백엔드(FastAPI, :8000)로 프록시 — same-origin이라 CORS/쿠키 SameSite
      // 이슈 없이 개발 가능. 프로덕션 배포 시에는 별도 리버스 프록시로 대체.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
