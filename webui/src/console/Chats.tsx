import { ArrowDownToLine, Eraser, Loader2, MessagesSquare, Search, Send } from 'lucide-react'
import { type KeyboardEvent, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { type Account, type Chat, type Message, type Topic, api, enc } from '../api'
import { Link, navigate } from '../router'
import { Avatar, Button, Empty, Switch, Tag, Tip, attempt, cn, fmtDay, fmtTime, toast, typeLabel, usePoll } from '../ui'

const CHAT_TYPE: Record<number, string> = { 1: '私聊', 2: '群聊', 3: '话题群' }
const WIDE = '(min-width: 821px)'

export function Chats({ account: a, chatId }: { account: Account; chatId: string }) {
  const [chats, setChats] = useState<Chat[] | null>(null)
  const [query, setQuery] = useState('')
  const load = () => api<Chat[]>('GET', `/accounts/${enc(a.id)}/chats`).then(setChats).catch(() => {})
  useEffect(() => void load(), [a.id])
  usePoll(() => void load(), 6000)

  // 宽屏下进来默认打开最新的会话
  useEffect(() => {
    if (!chatId && chats?.length && matchMedia(WIDE).matches) navigate(`/a/${enc(a.id)}/chats/${enc(chats[0]!.chat_id)}`, { replace: true })
  }, [chatId, chats, a.id])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? chats?.filter((c) => (c.name || c.chat_id).toLowerCase().includes(q)) : chats
  }, [chats, query])
  const current = chats?.find((c) => c.chat_id === chatId)

  return (
    <div className="grid h-full grid-cols-[minmax(0,1fr)] grid-rows-[minmax(120px,36%)_minmax(0,1fr)] min-[821px]:grid-cols-[300px_minmax(0,1fr)] min-[821px]:grid-rows-1">
      <aside className="flex min-h-0 flex-col border-b border-line-1 bg-surface-1/40 min-[821px]:border-r min-[821px]:border-b-0">
        <div className="relative shrink-0 p-3">
          <Search className="pointer-events-none absolute top-1/2 left-6 size-3.5 -translate-y-1/2 text-fg-4" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索会话"
            autoComplete="off"
            className="h-8 w-full rounded-full bg-fill-2 pr-3 pl-8 text-small outline-none ring-1 ring-transparent ring-inset placeholder:text-fg-4 focus:ring-accent-ring"
          />
        </div>
        <ul className="page-scroll min-h-0 flex-1 px-2 pb-2">
          {shown?.map((c) => {
            const name = c.name || c.chat_id
            const who = c.last_direction === 'out' ? '我： ' : c.chat_type !== 1 && c.last_sender ? `${c.last_sender}: ` : ''
            return (
              <li key={c.chat_id}>
                <Link
                  to={`/a/${enc(a.id)}/chats/${enc(c.chat_id)}`}
                  className={cn('flex gap-2.5 rounded-sm px-2.5 py-2 text-fg-1 no-underline hover:bg-fill-2', c.chat_id === chatId && 'bg-fill-3 hover:bg-fill-3')}
                >
                  <Avatar src={c.avatar} name={name} size="lg" />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline gap-2">
                      <span className="min-w-0 flex-1 truncate text-small font-medium">{name}</span>
                      <span className="tabular shrink-0 text-micro text-fg-3">{fmtTime(c.last_time)}</span>
                    </span>
                    <span className="block truncate text-caption text-fg-3">{who}{c.last_content || '[消息]'}</span>
                  </span>
                </Link>
              </li>
            )
          })}
          {chats && !shown?.length && (
            <li><Empty title={chats.length ? '没有匹配的会话' : '还没有会话'}>{chats.length ? '换个关键词试试。' : '启动账号收到消息后，会话会出现在这里。'}</Empty></li>
          )}
        </ul>
      </aside>
      {chatId ? (
        <Thread key={chatId} account={a} chatId={chatId} chat={current} onChanged={load} />
      ) : (
        <div className="grid place-items-center"><Empty icon={<MessagesSquare />} title="选择一个会话">在左边选一个会话查看聊天记录。</Empty></div>
      )}
    </div>
  )
}

const sameBlock = (a: Message | undefined, b: Message) =>
  !!a && a.direction === b.direction && a.sender_id === b.sender_id && b.time - a.time < 300 && fmtDay(a.time) === fmtDay(b.time)

const isMedia = (m: Message) => !m.content || (m.type !== 'TEXT' && m.type !== 'POST' && /^\[/.test(m.content))

function byTime(x: Message, y: Message) {
  return x.time - y.time || x.id - y.id
}

function Thread({ account: a, chatId, chat, onChanged }: { account: Account; chatId: string; chat?: Chat; onChanged: () => void }) {
  const [msgs, setMsgs] = useState<Message[] | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [topics, setTopics] = useState<Topic[]>([])
  const [anchor, setAnchor] = useState<string | null>(null)   // null = 全部，'' = 主会话，其它 = 某个话题
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [pulling, setPulling] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  const keepFrom = useRef<number | null>(null)
  const base = `/accounts/${enc(a.id)}/chats/${enc(chatId)}`
  const name = chat?.name || chatId

  const url = (extra: Record<string, string>) => {
    const p = new URLSearchParams(extra)
    if (anchor !== null) p.set('anchor', anchor)
    return `${base}/messages?${p}`
  }
  const load = async () => {
    const r = await api<{ messages: Message[]; has_more: boolean }>('GET', url({ limit: '50' }))
    setHasMore(r.has_more)
    setMsgs(r.messages)
  }
  // 只把新消息合并进来,不动已经翻出来的老消息
  const poll = async () => {
    const r = await api<{ messages: Message[] }>('GET', url({ limit: '50' }))
    setMsgs((cur) => {
      if (!cur) return r.messages
      const ids = new Set(cur.map((m) => m.id))
      const fresh = r.messages.filter((m) => !ids.has(m.id))
      return fresh.length ? [...cur, ...fresh].sort(byTime) : cur
    })
  }
  useEffect(() => {
    setMsgs(null)
    stick.current = true
    void attempt(load)
  }, [anchor, chatId])
  useEffect(() => {
    api<Topic[]>('GET', `${base}/topics`).then(setTopics).catch(() => {})
  }, [base])
  usePoll(() => void poll().catch(() => {}), 3000)

  // 贴底时跟随新消息;往前翻页时保持当前阅读位置
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    if (keepFrom.current !== null) {
      el.scrollTop = el.scrollHeight - keepFrom.current
      keepFrom.current = null
    } else if (stick.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [msgs])

  const older = () => attempt(async () => {
    const first = msgs?.[0]
    if (!first) return
    const r = await api<{ messages: Message[]; has_more: boolean }>('GET', url({ limit: '50', before: `${first.time}_${first.id}` }))
    keepFrom.current = box.current ? box.current.scrollHeight : null
    setHasMore(r.has_more)
    setMsgs((cur) => [...r.messages, ...(cur ?? [])])
  })

  const send = () => attempt(async () => {
    const text = draft.trim()
    if (!text || sending) return
    setSending(true)
    try {
      await api('POST', `${base}/messages`, { text, root_id: anchor || undefined })
      setDraft('')
      stick.current = true
      await poll()
      onChanged()
    } finally {
      setSending(false)
    }
  })
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void send()
    }
  }

  const pull = () => attempt(async () => {
    setPulling(true)
    try {
      const r = await api<{ pulled: number; at_start: boolean }>('POST', `${base}/history`, { count: 50 })
      toast(r.pulled ? `拉取了 ${r.pulled} 条历史消息` : r.at_start ? '已经是最早的消息了' : '没有新的历史消息')
      await load()
      onChanged()
    } finally {
      setPulling(false)
    }
  })
  const reset = () => attempt(async () => {
    const r = await api<{ cleared: number }>('POST', `${base}/reset`, { anchor: anchor ?? '' })
    toast(r.cleared ? `已开启新会话，清空了 ${r.cleared} 条排队消息` : '已开启新会话')
  })
  const toggleAgent = (enabled: boolean) => attempt(async () => {
    await api('PUT', `${base}/agent`, { enabled })
    onChanged()
  })

  const chips: { v: string | null; label: string }[] = topics.length
    ? [{ v: null, label: '全部' }, { v: '', label: '主会话' }, ...topics.map((t) => ({ v: t.anchor, label: `${t.title || t.anchor.slice(0, 6)} · ${t.count}` }))]
    : []
  const topicName = anchor ? topics.find((t) => t.anchor === anchor)?.title : ''

  return (
    <section className="flex min-h-0 min-w-0 flex-col">
      <div className="flex min-h-14 shrink-0 flex-wrap items-center gap-x-2.5 gap-y-1 border-b border-line-1 px-4 py-2">
        <Avatar src={chat?.avatar} name={name} size="md" />
        <h2 className="min-w-0 truncate text-body font-medium">{name}</h2>
        <Tag>{CHAT_TYPE[chat?.chat_type ?? 0] ?? '会话'}</Tag>
        <div className="ml-auto flex items-center gap-1">
          <label className="mr-2 flex cursor-pointer items-center gap-2 text-small text-fg-2">
            Agent
            <Switch checked={chat?.agent_enabled ?? true} onChange={toggleAgent} label="这个会话启用 agent" />
          </label>
          <Tip label="开启新的 Agent 上下文（等同于发送 /clear）">
            <Button size="icon" variant="ghost" aria-label="开启新会话" onClick={reset}><Eraser /></Button>
          </Tip>
          <Tip label="从飞书拉取更早的 50 条历史">
            <Button size="icon" variant="ghost" aria-label="拉取历史" disabled={pulling} onClick={pull}>{pulling ? <Loader2 className="spin" /> : <ArrowDownToLine />}</Button>
          </Tip>
        </div>
      </div>
      {chips.length > 0 && (
        <div className="scrollbar-none flex shrink-0 gap-1.5 overflow-x-auto border-b border-line-1 px-4 py-2">
          {chips.map((c) => (
            <button
              key={c.v ?? '__all'}
              type="button"
              onClick={() => setAnchor(c.v)}
              className={cn('press h-6 max-w-56 shrink-0 truncate rounded-full px-2.5 text-caption', c.v === anchor ? 'bg-invert text-invert-fg' : 'bg-fill-2 text-fg-2 hover:text-fg-1')}
            >
              {c.label}
            </button>
          ))}
        </div>
      )}
      <div
        ref={box}
        className="page-scroll min-h-0 flex-1 px-4 py-4"
        onScroll={(e) => {
          const el = e.currentTarget
          stick.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 40
        }}
      >
        <div className="mx-auto w-full max-w-[760px]">
          {hasMore && <div className="mb-3 flex justify-center"><Button size="sm" onClick={older}>加载更早的消息</Button></div>}
          {msgs && !msgs.length && <Empty title="这里还没有消息" />}
          {msgs?.map((m, i) => {
            const prev = msgs[i - 1]
            const out = m.direction === 'out'
            const grouped = sameBlock(prev, m)
            const newDay = !prev || fmtDay(prev.time) !== fmtDay(m.time)
            return (
              <div key={m.id}>
                {newDay && m.time > 0 && (
                  <div className="my-4 text-center"><span className="rounded-full bg-fill-2 px-2.5 py-0.5 text-caption text-fg-3">{fmtDay(m.time)}</span></div>
                )}
                <div className={cn('flex gap-2.5', grouped ? 'mt-1' : 'mt-4', out && 'flex-row-reverse')}>
                  {out ? null : grouped ? <span className="w-7 shrink-0" /> : (
                    <Avatar src={m.sender_id ? `/api/accounts/${enc(a.id)}/avatars/user/${m.sender_id}` : ''} name={m.sender} size="sm" />
                  )}
                  <div className={cn('flex max-w-[78%] min-w-0 flex-col', out && 'items-end')}>
                    {!grouped && !out && <span className="mb-1 text-caption text-fg-3">{m.sender}</span>}
                    <Tip label={fmtTime(m.time)}>
                      <div className={cn('rounded-md px-3 py-2 text-body break-words whitespace-pre-wrap', out ? 'bg-accent-soft' : 'bg-fill-2', isMedia(m) && 'text-fg-3 italic')}>
                        {m.content || typeLabel(m.type)}
                      </div>
                    </Tip>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
      <div className="shrink-0 border-t border-line-1 p-3">
        <div className="mx-auto flex w-full max-w-[760px] items-end gap-2 rounded-md bg-fill-2 p-1.5 ring-1 ring-transparent ring-inset focus-within:bg-transparent focus-within:ring-accent-ring">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKey}
            rows={1}
            disabled={!a.has_credentials}
            placeholder={!a.has_credentials ? '登录后才能发消息' : topicName ? `回复话题「${topicName}」，Enter 发送` : `发送给 ${name}，Enter 发送`}
            className="max-h-32 min-h-8 flex-1 resize-none bg-transparent px-2 py-1 text-body outline-none [field-sizing:content] placeholder:text-fg-4"
          />
          <Button size="icon" variant="primary" aria-label="发送" disabled={!draft.trim() || sending || !a.has_credentials} onClick={send}>
            {sending ? <Loader2 className="spin" /> : <Send />}
          </Button>
        </div>
      </div>
    </section>
  )
}
