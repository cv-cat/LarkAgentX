import { Check, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { type KeyboardEvent, useEffect, useState } from 'react'
import { type Account, type MemoryData, api, enc } from '../api'
import { Link } from '../router'
import { Button, Card, Empty, Input, Textarea, attempt, cn, isActive, toast, usePoll } from '../ui'

/** 长期记忆: 每个账号一份,条目用编号增删改,和 lark memory 命令是同一份数据 */
export function MemoryPage({ account: a }: { account: Account }) {
  const [data, setData] = useState<MemoryData | null>(null)
  const [draft, setDraft] = useState('')
  const [editing, setEditing] = useState(0)        // 正在改第几条(从 1 开始),0 = 没在改
  const [editText, setEditText] = useState('')
  const [reviewing, setReviewing] = useState(false)
  const base = `/accounts/${enc(a.id)}/memory`
  const load = () => api<MemoryData>('GET', base).then(setData).catch(() => undefined)
  useEffect(() => void load(), [a.id])
  usePoll(() => {
    if (!editing) void load()
  }, 5000)

  const add = () => attempt(async () => {
    const text = draft.trim()
    if (!text) return
    setData(await api<MemoryData>('POST', base, { text }))
    setDraft('')
  })
  const save = (n: number) => attempt(async () => {
    setData(await api<MemoryData>('PUT', `${base}/${n}`, { text: editText.trim() }))
    setEditing(0)
  })
  const remove = (n: number) => attempt(async () => {
    setData(await api<MemoryData>('DELETE', `${base}/${n}`))
    if (editing === n) setEditing(0)
  })
  const review = () => attempt(async () => {
    setReviewing(true)
    try {
      await api('POST', `${base}/review`)
      toast('已开始回顾，整理完后这里会更新')
    } finally {
      setReviewing(false)
    }
  })
  const onAddKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void add()
    }
  }

  const pct = data ? Math.min(100, Math.round((data.used / data.limit) * 100)) : 0
  return (
    <div className="page-scroll h-full">
      <div className="fade-in mx-auto flex w-full max-w-[760px] flex-col gap-4 px-6 py-8">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
          <div className="min-w-0 flex-1">
            <h1 className="text-title font-medium">长期记忆</h1>
            <p className="text-small text-fg-3">所有会话共用。Agent 会用 lark memory 增删改，你也可以在这里修改。</p>
          </div>
          <Button onClick={review} disabled={reviewing || !isActive(a.state) || !a.memory}>
            <RefreshCw className={cn(reviewing && 'spin')} />立即回顾
          </Button>
        </div>

        {!a.memory && (
          <div className="rounded-md bg-warning-soft px-4 py-3 text-small text-warning">
            长期记忆没有开启，Agent 不会读取这些内容。<Link to={`/a/${enc(a.id)}/settings`} className="font-medium text-warning">到设置里开启</Link>
          </div>
        )}

        {data && (
          <div>
            <div className="mb-1.5 flex items-baseline justify-between text-caption text-fg-3">
              <span>已用 <b className="tabular font-medium text-fg-1">{data.used}</b> / {data.limit} 字，写满后要先删除或合并旧条目</span>
              {data.last_review && <span>上次回顾 {data.last_review}</span>}
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-fill-2">
              <div className={cn('h-full rounded-full', pct >= 90 ? 'bg-warning' : 'bg-accent')} style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}

        <Card>
          {data && !data.entries.length ? (
            <Empty title="还没有记忆">Agent 遇到值得长期记住的事会自己记下，你也可以在下面添加。</Empty>
          ) : (
            <ol className="divide-y divide-line-1">
              {data?.entries.map((text, i) => {
                const n = i + 1
                return (
                  <li key={`${n}-${text}`} className="flex items-start gap-3 px-5 py-3">
                    <span className="tabular w-6 shrink-0 pt-0.5 text-right text-caption text-fg-3">{n}</span>
                    {editing === n ? (
                      <div className="flex min-w-0 flex-1 flex-col gap-2">
                        <Textarea value={editText} onChange={(e) => setEditText(e.target.value)} maxLength={2000} autoFocus />
                        <div className="flex justify-end gap-2">
                          <Button size="sm" variant="ghost" onClick={() => setEditing(0)}>取消</Button>
                          <Button size="sm" variant="primary" disabled={!editText.trim()} onClick={() => save(n)}><Check />保存</Button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <p className="min-w-0 flex-1 text-body break-words whitespace-pre-wrap">{text}</p>
                        <Button size="icon-sm" variant="ghost" aria-label={`修改第 ${n} 条`} onClick={() => { setEditing(n); setEditText(text) }}><Pencil /></Button>
                        <Button size="icon-sm" variant="ghost" aria-label={`删除第 ${n} 条`} onClick={() => remove(n)}><Trash2 /></Button>
                      </>
                    )}
                  </li>
                )
              })}
            </ol>
          )}
          <div className="flex items-center gap-2 border-t border-line-1 p-3">
            <Input value={draft} maxLength={2000} onChange={(e) => setDraft(e.target.value)} onKeyDown={onAddKey} placeholder="添加一条，例如：陈思远：后端负责人，喜欢先看结论" />
            <Button onClick={add} disabled={!draft.trim()}><Plus />添加</Button>
          </div>
        </Card>
      </div>
    </div>
  )
}
