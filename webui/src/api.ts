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
  triggers: Triggers
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

// ---------- 访问令牌: 从 ?token= 取一次,存 sessionStorage,地址栏里抹掉 ----------
const TOKEN_KEY = 'larkx_token'
let token = sessionStorage.getItem(TOKEN_KEY) || ''
const fromUrl = new URLSearchParams(location.search).get('token')
if (fromUrl) {
  token = fromUrl
  sessionStorage.setItem(TOKEN_KEY, token)
  history.replaceState(null, '', location.pathname + location.hash)
}

export function setToken(t: string) {
  token = t
  sessionStorage.setItem(TOKEN_KEY, t)
}

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
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = 'Bearer ' + token
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

/** <img> 带不了请求头,配了令牌时走 query */
export function withToken(url: string): string {
  // 只有接口要令牌;打包进来的静态图(可能是 data: 地址)原样返回
  if (!url || !token || !url.startsWith('/api/')) return url
  return url + (url.includes('?') ? '&' : '?') + 'token=' + enc(token)
}
