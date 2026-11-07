import { Check, RefreshCw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { type LoginSnapshot, api, enc } from '../api'
import { useConsole } from '../store'
import { Button, Seg, Textarea, attempt, cn } from '../ui'

/**
 * 扫码登录。不传 accountId = 添加账号： 账号在服务端先待定，登录成功才转正，中途退出什么都不留下。
 * 姓名、头像、公司登录后从飞书取，这里什么都不用填，只选飞书还是 Lark。
 */
export function LoginPanel({ accountId, region: initialRegion, onDone }: { accountId?: string; region?: string; onDone: (id: string) => void }) {
  const { meta } = useConsole()
  const [region, setRegion] = useState(initialRegion || 'feishu')
  const [mode, setMode] = useState<'qr' | 'cookie'>('qr')
  const [snap, setSnap] = useState<LoginSnapshot | null>(null)
  const [nonce, setNonce] = useState(0)
  const [cookie, setCookie] = useState('')
  const idRef = useRef(accountId || '')
  const doneRef = useRef(false)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  useEffect(() => {
    if (mode !== 'qr') return
    let dead = false
    let timer = 0
    setSnap(null)
    const finish = (id: string) => {
      doneRef.current = true
      onDoneRef.current(id)
    }
    const tick = async () => {
      try {
        const s = await api<LoginSnapshot>('GET', `/accounts/${enc(idRef.current)}/login/status`)
        if (dead) return
        setSnap(s)
        if (s.state === 'success') finish(s.account_id)
        else if (s.state !== 'failed') timer = window.setTimeout(tick, 1500)
      } catch {
        if (!dead) timer = window.setTimeout(tick, 3000)
      }
    }
    void attempt(async () => {
      const first = idRef.current
        ? await api<LoginSnapshot>('POST', `/accounts/${enc(idRef.current)}/login/qr`, { region })
        : await api<LoginSnapshot>('POST', '/accounts/add', { region })
      if (dead && !idRef.current) {
        void api('DELETE', `/accounts/${enc(first.account_id)}/login`)
        return
      }
      idRef.current = first.account_id
      if (dead) return
      setSnap(first)
      timer = window.setTimeout(tick, 1000)
    })
    return () => {
      dead = true
      clearTimeout(timer)
    }
  }, [mode, region, nonce])

  // 关掉弹窗/离开页面: 取消扫码(待定账号会一起清掉)
  useEffect(() => () => {
    if (!doneRef.current && idRef.current) void api('DELETE', `/accounts/${enc(idRef.current)}/login`).catch(() => {})
  }, [])

  const importCookie = () => attempt(async () => {
    await api('POST', `/accounts/${enc(idRef.current)}/login/cookie`, { cookie, region })
    doneRef.current = true
    onDone(idRef.current)
  })

  const regions = meta?.regions ?? [{ id: 'feishu', label: '飞书' }, { id: 'lark', label: 'Lark' }]
  const label = regions.find((r) => r.id === region)?.label ?? ''
  return (
    <div className="mx-auto flex w-full max-w-[340px] flex-col items-center">
      <Seg value={region} onChange={setRegion} options={regions.map((r) => ({ value: r.id, label: r.label }))} />
      {mode === 'qr' ? (
        <>
          <div className="relative mt-4 grid size-[232px] place-items-center overflow-hidden rounded-lg bg-white shadow-raised">
            {snap?.qr ? (
              <img src={snap.qr} alt="登录二维码" className={cn('size-full p-2 [image-rendering:pixelated]', snap.state === 'scanned' && 'opacity-10')} />
            ) : (
              <div className="size-full animate-pulse bg-fill-1" />
            )}
            {snap?.state === 'scanned' && (
              <div className="absolute inset-0 grid place-items-center">
                <span className="grid size-11 place-items-center rounded-full bg-success text-white"><Check className="size-6" /></span>
              </div>
            )}
          </div>
          <p className="mt-3 min-h-6 text-small text-fg-2">{snap?.state === 'failed' ? snap.message : snap?.state === 'scanned' ? snap.message : `请使用 ${label} App 的「扫一扫」`}</p>
          {snap?.state === 'failed' && (
            <Button className="mt-2" onClick={() => setNonce((n) => n + 1)}><RefreshCw />重新获取</Button>
          )}
          <button type="button" className="mt-2 text-caption text-fg-3 hover:text-fg-1" onClick={() => setMode('cookie')}>
            使用 Cookie 登录
          </button>
        </>
      ) : (
        <div className="mt-4 flex w-full flex-col gap-3">
          <Textarea value={cookie} onChange={(e) => setCookie(e.target.value)} placeholder={`从 ${label} 网页版的开发者工具复制完整的 Cookie 请求头`} className="min-h-32 font-mono text-caption" autoFocus />
          <p className="text-caption text-fg-3">Cookie 等同于登录凭证，只保存在本机。</p>
          <div className="flex items-center justify-between">
            <button type="button" className="text-caption text-fg-3 hover:text-fg-1" onClick={() => setMode('qr')}>返回扫码</button>
            <Button variant="primary" disabled={cookie.trim().length < 10} onClick={importCookie}>导入</Button>
          </div>
        </div>
      )}
    </div>
  )
}
