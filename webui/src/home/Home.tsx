import { ArrowRight, BookOpen, Bot, Check, Copy, Filter, Inbox, Layers, Loader2, MessagesSquare, Radio, Reply, Send, Terminal as TerminalIcon, Users } from 'lucide-react'
import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from 'react'
import { FooterName, Mark } from '../Logo'
import { Link } from '../router'
import { ThemeToggle } from '../store'
import { Avatar, GithubIcon, REPO_URL, Tag, btn, cn } from '../ui'
import { NavPills } from '../NavPills'

const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches

// 示例里的头像,来源和授权见 assets/avatars/SOURCE.md;人名都是虚构的
const AVATARS = import.meta.glob('../assets/avatars/*.{jpg,png}', { eager: true, import: 'default' }) as Record<string, string>
const av = (name: string) => AVATARS[`../assets/avatars/${name}.jpg`] ?? AVATARS[`../assets/avatars/${name}.png`]

function useInView<T extends Element>(threshold = 0.25) {
  const ref = useRef<T>(null)
  const [seen, setSeen] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => setSeen(!!e?.isIntersecting), { threshold })
    io.observe(el)
    return () => io.disconnect()
  }, [threshold])
  return [ref, seen] as const
}

function Reveal({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('reveal', className)}>{children}</div>
}

function SectionHead({ first, second, note }: { first: string; second: string; note: string }) {
  return (
    <div className="mb-8 grid gap-3 lg:grid-cols-[1fr_auto] lg:items-end">
      <h2 className="font-serif text-headline font-normal md:text-feature">
        {first}
        <span className="text-fg-3">{second}</span>
      </h2>
      <p className="max-w-[40ch] text-small text-fg-2 lg:ml-auto">{note}</p>
    </div>
  )
}

// ---------- 页头 ----------
function SiteHeader() {
  return (
    <div className="sticky top-0 z-30 flex h-14 items-start justify-center">
      <header className="header-float relative mx-auto flex h-14 w-full max-w-full items-center gap-3 px-5">
        <Link to="/" className="flex items-center gap-2 no-underline">
          <Mark size={26} />
          <span className="text-body font-medium tracking-tight">LarkAgentX</span>
        </Link>
        <div className="absolute left-1/2 hidden -translate-x-1/2 min-[960px]:block">
          <NavPills
            items={[
              { label: '功能', href: '#features' },
              { label: '工作方式', href: '#how' },
              { label: '快速开始', href: '#start' },
              { label: '文档', href: `${REPO_URL}#readme`, external: true },
            ]}
          />
        </div>
        <div className="ml-auto flex items-center gap-1">
          <a href={REPO_URL} target="_blank" rel="noreferrer" aria-label="GitHub" className={btn('ghost', 'icon')}>
            <GithubIcon />
          </a>
          <ThemeToggle />
          <Link to="/console" className={cn(btn('primary', 'md'), 'ml-1')}>
            打开控制台
          </Link>
        </div>
      </header>
    </div>
  )
}

// ---------- 首屏 ----------
const STORIES = [
  { who: '陈思远', avatar: av('chen-siyuan'), where: '会员中心重构', ask: '这个报错帮忙看下：Cannot read properties of undefined', reply: 'row.owner 在新建草稿时为空，已加判空并补上测试。' },
  { who: '周雨桐', avatar: av('zhou-yutong'), where: '私聊', ask: '昨天线上 5xx 多吗', reply: '昨天共 312 次，92% 来自 /export，今早 9 点后恢复正常。' },
  { who: '我', avatar: av('lin-zhixia'), where: '和自己的会话', ask: '部署一下 staging', reply: '已更新到 30530d1，健康检查通过。' },
  { who: '许嘉禾', avatar: av('xu-jiahe'), where: '研发周报', ask: '帮我把这周的 commit 整理成周报', reply: '本周 12 个 commit 已按 3 项工作整理，周报草稿如下。' },
  { who: '宋以宁', avatar: av('song-yining'), where: '话题 · 首页改版', ask: '这段文案翻译成英文', reply: '已翻译，附两个版本供选择。' },
  { who: '何嘉怡', avatar: av('he-jiayi'), where: '私聊', ask: '好的，谢谢', reply: '无需回复，已跳过。' },
  { who: '顾言', avatar: av('gu-yan'), where: '产品设计讨论', ask: '竞品这周有什么更新？', reply: '已查阅三家的更新日志，要点整理如下。' },
]

function StoryCard({ s }: { s: (typeof STORIES)[number] }) {
  return (
    <div className="flex w-80 shrink-0 flex-col gap-3 rounded-lg bg-surface-1 p-4 select-none">
      <div className="flex items-center gap-2">
        <Avatar src={s.avatar} name={s.who} size="xs" />
        <span className="text-small font-medium">{s.who}</span>
        <span className="truncate text-caption text-fg-3">{s.where}</span>
      </div>
      <p className="line-clamp-2 min-h-11 text-small text-fg-2">{s.ask}</p>
      <div className="flex min-h-11 items-start gap-2 rounded-sm bg-surface-3 px-3 py-2 shadow-raised">
        <Mark size={16} className="mt-0.5 shrink-0" />
        <p className="line-clamp-2 text-small">{s.reply}</p>
      </div>
    </div>
  )
}

function Hero() {
  const section = useRef<HTMLElement>(null)
  const lamp = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = section.current
    if (!el || reduced()) return
    let frame = 0
    const move = (e: PointerEvent) => {
      if (frame) return
      frame = requestAnimationFrame(() => {
        frame = 0
        const r = el.getBoundingClientRect()
        lamp.current?.style.setProperty('--x', `${e.clientX - r.left}px`)
        lamp.current?.style.setProperty('--y', `${e.clientY - r.top}px`)
      })
    }
    el.addEventListener('pointermove', move)
    return () => el.removeEventListener('pointermove', move)
  }, [])
  const delay = (ms: number) => ({ '--delay': `${ms}ms` }) as CSSProperties
  return (
    <section ref={section} className="relative isolate -mt-14 overflow-hidden pt-14">
      <div className="dot-field" />
      <div ref={lamp} className="dot-field-lamp" />
      <div className="mx-auto max-w-[1240px] px-6 pt-20 pb-14 sm:pt-28">
        <div className="blur-in" style={delay(40)}>
          <span className="glass inline-flex h-7 items-center gap-2 whitespace-nowrap rounded-full pr-3 pl-1 text-caption text-fg-2">
            <span className="rounded-full bg-surface-3 px-2 py-0.5 font-medium text-fg-1 shadow-raised dark:bg-fill-3">开源</span>
            支持飞书与 Lark
          </span>
        </div>
        <h1 className="blur-in mt-7 max-w-5xl text-headline font-medium sm:text-display lg:text-hero" style={delay(120)}>
          你的飞书账号，
          <span className="mt-1 block font-serif font-normal text-fg-3" style={{ fontSize: '1.06em' }}>
            直连本地 Coding Agent。
          </span>
        </h1>
        <p className="blur-in mt-8 max-w-3xl text-lead text-fg-2" style={delay(200)}>
          扫码登录后，收到的消息会交给本机的 Claude Code 或 Codex 处理，回复以你的账号发出。
          <br />
          无需配置飞书机器人，登录凭证和消息记录都保存在本地。
        </p>
        <div className="blur-in mt-9 flex flex-wrap gap-2" style={delay(240)}>
          <Link to="/console" className={btn('primary', 'lg')}>
            打开控制台 <ArrowRight />
          </Link>
          <a href="#start" className={btn('secondary', 'lg')}>
            快速开始
          </a>
          <a href={REPO_URL} target="_blank" rel="noreferrer" className={btn('ghost', 'lg')}>
            <GithubIcon /> GitHub
          </a>
        </div>
      </div>
      <div className="blur-in marquee overflow-hidden" style={delay(320)}>
        <div className="marquee-track">
          {[...STORIES, ...STORIES].map((s, i) => (
            <StoryCard key={i} s={s} />
          ))}
        </div>
      </div>
      <div className="blur-in flex flex-wrap items-center justify-center gap-x-10 gap-y-2 px-6 pt-8 pb-16 text-small font-medium text-fg-3" style={delay(380)}>
        <span className="font-normal text-fg-4">支持</span>
        <span>飞书</span>
        <span>Lark</span>
        <span>Claude Code</span>
        <span>Codex</span>
      </div>
    </section>
  )
}

// ---------- 产品自演示: 进视口才播 ----------
const SCENES = [
  {
    chip: '修报错', chat: '会员中心重构', chatAvatar: av('group-member-center'), type: '群聊', who: '陈思远', avatar: av('chen-siyuan'), backend: 'Claude Code',
    ask: '@林知夏 这个报错帮忙看下\nTypeError: Cannot read properties of undefined',
    steps: ['读取 src/list.js', '定位到 renderRow 没判空', '修复并跑通测试'],
    reply: 'row.owner 在新建草稿时为空，已加判空并补上测试。',
    cmd: 'lark send 7627… "row.owner 在新建草稿时…"',
  },
  {
    chip: '查日志', chat: '周雨桐', chatAvatar: av('zhou-yutong'), type: '私聊', who: '周雨桐', avatar: av('zhou-yutong'), backend: 'Codex',
    ask: '昨天线上 5xx 多吗',
    steps: ['拉取昨日网关日志', '按路径聚合'],
    reply: '昨天 5xx 共 312 次，其中 92% 来自 /export，今早 9 点后已恢复。',
    cmd: 'lark send 7633… "昨天 5xx 共 312 次…"',
  },
  {
    chip: '写周报', chat: '研发周报', chatAvatar: av('group-weekly'), type: '话题', who: '许嘉禾', avatar: av('xu-jiahe'), backend: 'Claude Code',
    ask: '帮我把这周的 commit 整理成周报',
    steps: ['读取本周 commit', '按模块归类', '生成草稿'],
    reply: '本周 12 个 commit 分为 3 项工作：导出重构、登录修复、性能优化。周报草稿如下。',
    cmd: 'lark send 7666… "本周 12 个 commit…" --root 7666…',
  },
]
const STEP_MS = 900

function ProductDemo() {
  const [ref, inView] = useInView<HTMLDivElement>(0.3)
  const [scene, setScene] = useState(0)
  const [phase, setPhase] = useState(0)     // 0 空，1 收到，2.. 步骤，steps+2 回复
  const s = SCENES[scene]!
  const last = s.steps.length + 2

  useEffect(() => {
    if (reduced()) {
      setPhase(last)
      return
    }
    if (!inView) return
    const wait = phase === 0 ? 450 : phase === 1 ? 1100 : phase >= last ? 3600 : STEP_MS
    const t = setTimeout(() => {
      if (phase >= last) {
        setScene((n) => (n + 1) % SCENES.length)
        setPhase(0)
      } else setPhase(phase + 1)
    }, wait)
    return () => clearTimeout(t)
  }, [phase, inView, last])

  const total = 450 + 1100 + s.steps.length * STEP_MS + 3600
  const running = phase >= 1 && phase < last
  return (
    <div ref={ref}>
      <div className="overflow-hidden rounded-xl bg-surface-3 shadow-float">
        <div className="flex h-13 items-center gap-2.5 border-b border-line-1 px-4">
          <Avatar src={s.chatAvatar} name={s.chat} size="sm" />
          <span className="truncate text-body font-medium">{s.chat}</span>
          <Tag>{s.type}</Tag>
          <span className="ml-auto flex items-center gap-1.5 text-caption text-fg-3">
            {running ? <Loader2 className="spin size-3.5" /> : <span className="size-2 rounded-full bg-success" />}
            {s.backend}
          </span>
        </div>
        <div className="flex h-[360px] flex-col gap-3 overflow-hidden bg-surface-1/50 p-5">
          {phase >= 1 && (
            <div key={`a${scene}`} className="rise flex max-w-[85%] gap-2.5">
              <Avatar src={s.avatar} name={s.who} size="sm" />
              <div>
                <div className="mb-1 text-caption text-fg-3">{s.who}</div>
                <div className="rounded-md bg-surface-3 px-3 py-2 whitespace-pre-wrap text-small shadow-raised dark:bg-fill-2">{s.ask}</div>
              </div>
            </div>
          )}
          {phase >= 2 && (
            <div key={`s${scene}`} className="rise ml-[38px] flex flex-col gap-1 font-mono text-caption text-fg-3">
              {s.steps.slice(0, phase - 1).map((step, i) => (
                <div key={step} className="rise flex items-center gap-2">
                  {i === phase - 2 && phase < last ? <Loader2 className="spin size-3" /> : <Check className="size-3 text-success" />}
                  {step}
                </div>
              ))}
            </div>
          )}
          <div className="mt-auto" />
          {phase >= last && (
            <div key={`r${scene}`} className="rise flex flex-col items-end gap-1.5">
              <div className="max-w-[85%] rounded-md bg-accent-soft px-3 py-2 text-small">{s.reply}</div>
              <div className="font-mono text-micro text-fg-4">$ {s.cmd}</div>
            </div>
          )}
        </div>
      </div>
      <div className="scrollbar-none mt-3 flex gap-2 overflow-x-auto">
        {SCENES.map((x, i) => (
          <button
            key={x.chip}
            type="button"
            onClick={() => {
              setScene(i)
              setPhase(0)
            }}
            className={cn('press relative h-8 shrink-0 overflow-hidden rounded-full px-3.5 text-small font-medium', i === scene ? 'bg-surface-3 text-fg-1 shadow-raised dark:bg-fill-2' : 'text-fg-3 hover:text-fg-1')}
          >
            {x.chip}
            {i === scene && inView && !reduced() && (
              <span key={`${scene}`} className="progress-line absolute inset-x-3 bottom-0 h-px bg-fg-2" style={{ '--duration': `${total}ms` } as CSSProperties} />
            )}
          </button>
        ))}
      </div>
    </div>
  )
}

const FEATURES = [
  { icon: Users, title: '多账号', text: '扫码添加，飞书与 Lark 账号可同时在线。姓名、头像和公司信息自动获取。' },
  { icon: MessagesSquare, title: '聊天记录', text: '按会话和话题浏览，支持回填历史消息，也可以直接在网页发送。' },
  { icon: Reply, title: '回复方式', text: '可回复到话题或主会话，支持直接发送、引用回复和开话题回复。' },
  { icon: Filter, title: '触发规则', text: '按前缀、关键词和 @ 提及过滤，私聊和单个会话可分别开关。' },
  { icon: Bot, title: 'Claude Code 与 Codex', text: '每个账号可选用不同的 Agent，按会话保持上下文。' },
  { icon: Layers, title: '内部接口', text: '解码 25 种消息类型，可直接调用 2200+ 个网关接口。' },
]

function Features() {
  return (
    <section id="features" className="mx-auto max-w-[1240px] scroll-mt-16 px-6 py-20">
      <Reveal>
        <SectionHead first="一个控制台，" second="管理所有账号" note="登录、查看消息和调整回复方式都在这里完成。设置保存后立即生效，无需重启。" />
        <div className="grid grid-cols-[minmax(0,1fr)] gap-10 lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-14">
          <ProductDemo />
          <ul className="flex flex-col divide-y divide-line-1">
            {FEATURES.map((f) => (
              <li key={f.title} className="flex gap-3.5 py-4 first:pt-0 last:pb-0">
                <span className="grid size-8 shrink-0 place-items-center rounded-sm bg-fill-2 text-fg-2">
                  <f.icon className="size-4" />
                </span>
                <div>
                  <div className="text-body font-medium">{f.title}</div>
                  <p className="text-small text-fg-3">{f.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </Reveal>
    </section>
  )
}

// ---------- 一条消息,一张图 ----------
const NODES = [
  { x: 90, y: 140, icon: Inbox, title: '飞书 / Lark', sub: '收到消息' },
  { x: 290, y: 140, icon: Radio, title: '本地长连接', sub: '解码并入库' },
  { x: 490, y: 140, icon: Filter, title: '按会话排队', sub: '按规则过滤' },
  { x: 700, y: 62, icon: Bot, title: 'Claude Code', sub: '持久会话' },
  { x: 700, y: 218, icon: TerminalIcon, title: 'Codex', sub: '持久会话' },
  { x: 900, y: 140, icon: Send, title: 'lark send', sub: '以你的账号发送' },
]
const EDGES = [
  'M90 140H290', 'M290 140H490',
  'M490 140C590 140 600 62 700 62', 'M490 140C590 140 600 218 700 218',
  'M700 62C800 62 810 140 900 140', 'M700 218C800 218 810 140 900 140',
]
const LIGHT_PATHS = ['M90 140H290H490C590 140 600 62 700 62C800 62 810 140 900 140', 'M90 140H290H490C590 140 600 218 700 218C800 218 810 140 900 140']

function FlowGraph() {
  const still = reduced()
  return (
    <>
      <div className="relative hidden aspect-[1000/280] lg:block">
        <svg viewBox="0 0 1000 280" className="absolute inset-0 size-full" aria-hidden="true">
          {EDGES.map((d) => (
            <path key={d} d={d} fill="none" stroke="var(--line-3)" strokeWidth="1.25" />
          ))}
          {!still && LIGHT_PATHS.map((d, i) => (
            <circle key={d} r="3" fill="var(--accent)">
              <animateMotion dur="5s" begin={`${i * 2.5}s`} repeatCount="indefinite" path={d} keyPoints="0;1" keyTimes="0;1" calcMode="linear" />
            </circle>
          ))}
        </svg>
        {NODES.map((n) => (
          <div
            key={n.title}
            className="absolute flex w-[176px] -translate-x-1/2 -translate-y-1/2 items-center gap-2.5 rounded-md bg-surface-3 px-3 py-2.5 shadow-raised dark:bg-surface-2"
            style={{ left: `${n.x / 10}%`, top: `${n.y / 2.8}%` }}
          >
            <span className="grid size-8 shrink-0 place-items-center rounded-sm bg-fill-2 text-fg-2">
              <n.icon className="size-4" />
            </span>
            <div className="min-w-0">
              <div className="truncate text-small font-medium">{n.title}</div>
              <div className="truncate text-caption text-fg-3">{n.sub}</div>
            </div>
          </div>
        ))}
      </div>
      <ol className="flex flex-col gap-2 lg:hidden">
        {NODES.map((n) => (
          <li key={n.title} className="flex items-center gap-2.5 rounded-md bg-surface-3 px-3 py-2.5 shadow-raised dark:bg-surface-2">
            <span className="grid size-8 shrink-0 place-items-center rounded-sm bg-fill-2 text-fg-2">
              <n.icon className="size-4" />
            </span>
            <div>
              <div className="text-small font-medium">{n.title}</div>
              <div className="text-caption text-fg-3">{n.sub}</div>
            </div>
          </li>
        ))}
      </ol>
    </>
  )
}

const FACTS = [
  { n: '25', label: '种消息类型解码' },
  { n: '2,202', label: '个网关接口可直接调用' },
  { n: '8,296', label: '个 proto 类型定义' },
  { n: '2', label: '种 Agent 后端' },
]

function HowItRuns() {
  return (
    <section id="how" className="mx-auto max-w-[1240px] scroll-mt-16 px-6 py-20">
      <Reveal>
        <SectionHead first="从收到消息，" second="到发出回复" note="LarkAgentX 没有中转服务器。消息经长连接直达本机，按会话排队后交给 Agent，由 Agent 判断是否回复。" />
        <div className="overflow-hidden rounded-xl bg-surface-1">
          <div className="p-5 lg:px-8 lg:py-6">
            <FlowGraph />
          </div>
          <div className="grid grid-cols-2 border-t border-line-1 md:grid-cols-4">
            {FACTS.map((f) => (
              <div key={f.label} className="px-6 py-6 lg:px-8">
                <div className="tabular text-headline font-medium">{f.n}</div>
                <div className="mt-1 text-caption text-fg-3">{f.label}</div>
              </div>
            ))}
          </div>
        </div>
      </Reveal>
    </section>
  )
}

// ---------- 快速开始 ----------
const COMMANDS = ['git clone https://github.com/cv-cat/LarkAgentX', 'cd LarkAgentX && pip install -e .', 'lark web']
const CHAR_MS = 22

function Terminal() {
  const [ref, inView] = useInView<HTMLDivElement>(0.4)
  const [line, setLine] = useState(0)
  const [chars, setChars] = useState(0)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (reduced()) {
      setLine(COMMANDS.length)
      return
    }
    if (!inView || line >= COMMANDS.length) return
    const full = COMMANDS[line]!.length
    const t = chars < full
      ? setTimeout(() => setChars(chars + 1), CHAR_MS)
      : setTimeout(() => {
          setLine(line + 1)
          setChars(0)
        }, 420)
    return () => clearTimeout(t)
  }, [inView, line, chars])
  const done = line >= COMMANDS.length
  return (
    <div ref={ref} className="overflow-hidden rounded-xl bg-terminal text-terminal-fg shadow-float">
      <div className="flex h-10 items-center gap-1.5 px-4">
        {[0, 1, 2].map((i) => <span key={i} className="size-2.5 rounded-full bg-terminal-fg/15" />)}
        <button
          type="button"
          className="press ml-auto inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-caption text-terminal-fg/60 hover:text-terminal-fg"
          onClick={() => {
            void navigator.clipboard?.writeText(COMMANDS.join('\n'))
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
          }}
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <div className="min-h-44 px-5 pb-5 font-mono text-small leading-7">
        {COMMANDS.map((c, i) => (i < line || i === line) && (
          <div key={c}>
            <span className="text-terminal-fg/40">$ </span>
            {i < line ? c : c.slice(0, chars)}
            {i === line && <span className="terminal-caret" />}
          </div>
        ))}
        {done && (
          <div className="rise text-terminal-ok">
            ✓ LarkAgentX: http://127.0.0.1:8765
            <span className="terminal-caret ml-2" />
          </div>
        )}
      </div>
    </div>
  )
}

const PROMISES = [
  { title: '数据保存在本地', text: '登录凭证存放在 ~/.larkx，消息默认写入本地 SQLite，也可切换到 MySQL。' },
  { title: '默认仅本机访问', text: '只监听 127.0.0.1；开放到局域网时必须设置访问令牌。' },
  { title: '使用本机的 Agent', text: '调用本机已安装的 Claude Code 或 Codex CLI。' },
]

function Start() {
  return (
    <section id="start" className="mx-auto max-w-[1240px] scroll-mt-16 px-6 pt-20 pb-28">
      <Reveal>
        <SectionHead first="本地运行，" second="三行命令启动" note="需要 Python 3.9 及以上。未安装 Agent 时仍可接收并保存消息。" />
        <div className="grid grid-cols-[minmax(0,1fr)] items-center gap-10 lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-14">
          <Terminal />
          <div>
            <ul className="flex flex-col gap-5">
              {PROMISES.map((p) => (
                <li key={p.title}>
                  <div className="text-body font-medium">{p.title}</div>
                  <p className="text-small text-fg-3">{p.text}</p>
                </li>
              ))}
            </ul>
            <div className="mt-7 flex flex-wrap gap-2">
              <Link to="/console" className={btn('primary', 'lg')}>
                打开控制台 <ArrowRight />
              </Link>
              <a href={`${REPO_URL}#readme`} target="_blank" rel="noreferrer" className={btn('secondary', 'lg')}>
                <BookOpen /> 文档
              </a>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  )
}

// ---------- 页脚 ----------
function SiteFooter() {
  const col = (title: string, links: { label: string; href: string }[]) => (
    <div>
      <div className="mb-3 text-caption text-fg-4">{title}</div>
      <ul className="flex flex-col gap-2">
        {links.map((l) => (
          <li key={l.label}>
            <a href={l.href} target={l.href.startsWith('http') ? '_blank' : undefined} rel="noreferrer" className="text-small text-fg-2 no-underline hover:text-fg-1">
              {l.label}
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
  return (
    <footer className="overflow-hidden border-t border-line-1">
      <div className="mx-auto grid max-w-[1240px] gap-10 px-6 pt-14 pb-8 md:grid-cols-[1fr_auto]">
        <div>
          <div className="flex items-center gap-2">
            <Mark size={26} />
            <span className="text-body font-medium">LarkAgentX</span>
          </div>
          <p className="mt-3 max-w-sm text-small text-fg-2">
            飞书账号直连本地 Coding Agent。<span className="text-fg-3">无需配置机器人。</span>
          </p>
          <a href={REPO_URL} target="_blank" rel="noreferrer" className={cn(btn('secondary', 'md'), 'mt-4')}>
            <GithubIcon /> GitHub
          </a>
        </div>
        <div className="flex gap-16">
          {col('产品', [
            { label: '控制台', href: '/console' },
            { label: '功能', href: '#features' },
            { label: '工作方式', href: '#how' },
          ])}
          {col('资源', [
            { label: '文档', href: `${REPO_URL}#readme` },
            { label: '问题反馈', href: `${REPO_URL}/issues` },
            { label: '讨论', href: `${REPO_URL}/discussions` },
          ])}
        </div>
      </div>
      <div className="mx-auto flex max-w-[1240px] flex-wrap justify-between gap-2 px-6 pb-10 text-caption text-fg-4">
        <span>社区开源项目，与飞书官方无关。飞书和 Lark 是其所有者的商标。</span>
      </div>
      <div className="mx-auto max-w-[1240px] px-6">
        <FooterName className="block w-full" />
      </div>
    </footer>
  )
}

export function Home() {
  return (
    <div className="min-h-dvh bg-bg">
      <SiteHeader />
      <main>
        <Hero />
        <Features />
        <HowItRuns />
        <Start />
      </main>
      <SiteFooter />
    </div>
  )
}
