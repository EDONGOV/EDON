import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

// Apply saved theme before first render to avoid flash
const savedTheme = localStorage.getItem('edon_theme') ?? 'dark'
document.documentElement.classList.add(savedTheme)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
