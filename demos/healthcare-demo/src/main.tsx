import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

// Healthcare demo is dark-mode only for enterprise walkthroughs.
localStorage.setItem('edon_theme', 'dark')
document.documentElement.classList.remove('light')
document.documentElement.classList.add('dark')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
