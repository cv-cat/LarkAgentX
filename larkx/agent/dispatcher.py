import asyncio
from datetime import datetime
from xml.sax.saxutils import escape, quoteattr

from loguru import logger

from .. import accounts

INSTRUCTIONS = '以上是飞书会话里新到的一条消息(XML 里有会话/发送者/内容)。你是这个数字人,完整对话历史你都有。如果对方也是机器人且只是互相客套寒暄,直接结束不要再接话。'
OUTPUT_RULES = '不需要回复就直接结束,不要解释、不要复述消息。'


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
    if m.get('at_me'):
        lines.append('  <at_me>true</at_me>')
    lines.append(f'  <time>{escape(_ts(m))}</time>')
    lines.append(f'  <content>{escape(str(m.get("content") or ""))}</content>')
    lines.append('</message>')
    return '\n'.join(lines)


class SessionWorker:
    def __init__(self, dispatcher, session_key: str):
        self.dispatcher = dispatcher
        self.session_key = session_key
        self.queue = asyncio.Queue()
        self.busy = False
        self.task = asyncio.create_task(self._run())

    async def _run(self):
        while True:
            msg = await self.queue.get()
            self.busy = True
            try:
                await self.dispatcher.handle_message(self.session_key, msg)
            except Exception as e:
                self.dispatcher.log.error(f'处理消息异常 [{self.session_key}]: {e}')
            finally:
                self.busy = False


class AgentDispatcher:
    def __init__(self, backend, reply_fn, cfg: dict=None, account_id: str=None):
        self.account_id = accounts.normalize(account_id)
        self.cfg = cfg if cfg is not None else accounts.get_settings(self.account_id)
        self.log = logger.bind(account=self.account_id)
        self.backend = backend
        self.reply_fn = reply_fn
        self.workers = {}

    def session_key_of(self, msg: dict) -> str:
        scope = self.cfg['context_scope']
        if scope == 'global':
            return 'global'
        if scope == 'chat':
            return str(msg.get('chat_id'))
        return f"{msg.get('chat_id')}:{msg.get('anchor') or ''}"

    def should_handle(self, msg: dict, my_user_id: str, self_chat: bool=False) -> bool:
        """self_chat: 用户在「和自己的会话」里亲手发的,这是他自己开的入口,不看会话类型和名单,只看前缀/关键词/排除。"""
        if str(msg.get('from_id')) == str(my_user_id) and not self_chat:
            return False
        t = self.cfg.get('triggers') or {}
        content = (msg.get('content') or '').strip()
        chat_id = str(msg.get('chat_id'))
        sender_id = str(msg.get('from_id'))
        type_name = {1: 'p2p', 2: 'group', 3: 'topic_group'}.get(msg.get('chat_type'), '')
        if t.get('prefix') and (not content.startswith(t['prefix'])):
            return False
        if type_name == 'p2p' and not self_chat and t.get('dm_enabled', True) is False:
            return False
        chat_types = t.get('chat_types') or []
        if chat_types and type_name not in chat_types and not self_chat:
            return False
        include = [str(x) for x in t.get('include_chats') or []]
        if include and chat_id not in include and not self_chat:
            return False
        exclude = [str(x) for x in t.get('exclude_chats') or []]
        if exclude and chat_id in exclude:
            return False
        senders = [str(x) for x in t.get('include_senders') or []]
        if senders and sender_id not in senders and not self_chat:
            return False
        blocked = [str(x) for x in t.get('exclude_senders') or []]
        if blocked and sender_id in blocked:
            return False
        keywords = t.get('keywords') or []
        if keywords and (not any((kw in content for kw in keywords))):
            return False
        if t.get('group_at_only') and type_name in ('group', 'topic_group') and (not msg.get('at_me')):
            return False
        return True

    async def submit(self, msg: dict, chat_name: str='', sender_name: str='', my_user_id: str='', self_chat: bool=False):
        if not self.should_handle(msg, my_user_id, self_chat):
            return
        cmd, remainder = self._parse_command(msg.get('content') or '')
        key = self.session_key_of(msg)
        chat_id = str(msg['chat_id'])
        root_id = (msg.get('anchor') or '') or None
        if cmd == 'clear':
            self._drain_queue(key)
            self.backend.reset_session(key)
            if not remainder:
                await self.reply_fn(chat_id, '✅ 已开启新会话', root_id)
                return
        elif cmd == 'stop':
            n = self._drain_queue(key)
            if not remainder:
                await self.reply_fn(chat_id, f'⏹ 已清空 {n} 条排队消息' if n else '⏹ 队列已清空', root_id)
                return
        msg = dict(msg)
        if cmd:
            msg['content'] = remainder
        msg['_chat_name'] = chat_name
        msg['_sender_name'] = sender_name
        if key not in self.workers:
            self.workers[key] = SessionWorker(self, key)
        await self.workers[key].queue.put(msg)

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
        """清排队 + 换新 agent 会话(和 /clear 一样)。返回清掉的排队条数。"""
        n = self._drain_queue(session_key)
        self.backend.reset_session(session_key)
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
                w.queue.get_nowait()
                n += 1
            except asyncio.QueueEmpty:
                return n

    async def shutdown(self):
        """停账号时取消所有排队 worker(会顺带杀掉正在跑的 agent 子进程)。"""
        workers, self.workers = list(self.workers.values()), {}
        for w in workers:
            w.task.cancel()
        await asyncio.gather(*(w.task for w in workers), return_exceptions=True)

    async def handle_message(self, session_key: str, msg: dict):
        body = build_xml_message(msg)
        chat_id = str(msg['chat_id'])
        reply_cmd = f'lark send {chat_id} "<回复内容>"' + self.reply_flags(msg)
        if self.account_id != accounts.DEFAULT_ID:
            # 多账号: agent 里的 lark send 必须明确用哪个账号发,不能靠环境变量(agent 的 shell 不一定继承)
            reply_cmd += f' --account {self.account_id}'
        rules = f'要回复就执行: {reply_cmd}\n' + OUTPUT_RULES
        if self.cfg.get('system_prompt'):
            instructions = self.cfg['system_prompt'] + '\n' + rules
        else:
            instructions = INSTRUCTIONS + '\n' + rules
        prompt = body + '\n\n' + instructions
        out = await self.backend.run(session_key, prompt, chat_id=chat_id, anchor=(msg.get('anchor') or ''))
        if out:
            self.log.debug(f'[{session_key}] agent 输出: {out[:200]}')
