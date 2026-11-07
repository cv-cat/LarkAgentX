import { X } from 'lucide-react'
import { Dialog as RDialog, DropdownMenu as RMenu, Switch as RSwitch, Tooltip as RTooltip } from 'radix-ui'
import {
  type ButtonHTMLAttributes, type InputHTMLAttributes, type KeyboardEvent, type ReactNode, type TextareaHTMLAttributes,
  forwardRef, useEffect, useRef, useState, useSyncExternalStore,
} from 'react'
import { type Account, type AccountState, withToken } from './api'

export const cn = (...xs: (string | false | null | undefined)[]) => xs.filter(Boolean).join(' ')

// ---------- 按钮: 一屏只放一个主按钮;主按钮是反色,强调色留给焦点和选中 ----------
type BtnVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
type BtnSize = 'sm' | 'md' | 'lg' | 'icon' | 'icon-sm'
const VARIANT: Record<BtnVariant, string> = {
  primary: 'sheen bg-invert text-invert-fg shadow-raised hover:bg-invert/90',
  secondary: 'bg-fill-2 text-fg-1 ring-1 ring-line-2 ring-inset hover:bg-fill-3',
  ghost: 'text-fg-2 hover:bg-fill-2 hover:text-fg-1',
  danger: 'bg-danger-soft text-danger ring-1 ring-danger/25 ring-inset hover:bg-danger hover:text-invert-fg',
}
const SIZE: Record<BtnSize, string> = {
  sm: 'h-7 rounded-full px-3 text-small [&_svg]:size-3.5',
  md: 'h-8 rounded-full px-3.5 text-small [&_svg]:size-4',
  lg: 'h-10 rounded-full px-5 text-body [&_svg]:size-4',
  icon: 'size-8 rounded-full [&_svg]:size-4',
  'icon-sm': 'size-7 rounded-full [&_svg]:size-3.5',
}
export function btn(variant: BtnVariant = 'secondary', size: BtnSize = 'md') {
  return cn(
    'press inline-flex shrink-0 select-none items-center justify-center gap-1.5 whitespace-nowrap font-medium no-underline disabled:pointer-events-none disabled:opacity-40',
    VARIANT[variant], SIZE[size],
  )
}
export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: BtnSize }>(
  function Button({ variant, size, className, type = 'button', ...rest }, ref) {
    return <button ref={ref} type={type} className={cn(btn(variant, size), className)} {...rest} />
  },
)

// ---------- 状态 ----------
const STATE: Record<AccountState, { label: string; tone: 'ok' | 'busy' | 'bad' | 'idle' }> = {
  no_login: { label: '未登录', tone: 'idle' },
  stopped: { label: '已停止', tone: 'idle' },
  idle: { label: '已停止', tone: 'idle' },
  starting: { label: '启动中', tone: 'busy' },
  connecting: { label: '连接中', tone: 'busy' },
  reconnecting: { label: '重连中', tone: 'busy' },
  running: { label: '运行中', tone: 'ok' },
  login_required: { label: '需要重新登录', tone: 'bad' },
  error: { label: '出错', tone: 'bad' },
}
export const stateLabel = (s: AccountState) => STATE[s]?.label ?? s
export const isActive = (s: AccountState) => ['starting', 'connecting', 'running', 'reconnecting'].includes(s)

export function StateDot({ state, className }: { state: AccountState; className?: string }) {
  const tone = STATE[state]?.tone ?? 'idle'
  return (
    <span
      aria-hidden="true"
      className={cn(
        'inline-block size-2 shrink-0 rounded-full',
        tone === 'ok' && 'bg-success',
        tone === 'busy' && 'pulse-dot bg-warning',
        tone === 'bad' && 'bg-danger',
        tone === 'idle' && 'bg-fg-4',
        className,
      )}
    />
  )
}

export function StateBadge({ state }: { state: AccountState }) {
  const tone = STATE[state]?.tone ?? 'idle'
  return (
    <span
      className={cn(
        'inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-caption font-medium',
        tone === 'ok' && 'bg-success-soft text-success',
        tone === 'busy' && 'bg-warning-soft text-warning',
        tone === 'bad' && 'bg-danger-soft text-danger',
        tone === 'idle' && 'bg-fill-2 text-fg-2',
      )}
    >
      <StateDot state={state} />
      {stateLabel(state)}
    </span>
  )
}

export function Tag({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn('inline-flex h-5 items-center rounded-full bg-fill-2 px-2 text-micro font-medium text-fg-2', className)}>{children}</span>
}

// ---------- 头像: 飞书真实头像,拿不到时退回中性的首字母(不搞彩色) ----------
// 加载失败的地址记一分钟: 期间直接显示首字母,过后自动重试。比如登录失效时全部失败,重新登录后不用刷新页面也会恢复
const broken = new Map<string, number>()
const AVATAR_RETRY_MS = 60_000
const initial = (name: string) => {
  const c = (name || '?').trim().codePointAt(0)
  return c ? String.fromCodePoint(c).toUpperCase() : '?'
}
const AVATAR_SIZE = { xs: 'size-5 text-micro', sm: 'size-7 text-caption', md: 'size-8 text-small', lg: 'size-10 text-body', xl: 'size-14 text-title' }

export function Avatar({ src, name, size = 'md', className }: { src?: string; name: string; size?: keyof typeof AVATAR_SIZE; className?: string }) {
  const url = src ? withToken(src) : ''
  const [, bump] = useState(0)
  const failedAt = url ? broken.get(url) : undefined
  const waiting = failedAt !== undefined && Date.now() - failedAt < AVATAR_RETRY_MS
  useEffect(() => {
    if (!waiting) return
    const t = setTimeout(() => bump((n) => n + 1), AVATAR_RETRY_MS - (Date.now() - failedAt!))
    return () => clearTimeout(t)
  }, [waiting, failedAt])
  const show = url && !waiting
  return (
    <span className={cn('relative inline-grid shrink-0 select-none place-items-center overflow-hidden rounded-full bg-fill-3 font-medium text-fg-2', AVATAR_SIZE[size], className)}>
      {initial(name)}
      {show && (
        <img
          src={url}
          alt=""
          loading="lazy"
          className="absolute inset-0 size-full object-cover"
          onError={() => {
            broken.set(url, Date.now())
            bump((n) => n + 1)
          }}
        />
      )}
    </span>
  )
}

export function AccountAvatar({ account, size }: { account: Account; size?: keyof typeof AVATAR_SIZE }) {
  return <Avatar src={account.avatar} name={account.name} size={size} />
}

// ---------- 表单 ----------
const INPUT = 'w-full rounded-sm bg-fill-2 px-3 text-body text-fg-1 outline-none ring-1 ring-transparent ring-inset transition-shadow placeholder:text-fg-4 focus:bg-transparent focus:ring-accent-ring disabled:opacity-50'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={cn(INPUT, 'h-9', className)} autoComplete="off" {...rest} />
})
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={cn(INPUT, 'min-h-22 resize-y py-2', className)} {...rest} />
})

export function Field({ label, hint, children, className }: { label: ReactNode; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={cn('flex flex-col gap-1.5', className)}>
      <span className="text-small font-medium text-fg-1">{label}</span>
      {children}
      {hint && <span className="text-caption text-fg-3">{hint}</span>}
    </label>
  )
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <RSwitch.Root
      checked={checked}
      onCheckedChange={onChange}
      aria-label={label}
      disabled={disabled}
      className="relative h-5 w-9 shrink-0 cursor-pointer rounded-full bg-fill-3 transition-colors disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-accent"
    >
      <RSwitch.Thumb className="block size-4 translate-x-0.5 rounded-full bg-surface-3 shadow-raised transition-transform duration-150 data-[state=checked]:translate-x-4.5 dark:bg-invert" />
    </RSwitch.Root>
  )
}

/** 一行开关： 左边说明，右边开关 */
export function SwitchRow({ title, hint, checked, onChange }: { title: string; hint?: ReactNode; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center gap-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="text-body font-medium">{title}</div>
        {hint && <div className="text-caption text-fg-3">{hint}</div>}
      </div>
      <Switch checked={checked} onChange={onChange} label={title} />
    </div>
  )
}

/** 分段控件： 胶囊底 + 选中项是白色小胶囊 */
export function Seg<T extends string>({ value, options, onChange, className }: { value: T; options: { value: T; label: string; disabled?: boolean }[]; onChange: (v: T) => void; className?: string }) {
  return (
    <div className={cn('scrollbar-none inline-flex max-w-full gap-0.5 overflow-x-auto rounded-full bg-fill-2 p-0.5', className)} role="radiogroup">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          disabled={o.disabled}
          onClick={() => onChange(o.value)}
          className={cn(
            'press h-7 whitespace-nowrap rounded-full px-3 text-small font-medium disabled:opacity-40',
            o.value === value ? 'bg-surface-3 text-fg-1 shadow-raised dark:bg-fill-3' : 'text-fg-2 hover:text-fg-1',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** 回车添加的标签输入 */
export function TagInput({ value, onChange, placeholder, id }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string; id?: string }) {
  const [draft, setDraft] = useState('')
  const commit = () => {
    const v = draft.trim().replace(/[,，]$/, '')
    if (v && !value.includes(v)) onChange([...value, v])
    setDraft('')
  }
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.nativeEvent.isComposing) return
    if (e.key === 'Enter' || e.key === ',' || e.key === '，') {
      e.preventDefault()
      commit()
    } else if (e.key === 'Backspace' && !draft && value.length) {
      onChange(value.slice(0, -1))
    }
  }
  return (
    <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-sm bg-fill-2 px-2 py-1.5 ring-1 ring-transparent ring-inset transition-shadow focus-within:bg-transparent focus-within:ring-accent-ring">
      {value.map((v) => (
        <span key={v} className="inline-flex h-6 items-center gap-1 rounded-full bg-surface-3 pr-1 pl-2.5 text-caption shadow-raised dark:bg-fill-3">
          {v}
          <button type="button" aria-label={`移除 ${v}`} className="press grid size-4 place-items-center rounded-full text-fg-3 hover:bg-fill-3 hover:text-fg-1" onClick={() => onChange(value.filter((x) => x !== v))}>
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        autoComplete="off"
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKey}
        onBlur={commit}
        placeholder={value.length ? '' : placeholder ?? '回车添加'}
        className="h-6 min-w-24 flex-1 bg-transparent px-1 text-small outline-none placeholder:text-fg-4"
      />
    </div>
  )
}

// ---------- 浮层 ----------
export function Dialog({ open, onClose, title, children, width = 'max-w-md' }: { open: boolean; onClose: () => void; title: string; children: ReactNode; width?: string }) {
  return (
    <RDialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <RDialog.Portal>
        <RDialog.Overlay className="fade-in fixed inset-0 z-40 bg-scrim backdrop-blur-[2px]" />
        <RDialog.Content
          aria-describedby={undefined}
          className={cn('pop-in fixed top-1/2 left-1/2 z-50 max-h-[92dvh] w-[calc(100%-32px)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl bg-surface-3 p-6 shadow-overlay', width)}
        >
          <RDialog.Title className="text-title font-medium">{title}</RDialog.Title>
          <RDialog.Close aria-label="关闭" className={cn(btn('ghost', 'icon-sm'), 'absolute top-4 right-4')}>
            <X />
          </RDialog.Close>
          <div className="mt-4">{children}</div>
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  )
}

export function Confirm({ open, onClose, title, body, ok, onOk }: { open: boolean; onClose: () => void; title: string; body: ReactNode; ok: string; onOk: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} title={title}>
      <p className="text-body text-fg-2">{body}</p>
      <div className="mt-6 flex justify-end gap-2">
        <Button onClick={onClose}>取消</Button>
        <Button variant="danger" onClick={onOk}>{ok}</Button>
      </div>
    </Dialog>
  )
}

export const MenuRoot = RMenu.Root
export const MenuTrigger = RMenu.Trigger
export function MenuContent({ children, align = 'start' }: { children: ReactNode; align?: 'start' | 'end' | 'center' }) {
  return (
    <RMenu.Portal>
      <RMenu.Content align={align} sideOffset={6} className="pop-in z-50 min-w-60 rounded-md p-1 menu-panel">
        {children}
      </RMenu.Content>
    </RMenu.Portal>
  )
}
export function MenuItem({ children, onSelect }: { children: ReactNode; onSelect: () => void }) {
  return (
    <RMenu.Item onSelect={onSelect} className="flex min-h-9 cursor-pointer items-center gap-2.5 rounded-sm px-2 py-1 text-small outline-none data-[highlighted]:bg-fill-2">
      {children}
    </RMenu.Item>
  )
}
export const MenuSeparator = () => <RMenu.Separator className="my-1 h-px bg-line-1" />

export const TooltipProvider = RTooltip.Provider
export function Tip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <RTooltip.Root delayDuration={250}>
      <RTooltip.Trigger asChild>{children}</RTooltip.Trigger>
      <RTooltip.Portal>
        <RTooltip.Content sideOffset={6} className="fade-in z-50 rounded-sm bg-invert px-2 py-1 text-caption text-invert-fg">
          {label}
        </RTooltip.Content>
      </RTooltip.Portal>
    </RTooltip.Root>
  )
}

// ---------- 提示条 ----------
type ToastItem = { id: number; text: string; err?: boolean }
let toasts: ToastItem[] = []
let seq = 0
const subs = new Set<() => void>()
const emit = () => subs.forEach((f) => f())
export function toast(text: string, err = false) {
  const id = ++seq
  toasts = [...toasts, { id, text, err }]
  emit()
  setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== id)
    emit()
  }, err ? 6000 : 2600)
}
export function Toasts() {
  const items = useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f) } }, () => toasts)
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-5 z-[60] flex flex-col items-center gap-2 px-4" role="status">
      {items.map((t) => (
        <div key={t.id} className={cn('pop-in max-w-md rounded-full px-4 py-2 text-small shadow-overlay', t.err ? 'bg-danger text-invert-fg' : 'bg-invert text-invert-fg')}>
          {t.text}
        </div>
      ))}
    </div>
  )
}

/** 跑一个操作，失败就弹错误，不让页面崩 */
export async function attempt<T>(fn: () => Promise<T>): Promise<T | undefined> {
  try {
    return await fn()
  } catch (e) {
    toast((e as Error).message || '操作失败', true)
    return undefined
  }
}

// ---------- 其它 ----------
export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      {icon && <div className="mb-1 grid size-11 place-items-center rounded-full bg-fill-2 text-fg-3 [&_svg]:size-5">{icon}</div>}
      <h3 className="text-lead font-medium">{title}</h3>
      {children && <div className="max-w-sm text-small text-fg-3">{children}</div>}
    </div>
  )
}

export function Card({ children, className }: { children?: ReactNode; className?: string }) {
  return <div className={cn('rounded-lg bg-surface-3 shadow-raised', className)}>{children}</div>
}

/** 轮询： 标签页在后台时暂停 */
export function usePoll(fn: () => void, ms: number) {
  const latest = useRef(fn)
  latest.current = fn
  useEffect(() => {
    const t = setInterval(() => {
      if (!document.hidden) latest.current()
    }, ms)
    return () => clearInterval(t)
  }, [ms])
}

export function GithubIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className={className}>
      <path d="M12 .5C5.73.5.75 5.48.75 11.75c0 4.97 3.22 9.18 7.69 10.67.56.1.77-.24.77-.54 0-.27-.01-.97-.02-1.91-3.13.68-3.79-1.51-3.79-1.51-.51-1.3-1.25-1.65-1.25-1.65-1.02-.7.08-.68.08-.68 1.13.08 1.72 1.16 1.72 1.16 1 1.72 2.63 1.22 3.27.93.1-.73.39-1.22.71-1.5-2.5-.28-5.13-1.25-5.13-5.57 0-1.23.44-2.24 1.16-3.03-.12-.28-.5-1.43.11-2.98 0 0 .95-.3 3.1 1.16.9-.25 1.86-.37 2.82-.38.96 0 1.92.13 2.82.38 2.15-1.46 3.1-1.16 3.1-1.16.61 1.55.23 2.7.11 2.98.72.79 1.16 1.8 1.16 3.03 0 4.33-2.64 5.28-5.15 5.56.4.35.76 1.03.76 2.08 0 1.5-.01 2.71-.01 3.08 0 .3.2.65.78.54A11.26 11.26 0 0 0 23.25 11.75C23.25 5.48 18.27.5 12 .5Z" />
    </svg>
  )
}

export const REPO_URL = 'https://github.com/cv-cat/LarkAgentX'

/** 消息没有文字内容时的占位 */
const TYPE_LABEL: Record<string, string> = { IMAGE: '图片', CARD: '卡片', FILE: '文件', AUDIO: '语音', MEDIA: '视频', STICKER: '表情', POST: '富文本', MERGE_FORWARD: '合并转发' }
export const typeLabel = (t: string) => `[${TYPE_LABEL[t] ?? '消息'}]`

// ---------- 时间 ----------
const pad = (n: number) => String(n).padStart(2, '0')
export function fmtTime(ts: number): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const now = new Date()
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  if (d.toDateString() === now.toDateString()) return hm
  const y = new Date(now)
  y.setDate(now.getDate() - 1)
  if (d.toDateString() === y.toDateString()) return '昨天 ' + hm
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`
}
export function fmtDay(ts: number): string {
  const d = new Date(ts * 1000)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) return '今天'
  const y = new Date(now)
  y.setDate(now.getDate() - 1)
  if (d.toDateString() === y.toDateString()) return '昨天'
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
