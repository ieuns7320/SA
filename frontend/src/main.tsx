import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { getInitialTheme } from './theme'

// React가 마운트되기 전에 동기적으로 세팅 — 안 그러면 첫 렌더에 다크 기본값이
// 잠깐 보였다가 라이트로 바뀌는 깜빡임(FOUC)이 생긴다.
document.documentElement.setAttribute('data-theme', getInitialTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
