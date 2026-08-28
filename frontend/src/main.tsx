import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { initClientErrorReporting } from '@/lib/clientErrorReporter'

import App from './App.tsx'

import './index.css'

initClientErrorReporting()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
)
