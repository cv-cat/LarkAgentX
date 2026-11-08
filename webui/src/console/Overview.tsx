import { AlertCircle, ArrowRight, Play, RotateCw, Square, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { type Account, type Overview as OverviewData, type Task, api, enc } from '../api'
import { Link, navigate } from '../router'
import { useConsole } from '../store'
import { AccountAvatar, Avatar, Button, Card, Dialog, Empty, StateBadge, Tag, attempt, cn, fmtTime, isActive, toast, typeLabel, usePoll } from '../ui'
import { LoginPanel } from './Login'

const BACKEND_LABEL: Record<string, string> = { claude: 'Claude Code', codex: 'Codex', none: '未接入 Agent' }

/**
 * 近 7 天收发： 分组柱形。规范来自 dataviz: 柱宽封顶 24px、顶部 4px 圆角、相邻柱留 2px 缝、
 * 发丝网格、两个系列必有图例、每天一个悬停提示，另有一张给读屏器的表。两色已跑过校验脚本。
 */
function WeekChart({ days }: { days: OverviewData['days'] }) {
  const [hover, setHover] = useState<number | null>(null)
  const peak = Math.max(1, ...days.flatMap((d) => [d.in, d.out]))
  const step = peak <= 4 ? 1 : peak <= 20 ? 5 : peak <= 100 ? 25 : 10 ** Math.floor(Math.log10(peak))
  const top = Math.ceil(peak / step) * step
  const ticks = top % 2 === 0 ? [top, top / 2, 0] : [top, 0]      // 消息数是整数,刻度不能出现 0.5
  const empty = days.every((d) => !d.in && !d.out)
  const H = 136
  const total = days.reduce((n, d) => ({ in: n.in + d.in, out: n.out + d.out }), { in: 0, out: 0 })
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 pt-4">
        <h2 className="flex-1 text-body font-medium">近 7 天消息</h2>
        <span className="flex items-center gap-1.5 text-caption text-fg-2"><i className="size-2 rounded-[2px] bg-chart-in" />收到 <b className="tabular font-medium text-fg-1">{total.in}</b></span>
        <span className="flex items-center gap-1.5 text-caption text-fg-2"><i className="size-2 rounded-[2px] bg-chart-out" />发出 <b className="tabular font-medium text-fg-1">{total.out}</b></span>
      </div>
      <div className="relative mt-3 px-5 pb-3" aria-hidden="true">
        <div className="relative ml-7" style={{ height: H }}>
          {ticks.map((t) => (
            <div key={t} className="absolute inset-x-0 border-t border-line-1" style={{ top: H - (t / top) * H }}>
              <span className="tabular absolute -top-2 -left-7 w-5 text-right text-micro text-fg-4">{t}</span>
            </div>
          ))}
          {empty && <div className="absolute inset-0 grid place-items-center text-caption text-fg-3">近 7 天没有消息</div>}
          <div className="absolute inset-0 grid grid-cols-7">
            {days.map((d, i) => (
              <div key={d.date} className={cn('relative flex items-end justify-center gap-0.5 rounded-t-sm', hover === i && 'bg-fill-1')} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                {[[d.in, 'bg-chart-in'], [d.out, 'bg-chart-out']].map(([n, color]) => (
                  <i key={color as string} className={cn('block w-full max-w-5 rounded-t-xs', color as string)} style={{ height: (n as number) ? Math.max(2, ((n as number) / top) * H) : 0 }} />
                ))}
                {hover === i && (
                  <div className="pointer-events-none absolute bottom-full z-10 mb-1 rounded-sm bg-invert px-2 py-1 text-caption whitespace-nowrap text-invert-fg">
                    {d.date} · 收到 {d.in} · 发出 {d.out}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
        <div className="mt-1.5 ml-7 grid grid-cols-7">
          {days.map((d) => <span key={d.date} className="tabular text-center text-micro text-fg-3">{d.date}</span>)}
        </div>
      </div>
      <table className="sr-only">
        <caption>近 7 天每天收到和发出的消息数</caption>
        <thead><tr><th>日期</th><th>收到</th><th>发出</th></tr></thead>
        <tbody>{days.map((d) => <tr key={d.date}><td>{d.date}</td><td>{d.in}</td><td>{d.out}</td></tr>)}</tbody>
      </table>
    </Card>
  )
}

/** 定时任务: agent 或 lark task add 创建,到点后交给创建它的那个会话处理 */
function Tasks({ account: a }: { account: Account }) {
  const [tasks, setTasks] = useState<Task[] | null>(null)
  const base = `/accounts/${enc(a.id)}/tasks`
  const load = () => api<Task[]>('GET', base).then(setTasks).catch(() => undefined)
  useEffect(() => void load(), [a.id])
  usePoll(() => void load(), 10000)
  const remove = (t: Task) => attempt(async () => {
    await api('DELETE', `${base}/${t.id}`)
    await load()
    toast('已删除定时任务')
  })
  return (
    <Card>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 px-5 pt-4 pb-2">
        <h2 className="text-body font-medium">定时任务</h2>
        <span className="text-caption text-fg-3">账号运行时才会执行</span>
      </div>
      {tasks && !tasks.length ? (
        <p className="px-5 pb-4 text-small text-fg-3">还没有定时任务。可以在飞书里让 Agent 安排，比如「30 分钟后提醒我交周报」，也可以用 lark task add 创建。</p>
      ) : (
        <ul className="pb-2">
          {tasks?.map((t) => (
            <li key={t.id} className="flex items-center gap-3 px-5 py-2">
              <span className="tabular w-32 shrink-0 text-small text-fg-2">{t.when}</span>
              <span className="min-w-0 flex-1 truncate text-small">{t.content}</span>
              <Tag className="hidden max-w-32 truncate md:inline-flex">{t.chat}</Tag>
              <Button size="icon-sm" variant="ghost" aria-label="删除这个定时任务" onClick={() => remove(t)}><Trash2 /></Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

export function Overview({ account: a }: { account: Account }) {
  const { refresh } = useConsole()
  const [data, setData] = useState<OverviewData | null>(null)
  const [login, setLogin] = useState(false)
  const load = () => api<OverviewData>('GET', `/accounts/${enc(a.id)}/overview`).then(setData).catch(() => {})
  useEffect(() => void load(), [a.id])
  usePoll(() => void load(), 5000)

  const act = (what: 'start' | 'stop' | 'restart') => attempt(async () => {
    await api('POST', `/accounts/${enc(a.id)}/${what}`)
    await refresh()
  })
  const running = isActive(a.state)
  const base = `/a/${enc(a.id)}`
  const stats = data && [
    { n: data.counts.in, label: '收到消息' },
    { n: data.counts.out, label: '发出消息' },
    { n: data.chats, label: '会话' },
    { n: data.sessions.length, label: 'Agent 会话' },
  ]

  return (
    <div className="page-scroll h-full">
      <div className="fade-in mx-auto flex w-full max-w-[960px] flex-col gap-4 px-6 py-8">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
          <AccountAvatar account={a} size="xl" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="truncate text-title font-medium">{a.name}</h1>
              <StateBadge state={a.state} />
            </div>
            <p className="truncate text-small text-fg-3">
              {[a.company, a.region_label, BACKEND_LABEL[a.backend] ?? a.backend].filter(Boolean).join(' · ')}
              {running && a.queue.busy + a.queue.queued > 0 && ` · 处理中 ${a.queue.busy}，排队 ${a.queue.queued}`}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {running ? (
              <>
                <Button onClick={() => act('restart')}><RotateCw />重启</Button>
                <Button onClick={() => act('stop')}><Square />停止</Button>
              </>
            ) : a.has_credentials && a.state !== 'login_required' && (
              <Button variant="primary" onClick={() => act('start')}><Play />启动</Button>
            )}
            {!running && (
              <Button variant={a.has_credentials && a.state !== 'login_required' ? 'ghost' : 'primary'} onClick={() => setLogin(true)}>{a.has_credentials ? '重新登录' : '扫码登录'}</Button>
            )}
          </div>
        </div>

        {a.error && !['running', 'reconnecting'].includes(a.state) && (
          <div className="flex items-start gap-2.5 rounded-md bg-danger-soft px-4 py-3 text-small text-danger">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <span className="min-w-0 flex-1 break-words whitespace-pre-line">{a.state === 'login_required' ? '登录已失效，请重新扫码登录。' : a.error}</span>
          </div>
        )}

        {stats ? (
          <Card className="grid grid-cols-2 divide-line-1 md:grid-cols-4 md:divide-x">
            {stats.map((s) => (
              <div key={s.label} className="px-5 py-4">
                <div className="tabular text-heading font-medium">{s.n.toLocaleString()}</div>
                <div className="text-caption text-fg-3">{s.label}</div>
              </div>
            ))}
          </Card>
        ) : <Card className="h-[92px] animate-pulse" />}

        {data ? <WeekChart days={data.days} /> : <Card className="h-[230px] animate-pulse" />}

        <Tasks account={a} />

        <Card>
          <div className="flex items-center justify-between px-5 pt-4 pb-2">
            <h2 className="text-body font-medium">最近消息</h2>
            <Link to={`${base}/chats`} className="inline-flex items-center gap-1 text-small text-fg-3 no-underline hover:text-fg-1">
              全部聊天记录 <ArrowRight className="size-3.5" />
            </Link>
          </div>
          {data && !data.recent.length ? (
            <Empty title="还没有消息">启动账号后，收到的消息会出现在这里。</Empty>
          ) : (
            <ul className="pb-2">
              {data?.recent.map((m) => (
                <li key={m.id}>
                  <button type="button" onClick={() => navigate(`${base}/chats/${enc(m.chat_id)}`)} className="flex w-full items-center gap-3 px-5 py-2 text-left hover:bg-fill-1">
                    <Avatar src={m.direction === 'out' ? a.avatar : m.sender_id ? `/api/accounts/${enc(a.id)}/avatars/user/${m.sender_id}` : ''} name={m.direction === 'out' ? a.name : m.sender} size="sm" />
                    <span className="w-28 shrink-0 truncate text-small font-medium">{m.direction === 'out' ? '我' : m.sender}</span>
                    <span className="min-w-0 flex-1 truncate text-small text-fg-2">{m.content || typeLabel(m.type)}</span>
                    <Tag className="hidden max-w-32 truncate md:inline-flex">{m.chat}</Tag>
                    <span className="tabular w-20 shrink-0 text-right text-caption text-fg-3">{fmtTime(m.time)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <Dialog open={login} onClose={() => setLogin(false)} title="扫码登录">
        {login && (
          <LoginPanel
            accountId={a.id}
            region={a.region}
            onDone={async () => {
              setLogin(false)
              await refresh()
              toast('登录成功')
            }}
          />
        )}
      </Dialog>
    </div>
  )
}
