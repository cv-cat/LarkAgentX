import { ArrowRight, ChevronRight, Trash2, X } from 'lucide-react'
import { type KeyboardEvent, type ReactNode, useEffect, useState } from 'react'
import { type Account, type Person, type Runtime, type Settings, type Triggers, api, enc } from '../api'
import { Link, navigate } from '../router'
import { useConsole } from '../store'
import { AccountAvatar, Avatar, Button, Card, Confirm, Field, Input, Seg, SwitchRow, TagInput, Textarea, attempt, cn, toast } from '../ui'
import { deleteHint } from './Accounts'

const SECTIONS = [
  { id: 'account', label: '账号' },
  { id: 'agent', label: 'Agent' },
  { id: 'reply', label: '回复方式' },
  { id: 'triggers', label: '触发规则' },
  { id: 'memory', label: '长期记忆' },
  { id: 'danger', label: '危险操作' },
]

/** 名单里的人: 按名字搜索添加,显示头像和名字;也可以直接粘贴 user_id 回车 */
function PeopleInput({ accountId, value, onChange }: { accountId: string; value: string[]; onChange: (v: string[]) => void }) {
  const [names, setNames] = useState<Record<string, Person>>({})
  const [q, setQ] = useState('')
  const [results, setResults] = useState<Person[] | null>(null)
  const [busy, setBusy] = useState(false)
  const base = `/accounts/${enc(accountId)}/people`
  const remember = (ps: Person[]) => setNames((cur) => ({ ...cur, ...Object.fromEntries(ps.map((p) => [p.id, p])) }))

  useEffect(() => {
    const missing = value.filter((id) => !names[id])
    if (missing.length) api<Person[]>('GET', `${base}?ids=${enc(missing.join(','))}`).then(remember).catch(() => undefined)
  }, [value.join(','), base])

  useEffect(() => {
    const text = q.trim()
    if (!text || /^\d+$/.test(text)) {
      setResults(null)
      return
    }
    const t = setTimeout(() => {
      setBusy(true)
      api<Person[]>('GET', `${base}?q=${enc(text)}`)
        .then(setResults)
        .catch((e: Error) => {
          setResults([])
          toast(e.message, true)
        })
        .finally(() => setBusy(false))
    }, 300)
    return () => clearTimeout(t)
  }, [q, base])

  const add = (p: Person) => {
    remember([p])
    if (!value.includes(p.id)) onChange([...value, p.id])
    setQ('')
    setResults(null)
  }
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.nativeEvent.isComposing) return
    const text = q.trim()
    if (e.key === 'Enter') {
      e.preventDefault()
      if (/^\d+$/.test(text)) add({ id: text, name: '', desc: '', avatar: '' })
      else if (results?.length) add(results[0]!)
    } else if (e.key === 'Backspace' && !q && value.length) {
      onChange(value.slice(0, -1))
    } else if (e.key === 'Escape') {
      setResults(null)
    }
  }

  return (
    <div className="relative">
      <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-sm bg-fill-2 px-2 py-1.5 ring-1 ring-transparent ring-inset transition-shadow focus-within:bg-transparent focus-within:ring-accent-ring">
        {value.map((id) => {
          const name = names[id]?.name || id
          return (
            <span key={id} title={`user_id ${id}`} className="inline-flex h-6 items-center gap-1 rounded-full bg-surface-3 pr-1 pl-0.5 text-caption shadow-raised dark:bg-fill-3">
              <Avatar src={`/api/accounts/${enc(accountId)}/avatars/user/${id}`} name={name} size="xs" />
              <span className="max-w-32 truncate">{name}</span>
              <button type="button" aria-label={`移除 ${name}`} className="press grid size-4 place-items-center rounded-full text-fg-3 hover:bg-fill-3 hover:text-fg-1" onClick={() => onChange(value.filter((x) => x !== id))}>
                <X className="size-3" />
              </button>
            </span>
          )
        })}
        <input
          value={q}
          autoComplete="off"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKey}
          onBlur={() => setResults(null)}
          placeholder={value.length ? '' : '输入名字搜索'}
          className="h-6 min-w-24 flex-1 bg-transparent px-1 text-small outline-none placeholder:text-fg-4"
        />
      </div>
      {results !== null && (
        <div className="menu-panel absolute inset-x-0 top-full z-20 mt-1 max-h-64 overflow-y-auto rounded-md p-1">
          {results.length ? results.map((p) => (
            <button
              key={p.id}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => add(p)}
              className="flex w-full items-center gap-2.5 rounded-sm px-2 py-1.5 text-left text-small hover:bg-fill-2"
            >
              <Avatar src={p.avatar} name={p.name} size="sm" />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{p.name || p.id}</span>
                <span className="block truncate text-caption text-fg-3">{[p.desc, p.id].filter(Boolean).join(' · ')}</span>
              </span>
            </button>
          )) : <div className="px-2 py-2 text-small text-fg-3">{busy ? '正在搜索…' : '没有找到'}</div>}
        </div>
      )}
    </div>
  )
}

function Section({ id, title, note, children }: { id: string; title: string; note?: string; children: ReactNode }) {
  return (
    <section id={`s-${id}`} className="scroll-mt-6">
      <h2 className="text-lead font-medium">{title}</h2>
      {note && <p className="mb-3 text-small text-fg-3">{note}</p>}
      {!note && <div className="mb-3" />}
      {children}
    </section>
  )
}

export function SettingsPage({ account: a }: { account: Account }) {
  const { meta, refresh } = useConsole()
  const [saved, setSaved] = useState<Settings | null>(null)
  const [s, setS] = useState<Settings | null>(null)
  const [runtimes, setRuntimes] = useState<Runtime[]>([])
  const [active, setActive] = useState('account')
  const [more, setMore] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    void attempt(async () => {
      const v = await api<Settings>('GET', `/accounts/${enc(a.id)}/settings`)
      setSaved(v)
      setS(v)
      const t = v.triggers
      setMore([t.chat_types, t.include_chats, t.exclude_chats, t.include_senders, t.exclude_senders].some((x) => x.length > 0))
    })
    api<Runtime[]>('GET', '/runtimes').then(setRuntimes).catch(() => {})
  }, [a.id])

  if (!s || !saved) return <div className="h-full" />
  const dirty = JSON.stringify(s) !== JSON.stringify(saved)
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setS({ ...s, [k]: v })
  const trig = <K extends keyof Triggers>(k: K, v: Triggers[K]) => setS({ ...s, triggers: { ...s.triggers, [k]: v } })

  const save = () => attempt(async () => {
    setSaving(true)
    try {
      const r = await api<{ applied: boolean }>('PUT', `/accounts/${enc(a.id)}/settings`, s)
      setSaved(s)
      await refresh()
      toast(r.applied ? '已保存，对运行中的账号立即生效' : '已保存')
    } finally {
      setSaving(false)
    }
  })

  const onScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const top = e.currentTarget.getBoundingClientRect().top
    let cur = SECTIONS[0]!.id
    for (const x of SECTIONS) {
      const el = document.getElementById(`s-${x.id}`)
      if (el && el.getBoundingClientRect().top - top < 90) cur = x.id
    }
    setActive(cur)
  }
  const toggleType = (v: string) => {
    const has = s.triggers.chat_types.includes(v)
    trig('chat_types', has ? s.triggers.chat_types.filter((x) => x !== v) : [...s.triggers.chat_types, v])
  }

  return (
    <div className="page-scroll h-full" onScroll={onScroll}>
      <div className="fade-in mx-auto grid w-full max-w-[960px] gap-8 px-6 py-8 md:grid-cols-[160px_minmax(0,1fr)]">
        <nav className="flex gap-1 overflow-x-auto md:sticky md:top-8 md:flex-col md:self-start">
          {SECTIONS.map((x) => (
            <button
              key={x.id}
              type="button"
              onClick={() => document.getElementById(`s-${x.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
              className={cn('press h-8 shrink-0 rounded-full px-3 text-left text-small', active === x.id ? 'bg-fill-2 font-medium text-fg-1' : 'text-fg-3 hover:text-fg-1')}
            >
              {x.label}
            </button>
          ))}
        </nav>

        <form className="flex min-w-0 flex-col gap-8 pb-16" onSubmit={(e) => { e.preventDefault(); void save() }}>
          <Section id="account" title="账号" note="姓名、头像和公司信息来自飞书。">
            <Card className="p-5">
              <div className="flex items-center gap-3">
                <AccountAvatar account={a} size="lg" />
                <div className="min-w-0">
                  <div className="truncate text-body font-medium">{a.name}</div>
                  <div className="truncate text-caption text-fg-3">{[a.company, a.region_label, a.user_id && `ID ${a.user_id}`].filter(Boolean).join(' · ') || '还没有登录'}</div>
                </div>
              </div>
              <Field label="备注名（可选）" hint="仅在控制台中显示，留空时使用飞书姓名。" className="mt-4">
                <Input value={s.remark} maxLength={40} onChange={(e) => set('remark', e.target.value)} placeholder="例如：工作号" />
              </Field>
              <div className="mt-2 border-t border-line-1">
                <SwitchRow title="随控制台自动启动" hint="运行 lark web 时自动开始接收消息。" checked={s.autostart} onChange={(v) => set('autostart', v)} />
              </div>
            </Card>
          </Section>

          <Section id="agent" title="Agent" note="选择处理消息的 Agent。保存后立即生效，无需重启。">
            <Card className="flex flex-col gap-5 p-5">
              <div className="grid gap-2 sm:grid-cols-3">
                {(meta?.backends ?? []).map((b) => {
                  const rt = runtimes.find((r) => r.id === b.id)
                  return (
                    <button
                      key={b.id}
                      type="button"
                      disabled={!b.installed}
                      onClick={() => set('agent_backend', b.id)}
                      className={cn(
                        'press rounded-sm p-3 text-left ring-1 ring-inset disabled:opacity-50',
                        s.agent_backend === b.id ? 'bg-accent-soft ring-accent' : 'bg-fill-1 ring-line-1 hover:bg-fill-2',
                      )}
                    >
                      <div className="truncate text-small font-medium">{b.id === 'none' ? '不接入 Agent' : b.label}</div>
                      <div className="truncate text-caption text-fg-3">{b.id === 'none' ? '仅接收并保存消息' : !b.installed ? '未在 PATH 中找到' : rt?.version || '已安装'}</div>
                    </button>
                  )
                })}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="模型（可选）"><Input value={s.agent_model} onChange={(e) => set('agent_model', e.target.value)} placeholder="留空用 CLI 默认" /></Field>
                <Field label="单次超时（可选）" hint="超过这个时间还没处理完，就结束这次处理。留空表示不限。">
                  <div className="relative">
                    <Input type="number" min={0} max={86400} value={s.agent_timeout || ''} onChange={(e) => set('agent_timeout', parseInt(e.target.value, 10) || 0)} placeholder="不限" className="pr-8" />
                    <span className="absolute top-1/2 right-3 -translate-y-1/2 text-caption text-fg-3">秒</span>
                  </div>
                </Field>
              </div>
              <Field label="工作目录（可选）" hint="Agent 在此目录下运行，可读写其中的文件。">
                <Input value={s.workdir} onChange={(e) => set('workdir', e.target.value)} placeholder="留空用控制台所在目录" className="font-mono text-small" />
              </Field>
              <Field label="系统提示词（可选）">
                <Textarea value={s.system_prompt} onChange={(e) => set('system_prompt', e.target.value)} placeholder="留空用内置默认" />
              </Field>
              <div>
                <div className="mb-1.5 text-small font-medium">上下文边界</div>
                <Seg
                  value={s.context_scope}
                  onChange={(v) => set('context_scope', v)}
                  options={[{ value: 'anchor', label: '会话 + 话题' }, { value: 'chat', label: '会话' }, { value: 'global', label: '全局共享' }]}
                />
                <p className="mt-1.5 text-caption text-fg-3">决定哪些消息共用同一个 Agent 上下文。</p>
              </div>
              <p className="rounded-sm bg-warning-soft px-3 py-2 text-caption text-warning">
                Claude Code 和 Codex 都以免确认模式运行，可在本机执行任意命令，请只对信任的会话开启。
              </p>
            </Card>
          </Section>

          <Section id="reply" title="回复方式" note="设置需要处理的消息范围，以及回复的发送位置。">
            <Card className="px-5 py-2">
              <div className="divide-y divide-line-1">
                <SwitchRow title="处理私聊消息" checked={s.triggers.dm_enabled} onChange={(v) => trig('dm_enabled', v)} />
                <SwitchRow
                  title="处理「和自己的会话」"
                  hint="开启后，发给自己的消息也会交给 Agent 处理，可以在手机上发送指令。"
                  checked={s.triggers.self_chat_enabled}
                  onChange={(v) => trig('self_chat_enabled', v)}
                />
                <SwitchRow title="群聊中只处理 @我 的消息" checked={s.triggers.group_at_only} onChange={(v) => trig('group_at_only', v)} />
                <SwitchRow title="处理后标记已读" hint="同步清除手机端的未读角标。" checked={s.mark_read} onChange={(v) => set('mark_read', v)} />
                <SwitchRow
                  title="收到消息先点个 👌"
                  hint="交给 Agent 处理的消息会先加一个 OK 表情。对方会看到这条消息已读，撤掉表情也不会恢复成未读。"
                  checked={s.ack_reaction}
                  onChange={(v) => set('ack_reaction', v)}
                />
                <div className="py-3">
                  <Field label="回复署名（可选）" hint="加在 Agent 发出的每条消息末尾。你自己发的消息不加。">
                    <Input value={s.reply_signature} maxLength={100} onChange={(e) => set('reply_signature', e.target.value)} placeholder="例如：—— 🤖 数字分身" />
                  </Field>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-3">
                  <div className="min-w-0">
                    <div className="text-body font-medium">话题内的消息</div>
                    <div className="text-caption text-fg-3">回复到该话题，或发送到主会话。</div>
                  </div>
                  <Seg
                    value={s.reply_in_topic ? 'in' : 'out'}
                    onChange={(v) => set('reply_in_topic', v === 'in')}
                    options={[{ value: 'in', label: '话题内' }, { value: 'out', label: '主会话' }]}
                  />
                </div>
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-3">
                  <div className="min-w-0">
                    <div className="text-body font-medium">主会话的消息</div>
                    <div className="text-caption text-fg-3">私聊不支持话题，选择「开话题回复」时按引用回复。</div>
                  </div>
                  <Seg
                    value={s.reply_mode}
                    onChange={(v) => set('reply_mode', v)}
                    options={[{ value: 'direct', label: '直接发送' }, { value: 'quote', label: '引用回复' }, { value: 'thread', label: '开话题回复' }]}
                  />
                </div>
              </div>
            </Card>
          </Section>

          <Section id="triggers" title="触发规则" note="留空则处理所有消息，多个条件需同时满足。你发给他人的消息不会触发。">
            <Card className="flex flex-col gap-4 p-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="前缀"><Input value={s.triggers.prefix} maxLength={64} onChange={(e) => trig('prefix', e.target.value)} placeholder="例如 /run" /></Field>
                <div className="flex flex-col gap-1.5">
                  <span className="text-small font-medium">关键词</span>
                  <TagInput value={s.triggers.keywords} onChange={(v) => trig('keywords', v)} placeholder="命中任一即可，回车添加" />
                </div>
              </div>
              <button type="button" className="flex items-center gap-1 self-start text-small text-fg-3 hover:text-fg-1" onClick={() => setMore(!more)}>
                <ChevronRight className={cn('size-3.5 transition-transform', more && 'rotate-90')} />
                更多条件
              </button>
              {more && (
                <div className="flex flex-col gap-4">
                  <div>
                    <div className="mb-1.5 text-small font-medium">只处理这些类型</div>
                    <div className="flex flex-wrap gap-1.5">
                      {[['p2p', '私聊'], ['group', '群聊'], ['topic_group', '话题群']].map(([v, l]) => (
                        <button key={v} type="button" onClick={() => toggleType(v!)} className={cn('press h-7 rounded-full px-3 text-small', s.triggers.chat_types.includes(v!) ? 'bg-invert text-invert-fg' : 'bg-fill-2 text-fg-2 hover:text-fg-1')}>
                          {l}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    {([['include_chats', '只处理这些会话 ID'], ['exclude_chats', '忽略这些会话 ID']] as const).map(([k, l]) => (
                      <div key={k} className="flex flex-col gap-1.5">
                        <span className="text-small font-medium">{l}</span>
                        <TagInput value={s.triggers[k]} onChange={(v) => trig(k, v)} />
                      </div>
                    ))}
                    {([['include_senders', '只处理这些发送者'], ['exclude_senders', '忽略这些发送者']] as const).map(([k, l]) => (
                      <div key={k} className="flex flex-col gap-1.5">
                        <span className="text-small font-medium">{l}</span>
                        <PeopleInput accountId={a.id} value={s.triggers[k]} onChange={(v) => trig(k, v)} />
                      </div>
                    ))}
                  </div>
                  {s.triggers.include_senders.length > 0 && (
                    <Field label="名单外的人触发时回复（可选）" hint="不在「只处理这些发送者」里的人触发 Agent 时，自动回这句话。留空则不回复。">
                      <Input value={s.deny_reply} maxLength={500} onChange={(e) => set('deny_reply', e.target.value)} placeholder="例如：抱歉，这个助手只为部分同事服务。" />
                    </Field>
                  )}
                  <p className="text-caption text-fg-3">单个会话的开关位于聊天记录页右上角，与此处名单同步。</p>
                </div>
              )}
            </Card>
          </Section>

          <Section id="memory" title="长期记忆" note="Agent 用 lark memory 记下长期有用的信息，比如人物、偏好和约定。所有会话共用，最多 2000 字。">
            <Card className="px-5 py-2">
              <div className="divide-y divide-line-1">
                <SwitchRow
                  title="开启长期记忆"
                  hint="开启后，交给 Agent 的消息会带上记忆。"
                  checked={s.memory_enabled}
                  onChange={(v) => set('memory_enabled', v)}
                />
                {s.memory_enabled && (
                  <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-body font-medium">每日回顾</div>
                      <div className="text-caption text-fg-3">到点后把最近 24 小时的聊天（最多 500 条）交给 Agent 整理记忆，聊天内容会发给模型。账号没在运行时跳过。留空则不回顾。</div>
                    </div>
                    <Input type="time" value={s.memory_review_at} onChange={(e) => set('memory_review_at', e.target.value)} className="w-32" />
                  </div>
                )}
                <div className="py-3">
                  <Link to={`/a/${enc(a.id)}/memory`} className="inline-flex items-center gap-1 text-small text-fg-3 no-underline hover:text-fg-1">
                    查看和修改记忆 <ArrowRight className="size-3.5" />
                  </Link>
                </div>
              </div>
            </Card>
          </Section>

          <Section id="danger" title="危险操作">
            <Card className="flex flex-wrap items-center gap-3 p-5">
              <div className="min-w-0 flex-1">
                <div className="text-body font-medium">删除这个账号</div>
                <div className="text-caption text-fg-3">{deleteHint(a)}</div>
              </div>
              <Button variant="danger" onClick={() => setRemoving(true)}><Trash2 />删除</Button>
            </Card>
          </Section>

          {dirty && (
            <div className="sticky bottom-4 z-10 flex justify-center">
              <div className="glass-panel pop-in flex items-center gap-3 rounded-full py-1.5 pr-1.5 pl-4">
                <span className="text-small text-fg-2">有未保存的改动</span>
                <Button size="sm" variant="ghost" onClick={() => setS(saved)}>放弃</Button>
                <Button size="sm" variant="primary" type="submit" disabled={saving}>保存</Button>
              </div>
            </div>
          )}
        </form>
      </div>
      <Confirm
        open={removing}
        onClose={() => setRemoving(false)}
        title={`删除「${a.name}」?`}
        body={deleteHint(a)}
        ok="删除"
        onOk={() => {
          setRemoving(false)
          void attempt(async () => {
            await api('DELETE', `/accounts/${enc(a.id)}`)
            await refresh()
            navigate('/console')
          })
        }}
      />
    </div>
  )
}
