import { Moon, Sun } from 'lucide-react'
import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from 'react'
import { type Account, type Meta, TokenRequired, api, login, onUnauthorized } from './api'
import { Button, Dialog, Input, attempt, btn, cn, usePoll } from './ui'

// ---------- 主题 ----------
function currentTheme(): 'light' | 'dark' {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useState(currentTheme)
  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    localStorage.setItem('larkx_theme', next)
    document.documentElement.className = next
    setTheme(next)
  }
  return (
    <button type="button" aria-label={theme === 'dark' ? '切换到浅色' : '切换到深色'} onClick={toggle} className={cn(btn('ghost', 'icon'), className)}>
      {theme === 'dark' ? <Sun /> : <Moon />}
    </button>
  )
}

// ---------- 控制台数据: 账号列表每 4 秒同步一次,所有页面读同一份 ----------
interface ConsoleData {
  accounts: Account[]
  meta: Meta | null
  loaded: boolean
  error: string
  refresh: () => Promise<void>
}

const Ctx = createContext<ConsoleData>({ accounts: [], meta: null, loaded: false, error: '', refresh: async () => {} })
export const useConsole = () => useContext(Ctx)

export function ConsoleProvider({ children }: { children: ReactNode }) {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [meta, setMeta] = useState<Meta | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [asking, setAsking] = useState(false)
  const [tokenDraft, setTokenDraft] = useState('')

  const refresh = useCallback(async () => {
    try {
      setAccounts(await api<Account[]>('GET', '/accounts'))
      setError('')
      setLoaded(true)
    } catch (e) {
      if (!(e instanceof TokenRequired)) setError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    onUnauthorized(() => setAsking(true))
    api<Meta>('GET', '/meta').then(setMeta).catch(() => {})
    void refresh()
  }, [refresh])
  usePoll(() => void refresh(), 4000)

  return (
    <Ctx.Provider value={{ accounts, meta, loaded, error, refresh }}>
      {children}
      <Dialog open={asking} onClose={() => setAsking(false)} title="需要访问令牌">
        <p className="mb-3 text-small text-fg-2">这个控制台设置了访问令牌，请输入启动时的 --token。</p>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void attempt(async () => {
              await login(tokenDraft.trim())
              location.reload()
            })
          }}
        >
          <Input type="password" value={tokenDraft} onChange={(e) => setTokenDraft(e.target.value)} placeholder="访问令牌" autoFocus />
          <div className="mt-4 flex justify-end">
            <Button type="submit" variant="primary">确定</Button>
          </div>
        </form>
      </Dialog>
    </Ctx.Provider>
  )
}
