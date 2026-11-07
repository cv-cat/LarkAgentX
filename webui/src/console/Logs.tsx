import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { type Account, type LogLine, api, enc } from '../api'
import { Card, Empty, cn, usePoll } from '../ui'

const MAX = 500

export function Logs({ account: a }: { account: Account }) {
  const [rows, setRows] = useState<LogLine[]>([])
  const box = useRef<HTMLDivElement>(null)
  const since = useRef(0)
  const stick = useRef(true)

  const pull = async () => {
    const fresh = await api<LogLine[]>('GET', `/accounts/${enc(a.id)}/logs?since=${since.current}`)
    if (!fresh.length) return
    since.current = fresh[fresh.length - 1]!.seq
    setRows((cur) => [...cur, ...fresh].slice(-MAX))
  }
  useEffect(() => {
    since.current = 0
    setRows([])
    void pull().catch(() => {})
  }, [a.id])
  usePoll(() => void pull().catch(() => {}), 1500)
  useLayoutEffect(() => {
    if (stick.current && box.current) box.current.scrollTop = box.current.scrollHeight
  }, [rows])

  return (
    <div className="fade-in mx-auto flex h-full w-full max-w-[960px] flex-col px-6 py-8">
      <div className="mb-4 shrink-0">
        <h1 className="text-title font-medium">日志</h1>
        <p className="text-small text-fg-3">这个账号收发消息和调用 agent 的实时记录，只保留在内存里。</p>
      </div>
      <Card className="min-h-0 flex-1 overflow-hidden">
        {rows.length ? (
          <div
            ref={box}
            className="page-scroll h-full p-4 font-mono text-caption"
            onScroll={(e) => {
              const el = e.currentTarget
              stick.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 24
            }}
          >
            {rows.map((r) => (
              <div key={r.seq} className={cn('break-all whitespace-pre-wrap', r.level === 'WARNING' && 'text-warning', (r.level === 'ERROR' || r.level === 'CRITICAL') && 'text-danger')}>
                <span className="tabular mr-3 text-fg-4">{r.time}</span>
                {r.text}
              </div>
            ))}
          </div>
        ) : (
          <div className="grid h-full place-items-center"><Empty title="暂无日志">启动账号后，这里会实时显示收发消息和 agent 调用。</Empty></div>
        )}
      </Card>
    </div>
  )
}
