import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import './styles/app.css'
import { createRoot } from 'react-dom/client'
import { ConsoleApp } from './console/ConsoleApp'
import { Home } from './home/Home'
import { usePath } from './router'
import { Toasts, TooltipProvider } from './ui'

function App() {
  const path = usePath()
  return (
    <TooltipProvider>
      {path === '/' ? <Home /> : <ConsoleApp path={path} />}
      <Toasts />
    </TooltipProvider>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
