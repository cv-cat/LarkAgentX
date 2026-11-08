import asyncio
import time
from datetime import datetime
from xml.sax.saxutils import escape, quoteattr

from loguru import logger

from .. import accounts, memory

INSTRUCTIONS = '以上是飞书会话里新到的一条消息(XML 里有会话/发送者/内容)。你是这个数字人,完整对话历史你都有。如果对方也是机器人且只是互相客套寒暄,直接结束不要再接话。'
OUTPUT_RULES = '不需要回复就直接结束,不要解释、不要复述消息。'
# 发送选项,写给 agent 看。撤回、转发、@ 只在明确要求时用
SEND_HELP = ('lark send 的其他用法: -m 按 markdown 发(代码块、列表、加粗、链接);--mention 用户id:名字 真正 @ 某人(可重复,'
             '正文里写到的「@名字」会变成 @);--image 路径 / --file 路径 发图片或文件。lark recall 消息id 撤回自己发的消息;'
             'lark forward 消息id... --to 会话id [--merge] 转发。lark task add --in 30m / --at "2026-01-02 09:00" / --daily 09:00 "要做的事" '
             '安排定时任务(到点后在当前会话里交给你处理),lark task 查看,lark task rm 编号 删除。')
# 太久以前的消息(重启后排队里剩下的、补收回来的)只入库不回复,免得回复几个小时前的事
STALE_SECONDS = 600
REVIEW_KEY = 'memory-review'


def _ts(msg: dict) -> str:
    t = msg.get('create_time')
    if not t:
        return ''
    try:
        return datetime.fromtimestamp(int(t)).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(t)


def build_xml_message(m: dict) -> str:
    lines = ['<message>']
    lines.append(f'  <chat id={quoteattr(str(m.get("chat_id")))} name={quoteattr(str(m.get("_chat_name") or ""))} type={quoteattr(str(m.get("chat_type_name") or ""))} anchor={quoteattr(str(m.get("anchor") or ""))}/>')
    lines.append(f'  <sender id={quoteattr(str(m.get("from_id")))} name={quoteattr(str(m.get("_sender_name") or ""))}/>')
    if m.get('msg_id'):
        lines.append(f'  <msg_id>{escape(str(m["msg_id"]))}</msg_id>')
    if m.get('at_me'):
        lines.append('  <at_me>true</at_me>')
    lines.append(f'  <time>{escape(_ts(m))}</time>')
    lines.append(f'  <content>{escape(str(m.get("content") or ""))}</content>')
    lines.append('</message>')
    return '\n'.join(lines)


def is_stale(msg: dict, now: float = None) -> bool:
    try:
        return (now or time.time()) - int(msg.get('create_time') or 0) > STALE_SECONDS
    except (TypeError, ValueError):
        return False


class SessionWorker:
    def __init__(self, dispatcher, session_key: str):
        self.dispatcher = dispatcher
        self.session_key = session_key
        self.queue = asyncio.Queue()
        self.busy = False
        self.current = None
        self._interrupted = False
        self.task = asyncio.create_task(self._run())

    async def _run(self):
        while True:
            pending_id, msg = await self.queue.get()
            self.busy, self._interrupted = True, False
            self.current = asyncio.ensure_future(self.dispatcher.handle_message(self.session_key, msg))
            try:
                await self.current
            except asyncio.CancelledError:
                if not self._interrupted:
                    raise          # 整个 worker 被取消(停账号),排队记录留着,下次启动接着处理
                self.dispatcher.log.info(f'已打断 [{self.session_key}] 正在处理的消息')
            except Exception as e:
                self.dispatcher.log.error(f'处理消息异常 [{self.session_key}]: {e}')
            self.busy, self.current = False, None
            self.dispatcher.forget(pending_id)

    def interrupt(self) -> bool:
        """打断正在跑的这条(agent 子进程会被杀掉)。"""
        if self.current and not self.current.done():
            self._interrupted = True
            self.current.cancel()
            return True
        return False


class AgentDispatcher:
    def __init__(self, backend, reply_fn, cfg: dict=None, account_id: str=None, storage=None):
        self.account_id = accounts.normalize(account_id)
        self.cfg = cfg if cfg is not None else accounts.get_settings(self.account_id)
        self.log = logger.bind(account=self.account_id)
        self.backend = backend
        self.reply_fn = reply_fn
        self.storage = storage
        self.workers = {}
        self.memory_seen = {}      # session_key -> 上次附上的记忆内容
        self.denied = None         # 名单外的人触发时的回调(由 Listener 设置)
        self.accepted = None       # 消息交给 agent 时的回调(点 👌)

    def session_key_of(self, msg: dict) -> str:
        scope = self.cfg['context_scope']
        if scope == 'global':
            return 'global'
        if scope == 'chat':
            return str(msg.get('chat_id'))
        return f"{msg.get('chat_id')}:{msg.get('anchor') or ''}"

    def should_handle(self, msg: dict, my_user_id: str, self_chat: bool=False) -> bool:
        return self.check(msg, my_user_id, self_chat) == 'ok'

    def check(self, msg: dict, my_user_id: str, self_chat: bool=False) -> str:
        """'ok' 交给 agent;'denied' 本该触发但发送者不在「只处理这些发送者」名单里;其他情况返回 'skip'。
        self_chat: 用户在「和自己的会话」里亲手发的,这是他自己开的入口,不看会话类型和名单,只看前缀/关键词/排除。"""
        if str(msg.get('from_id')) == str(my_user_id) and not self_chat:
            return 'skip'
        t = self.cfg.get('triggers') or {}
        content = (msg.get('content') or '').strip()
        chat_id = str(msg.get('chat_id'))
        sender_id = str(msg.get('from_id'))
        type_name = {1: 'p2p', 2: 'group', 3: 'topic_group'}.get(msg.get('chat_type'), '')
        if t.get('prefix') and (not content.startswith(t['prefix'])):
            return 'skip'
        if type_name == 'p2p' and not self_chat and t.get('dm_enabled', True) is False:
            return 'skip'
        chat_types = t.get('chat_types') or []
        if chat_types and type_name not in chat_types and not self_chat:
            return 'skip'
        include = [str(x) for x in t.get('include_chats') or []]
        if include and chat_id not in include and not self_chat:
            return 'skip'
        exclude = [str(x) for x in t.get('exclude_chats') or []]
        if exclude and chat_id in exclude:
            return 'skip'
        blocked = [str(x) for x in t.get('exclude_senders') or []]
        if blocked and sender_id in blocked:
            return 'skip'
        keywords = t.get('keywords') or []
        if keywords and (not any((kw in content for kw in keywords))):
            return 'skip'
        if t.get('group_at_only') and type_name in ('group', 'topic_group') and (not msg.get('at_me')):
            return 'skip'
        senders = [str(x) for x in t.get('include_senders') or []]
        if senders and sender_id not in senders and not self_chat:
            return 'denied'
        return 'ok'

    async def submit(self, msg: dict, chat_name: str='', sender_name: str='', my_user_id: str='', self_chat: bool=False):
        is_owner = str(msg.get('from_id')) == str(my_user_id)
        cmd, remainder = self._parse_command(msg.get('content') or '')
        if cmd and is_owner and (remainder == '' or self_chat):
            # 你本人在任何会话里发的 /stop、/clear 都管用;带后续内容的写法只在「和自己的会话」里认
            await self._run_command(cmd, remainder, msg, chat_name, sender_name)
            return
        verdict = self.check(msg, my_user_id, self_chat)
        if verdict == 'denied':
            if self.denied and self.cfg.get('deny_reply'):
                await self.denied(msg)
            return
        if verdict != 'ok':
            return
        if cmd and not is_owner:
            return             # 别人发的 /stop、/clear 不当命令,也不交给 agent
        if self.accepted:
            self.accepted(msg)
        await self._enqueue(msg, chat_name, sender_name)

    async def _run_command(self, cmd, remainder, msg, chat_name, sender_name):
        key = self.session_key_of(msg)
        chat_id = str(msg['chat_id'])
        root_id = (msg.get('anchor') or '') or None
        n = self._drain_queue(key)
        if cmd == 'clear':
            self.backend.reset_session(key)
            self.memory_seen.pop(key, None)
        stopped = self._interrupt(key)
        if remainder:
            await self._enqueue({**msg, 'content': remainder}, chat_name, sender_name)
            return
        if cmd == 'clear':
            await self.reply_fn(chat_id, '✅ 已开启新会话', root_id)
        else:
            parts = (['已打断正在处理的消息'] if stopped else []) + ([f'清空了 {n} 条排队消息'] if n else [])
            await self.reply_fn(chat_id, '⏹ ' + ('，'.join(parts) if parts else '没有正在处理的消息'), root_id)

    async def _enqueue(self, msg: dict, chat_name: str='', sender_name: str='', key: str=None):
        msg = dict(msg)
        msg['_chat_name'] = chat_name or msg.get('_chat_name', '')
        msg['_sender_name'] = sender_name or msg.get('_sender_name', '')
        key = key or self.session_key_of(msg)
        pending_id = self.storage.pending_add(key, msg) if self.storage else None
        if key not in self.workers:
            self.workers[key] = SessionWorker(self, key)
        await self.workers[key].queue.put((pending_id, msg))

    async def enqueue_task(self, task):
        """定时任务到点:当成一条消息交给创建它的那个会话。"""
        msg = {'_task': task.content, 'chat_id': task.chat_id, 'anchor': task.anchor, 'scope': 'topic' if task.anchor else 'chat',
               'create_time': int(time.time())}
        await self._enqueue(msg, key=self.session_key_of(msg))

    async def enqueue_review(self, transcript: str) -> bool:
        """每日回顾:单独的会话,不和任何聊天混在一起,每次都从新会话开始,不会一天天越堆越长。
        上一次还在排队或进行中时不再重复,返回 False。"""
        w = self.workers.get(REVIEW_KEY)
        if w and (w.busy or not w.queue.empty()):
            return False
        self.backend.reset_session(REVIEW_KEY)
        await self._enqueue({'_review': transcript, 'chat_id': '', 'create_time': int(time.time())}, key=REVIEW_KEY)
        return True

    async def restore(self):
        """重启后接着处理上次没处理完的消息;太久以前的只记一笔日志,不回复。"""
        if not self.storage:
            return
        stale = 0
        for pending_id, key, msg, created in self.storage.pending_all():
            self.storage.pending_done(pending_id)
            if time.time() - (created or 0) > STALE_SECONDS:
                stale += 1
                continue
            await self._enqueue(msg, key=key)
        if stale:
            self.log.info(f'上次停止时还有 {stale} 条消息没处理,已超过 {STALE_SECONDS // 60} 分钟,不再回复')

    def forget(self, pending_id):
        if self.storage and pending_id:
            try:
                self.storage.pending_done(pending_id)
            except Exception as e:
                self.log.debug(f'删除已处理的排队记录失败: {e}')

    def reply_flags(self, msg: dict) -> str:
        """agent 回复这条消息时 lark send 要带的参数。
        话题里的消息: 默认回到话题(--root),可改成发到外面的主会话。
        主会话的消息: 默认直接发,可改成引用原消息(--quote)或开话题回复(--root)。"""
        anchor = msg.get('anchor') or ''
        if anchor:
            return f' --root {anchor}' if self.cfg.get('reply_in_topic', True) else ''
        mode = self.cfg.get('reply_mode') or 'direct'
        msg_id = str(msg.get('msg_id') or '')
        if not msg_id or mode == 'direct':
            return ''
        # 私聊没有话题,开话题回复退回引用
        if mode == 'thread' and msg.get('chat_type') != 1:
            return f' --root {msg_id}'
        return f' --quote {msg_id}'

    def stats(self) -> dict:
        workers = list(self.workers.values())
        return {'busy': sum(1 for w in workers if w.busy), 'queued': sum(w.queue.qsize() for w in workers)}

    def clear_session(self, session_key: str) -> int:
        """清排队 + 打断正在跑的 + 换新 agent 会话(和 /clear 一样)。返回清掉的排队条数。"""
        n = self._drain_queue(session_key)
        self._interrupt(session_key)
        self.backend.reset_session(session_key)
        self.memory_seen.pop(session_key, None)
        return n

    def _parse_command(self, content: str):
        t = self.cfg.get('triggers') or {}
        prefix = t.get('prefix') or ''
        c = content.strip()
        if prefix and c.startswith(prefix):
            c = c[len(prefix):].lstrip()
        for cmd in ('/clear', '/stop'):
            if c == cmd:
                return cmd[1:], ''
            if c.startswith(cmd) and len(c) > len(cmd) and (c[len(cmd)] in (' ', '\t', '\n')):
                return cmd[1:], c[len(cmd):].strip()
        return None, None

    def _drain_queue(self, key) -> int:
        w = self.workers.get(key)
        if not w:
            return 0
        n = 0
        while True:
            try:
                pending_id, _ = w.queue.get_nowait()
            except asyncio.QueueEmpty:
                return n
            self.forget(pending_id)
            n += 1

    def _interrupt(self, key) -> bool:
        w = self.workers.get(key)
        return bool(w and w.interrupt())

    async def shutdown(self):
        """停账号时取消所有排队 worker(会顺带杀掉正在跑的 agent 子进程)。排队记录留着,下次启动接着处理。"""
        workers, self.workers = list(self.workers.values()), {}
        for w in workers:
            w.task.cancel()
        await asyncio.gather(*(w.task for w in workers), return_exceptions=True)

    def _account_flag(self) -> str:
        return '' if self.account_id == accounts.DEFAULT_ID else f' --account {self.account_id}'

    def _memory_prefix(self, session_key: str) -> str:
        """开了长期记忆时,这个会话第一次处理、或者记忆变了,才附上最新的记忆。"""
        if not self.cfg.get('memory_enabled'):
            return ''
        block = memory.prompt_block(self.account_id)
        if self.memory_seen.get(session_key) == block:
            return ''
        self.memory_seen[session_key] = block
        return block + '\n\n'

    def build_prompt(self, session_key: str, msg: dict) -> str:
        acct = self._account_flag()
        if msg.get('_review') is not None:
            return (memory.prompt_block(self.account_id) + '\n\n' + memory.REVIEW_PROMPT.format(acct=acct) + '\n\n<chats>\n'
                    + msg['_review'] + '\n</chats>')
        chat_id = str(msg['chat_id'])
        if msg.get('_task') is not None:
            body = f'<task>\n  <chat id={quoteattr(chat_id)} anchor={quoteattr(str(msg.get("anchor") or ""))}/>\n  <content>{escape(msg["_task"])}</content>\n</task>'
            lead = '以上是你之前安排的定时任务,现在到点了,请执行。'
        else:
            body = build_xml_message(msg)
            lead = self.cfg.get('system_prompt') or INSTRUCTIONS
        reply_cmd = f'lark send {chat_id} "<回复内容>"' + self.reply_flags(msg) + acct
        rules = f'要回复就执行: {reply_cmd}\n' + OUTPUT_RULES + '\n' + SEND_HELP
        return self._memory_prefix(session_key) + body + '\n\n' + lead + '\n' + rules

    async def handle_message(self, session_key: str, msg: dict):
        prompt = self.build_prompt(session_key, msg)
        try:
            out = await self.backend.run(session_key, prompt, chat_id=str(msg.get('chat_id') or ''), anchor=(msg.get('anchor') or ''))
        finally:
            # 第一轮没跑成功时会话还没建立(下次会换一个新会话),记忆下次要重新附上
            if not self.backend.session_started(session_key):
                self.memory_seen.pop(session_key, None)
        if out:
            self.log.debug(f'[{session_key}] agent 输出: {out[:200]}')
