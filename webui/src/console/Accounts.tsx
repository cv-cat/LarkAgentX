import { Play, Plus, Square, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { type Account, api, enc } from '../api'
import { navigate } from '../router'
import { useConsole } from '../store'
import { AccountAvatar, Button, Card, Confirm, Dialog, StateBadge, Tip, attempt, cn, isActive, toast } from '../ui'
import { LoginPanel } from './Login'

export function deleteHint(a: Account) {
  return a.id === 'default' ? '会停止运行并删除登录凭证和设置，消息库保留。' : '会停止运行并删除它的登录凭证、消息库和设置，无法恢复。'
}

export function Accounts({ onAdd }: { onAdd: () => void }) {
  const { accounts, refresh } = useConsole()
  const [removing, setRemoving] = useState<Account | null>(null)
  const [loginFor, setLoginFor] = useState<Account | null>(null)

  const act = (a: Account, what: 'start' | 'stop') => attempt(async () => {
    await api('POST', `/accounts/${enc(a.id)}/${what}`)
    await refresh()
  })

  return (
    <div className="page-scroll h-full">
      <div className="fade-in mx-auto w-full max-w-[960px] px-6 py-8">
        <div className="mb-6 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-title font-medium">全部账号</h1>
            <p className="text-small text-fg-3">每个账号独立登录、独立存储、独立设置，可以同时运行。</p>
          </div>
          <Button variant="primary" onClick={onAdd}><Plus />添加账号</Button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {accounts.map((a) => (
            <Card key={a.id} className="group flex flex-col">
              <button type="button" className="flex items-center gap-3 p-4 text-left" onClick={() => navigate(`/a/${enc(a.id)}/overview`)}>
                <AccountAvatar account={a} size="lg" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-body font-medium">{a.name}</span>
                  <span className="block truncate text-caption text-fg-3">{[a.company, a.region_label].filter(Boolean).join(' · ')}</span>
                </span>
              </button>
              <div className="mt-auto flex items-center gap-1.5 border-t border-line-1 px-4 py-2.5">
                <StateBadge state={a.state} />
                <span className="ml-auto" />
                {isActive(a.state) ? (
                  <Button size="sm" onClick={() => act(a, 'stop')}><Square />停止</Button>
                ) : a.has_credentials && a.state !== 'login_required' ? (
                  <Button size="sm" onClick={() => act(a, 'start')}><Play />启动</Button>
                ) : (
                  <Button size="sm" onClick={() => setLoginFor(a)}>{a.has_credentials ? '重新登录' : '登录'}</Button>
                )}
                <Tip label="删除账号">
                  <Button size="icon-sm" variant="ghost" aria-label="删除账号" className={cn('hover:text-danger')} onClick={() => setRemoving(a)}><Trash2 /></Button>
                </Tip>
              </div>
            </Card>
          ))}
        </div>
      </div>
      <Confirm
        open={!!removing}
        onClose={() => setRemoving(null)}
        title={`删除「${removing?.name ?? ''}」?`}
        body={removing ? deleteHint(removing) : ''}
        ok="删除"
        onOk={() => {
          const a = removing!
          setRemoving(null)
          void attempt(async () => {
            await api('DELETE', `/accounts/${enc(a.id)}`)
            await refresh()
            toast('已删除')
          })
        }}
      />
      <Dialog open={!!loginFor} onClose={() => setLoginFor(null)} title={`登录「${loginFor?.name ?? ''}」`}>
        {loginFor && (
          <LoginPanel
            accountId={loginFor.id}
            region={loginFor.region}
            onDone={async () => {
              setLoginFor(null)
              await refresh()
              toast('登录成功')
            }}
          />
        )}
      </Dialog>
    </div>
  )
}
