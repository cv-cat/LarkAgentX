import { ChevronDown, Plus, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Mark } from '../Logo'
import { NavPills } from '../NavPills'
import { Link, navigate } from '../router'
import { ConsoleProvider, ThemeToggle, useConsole } from '../store'
import { AccountAvatar, Dialog, Empty, GithubIcon, MenuContent, MenuItem, MenuRoot, MenuSeparator, MenuTrigger, REPO_URL, StateDot, btn, cn, stateLabel } from '../ui'
import { Accounts } from './Accounts'
import { Chats } from './Chats'
import { LoginPanel } from './Login'
import { Logs } from './Logs'
import { Overview } from './Overview'
import { SettingsPage } from './Settings'

const TABS = [
  { id: 'overview', label: '概览' },
  { id: 'chats', label: '聊天记录' },
  { id: 'settings', label: '设置' },
  { id: 'logs', label: '日志' },
] as const
type TabId = (typeof TABS)[number]['id']

function parse(path: string) {
  const m = path.match(/^\/a\/([^/]+)(?:\/(\w+))?(?:\/([^/]+))?/)
  if (!m) return { view: path === '/accounts' ? 'accounts' : 'entry', id: '', tab: 'overview' as TabId, chat: '' }
  const tab = TABS.some((t) => t.id === m[2]) ? (m[2] as TabId) : 'overview'
  return { view: 'account', id: decodeURIComponent(m[1]!), tab, chat: m[3] ? decodeURIComponent(m[3]) : '' }
}

export function ConsoleApp({ path }: { path: string }) {
  return (
    <ConsoleProvider>
      <Shell path={path} />
    </ConsoleProvider>
  )
}

function AccountMenu({ currentId, tab, onAdd }: { currentId: string; tab: TabId; onAdd: () => void }) {
  const { accounts } = useConsole()
  const current = accounts.find((a) => a.id === currentId)
  return (
    <MenuRoot>
      <MenuTrigger asChild>
        <button type="button" className="press flex h-9 min-w-0 items-center gap-2 rounded-full pr-2 pl-1 outline-none hover:bg-fill-2 data-[state=open]:bg-fill-2">
          {current ? (
            <>
              <AccountAvatar account={current} size="sm" />
              <span className="max-w-40 truncate text-small font-medium">{current.name}</span>
              <StateDot state={current.state} />
            </>
          ) : (
            <span className="flex items-center gap-2 px-2 text-small font-medium"><Users className="size-4" />全部账号</span>
          )}
          <ChevronDown className="size-3.5 text-fg-3" />
        </button>
      </MenuTrigger>
      <MenuContent>
        {accounts.map((a) => (
          <MenuItem key={a.id} onSelect={() => navigate(`/a/${encodeURIComponent(a.id)}/${tab}`)}>
            <AccountAvatar account={a} size="sm" />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{a.name}</span>
              <span className="block truncate text-caption text-fg-3">{[a.company, a.region_label, stateLabel(a.state)].filter(Boolean).join(' · ')}</span>
            </span>
            <StateDot state={a.state} />
          </MenuItem>
        ))}
        {accounts.length > 0 && <MenuSeparator />}
        <MenuItem onSelect={onAdd}>
          <span className="grid size-7 place-items-center"><Plus className="size-4" /></span>
          添加账号
        </MenuItem>
        <MenuItem onSelect={() => navigate('/accounts')}>
          <span className="grid size-7 place-items-center"><Users className="size-4" /></span>
          全部账号
        </MenuItem>
      </MenuContent>
    </MenuRoot>
  )
}

function Shell({ path }: { path: string }) {
  const { accounts, loaded, error, refresh } = useConsole()
  const route = parse(path)
  const [adding, setAdding] = useState(false)
  const account = accounts.find((a) => a.id === route.id)

  // /console 是入口: 一个账号直接进它,多个进列表;链接里的账号不存在就回列表
  useEffect(() => {
    if (!loaded) return
    if (route.view === 'entry') {
      if (accounts.length === 1) navigate(`/a/${encodeURIComponent(accounts[0]!.id)}/overview`, { replace: true })
      else if (accounts.length > 1) navigate('/accounts', { replace: true })
    } else if (route.view === 'account' && !account) {
      navigate('/accounts', { replace: true })
    }
  }, [loaded, route.view, accounts, account])

  const base = account ? `/a/${encodeURIComponent(account.id)}` : ''
  const nav = account && (
    <NavPills items={TABS.map((t) => ({ label: t.label, to: `${base}/${t.id}`, active: route.tab === t.id }))} />
  )

  const finishAdd = async (id: string) => {
    setAdding(false)
    await refresh()
    navigate(`/a/${encodeURIComponent(id)}/overview`)
  }

  let page = null
  if (error && !loaded) {
    page = <div className="grid h-full place-items-center"><Empty title="连不上控制台">{error}</Empty></div>
  } else if (loaded && !accounts.length) {
    page = (
      <div className="page-scroll grid h-full place-items-center p-6">
        <div className="fade-in flex flex-col items-center text-center">
          <h1 className="font-serif text-headline font-normal">
            扫码登录，<span className="text-fg-3">开始使用。</span>
          </h1>
          <p className="mt-2 mb-6 text-small text-fg-3">姓名、头像和公司信息会在登录后自动获取。</p>
          <LoginPanel onDone={finishAdd} />
        </div>
      </div>
    )
  } else if (route.view === 'accounts') {
    page = <Accounts onAdd={() => setAdding(true)} />
  } else if (account) {
    if (route.tab === 'chats') page = <Chats key={account.id} account={account} chatId={route.chat} />
    else if (route.tab === 'settings') page = <SettingsPage key={account.id} account={account} />
    else if (route.tab === 'logs') page = <Logs key={account.id} account={account} />
    else page = <Overview key={account.id} account={account} />
  }

  return (
    <div className="relative flex h-dvh flex-col overflow-hidden bg-surface-1">
      <header className="relative flex h-14 shrink-0 items-center gap-2 px-4">
        <Link to="/" aria-label="回到主页" className="flex shrink-0 items-center gap-2 no-underline">
          <Mark size={26} />
          <span className="hidden text-body font-medium tracking-tight sm:inline">LarkAgentX</span>
        </Link>
        {loaded && accounts.length > 0 && (
          <>
            <span aria-hidden="true" className="mx-1 hidden h-4 w-px bg-line-2 sm:block" />
            <AccountMenu currentId={route.id} tab={route.tab} onAdd={() => setAdding(true)} />
          </>
        )}
        <div className="absolute left-1/2 hidden -translate-x-1/2 min-[960px]:block">{nav}</div>
        <div className="ml-auto flex shrink-0 items-center gap-1">
          <a href={REPO_URL} target="_blank" rel="noreferrer" aria-label="GitHub" className={btn('ghost', 'icon')}>
            <GithubIcon />
          </a>
          <ThemeToggle />
        </div>
      </header>
      {account && <div className={cn('scrollbar-none shrink-0 overflow-x-auto px-3 pb-2 min-[960px]:hidden')}>{nav}</div>}
      <main className="relative mx-2 mb-2 min-h-0 flex-1 overflow-hidden rounded-lg bg-bg shadow-raised">{page}</main>
      <Dialog open={adding} onClose={() => setAdding(false)} title="添加账号">
        {adding && <LoginPanel onDone={finishAdd} />}
      </Dialog>
    </div>
  )
}
