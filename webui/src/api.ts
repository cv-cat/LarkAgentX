/** 控制台的后端接口。类型和 larkx/web/manager.py 的返回一一对应。 */

export type AccountState =
  | 'no_login' | 'stopped' | 'idle' | 'starting' | 'connecting' | 'running' | 'reconnecting' | 'login_required' | 'error'

export interface Account {
  id: string
  name: string
  remark: string
  company: string
  avatar: string
  region: string
  region_label: string
  autostart: boolean
  has_credentials: boolean
  user_id: string
  saved_at: number
  state: AccountState
  error: string
  backend: string
  memory: boolean
  queue: { busy: number; queued: number }
}

export interface Meta {
  version: string
  backends: { id: string; label: string; installed: boolean }[]
  regions: { id: string; label: string }[]
  auth_required: boolean
}

export interface Runtime {
  id: string
  label: string
  binary: string
  installed: boolean
  path: string
  version: string
}

export interface Overview {
  counts: { in: number; out: number }
  chats: number
  sessions: { key: string; chat_id: string; anchor: string; started: boolean; msg_count: number; last_active: string }[]
  recent: { id: number; time: number; direction: string; chat_id: string; chat: string; sender: string; sender_id: string; type: string; content: string }[]
  days: { date: string; in: number; out: number }[]
}

export interface Chat {
  chat_id: string
  name: string
  chat_type: number
  count: number
  last_time: number
  last_sender: string
  last_direction: string
  last_content: string
  peer_id: string
  avatar: string
  agent_enabled: boolean
}

export interface Topic {
  anchor: string
  count: number
  last_time: number
  title: string
}

export interface Message {
  id: number
  msg_id: string
  time: number
  direction: string
  sender: string
  sender_id: string
  type: string
  content: string
  anchor: string
  agent: boolean
}

export interface Triggers {
  prefix: string
  chat_types: string[]
  include_chats: string[]
  exclude_chats: string[]
  include_senders: string[]
  exclude_senders: string[]
  keywords: string[]
  group_at_only: boolean
  dm_enabled: boolean
  self_chat_enabled: boolean
}

export interface Settings {
  remark: string
  autostart: boolean
  agent_backend: string
  agent_model: string
  workdir: string
  agent_timeout: number
  system_prompt: string
  context_scope: string
  mark_read: boolean
  reply_in_topic: boolean
  reply_mode: string
  reply_signature: string
  ack_reaction: boolean
  deny_reply: string
  memory_enabled: boolean
  memory_review_at: string
  triggers: Triggers
}

export interface Person {
  id: string
  name: string
  desc: string
  avatar: string
}

export interface MemoryData {
  entries: string[]
  used: number
  limit: number
  last_review: string
}

export interface Task {
  id: number
  kind: 'once' | 'daily'
  when: string
  next_run: number
  chat_id: string
  chat: string
  anchor: string
  content: string
  created_by: string
}

export interface LoginSnapshot {
  state: 'idle' | 'starting' | 'waiting' | 'scanned' | 'success' | 'failed'
  message: string
  qr: string
  attempt: number
  account_id: string
}

export interface LogLine {
  seq: number
  time: string
  level: string
  text: string
}

// ---------- 访问令牌: 换成 HttpOnly cookie,之后的请求都靠 cookie,令牌不出现在网址里 ----------
/** 用访问令牌换 cookie。令牌不对时抛错。 */
export async function login(token: string): Promise<void> {
  const res = await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }) })
  if (!res.ok) throw new Error(res.status === 401 ? '访问令牌不对' : `${res.status} ${res.statusText}`)
}

// lark web 打印的链接带 #token=(旧版是 ?token=):取出来换 cookie,地址栏里抹掉
const linkToken = new URLSearchParams(location.hash.slice(1)).get('token') || new URLSearchParams(location.search).get('token')
if (linkToken) history.replaceState(null, '', location.pathname)
// 第一批请求等 cookie 换好再发,免得先弹出令牌输入框
const ready: Promise<unknown> = linkToken ? login(linkToken).catch(() => undefined) : Promise.resolve()

export class TokenRequired extends Error {}

let onTokenRequired: () => void = () => {}
export function onUnauthorized(fn: () => void) {
  onTokenRequired = fn
}

function errorText(data: unknown, res: Response): string {
  const d = (data as { detail?: unknown } | null)?.detail
  if (Array.isArray(d)) return d.map((e: { loc?: unknown[]; msg?: string }) => `${(e.loc || []).slice(1).join('.')}: ${e.msg}`).join('; ')
  return typeof d === 'string' ? d : `${res.status} ${res.statusText}`
}

export async function api<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
  await ready
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch('/api' + path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined })
  let data: unknown = null
  try {
    data = await res.json()
  } catch {
    /* 空响应 */
  }
  if (res.status === 401) {
    onTokenRequired()
    throw new TokenRequired('需要访问令牌')
  }
  if (!res.ok) throw new Error(errorText(data, res))
  return data as T
}

export const enc = encodeURIComponent
