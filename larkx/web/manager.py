"""web 进程里的账号运行时: 每个账号一个 Listener 任务 + 可选的一个扫码登录流程 + 一份内存日志。"""
import asyncio
import hashlib
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from datetime import datetime

from loguru import logger

from .. import accounts, memory, profile, tasks
from ..agent import get_backend
from ..agent.backend import BACKENDS, find_binary
from ..auth import AuthExpired, LarkAuth
from ..client import LarkClient
from ..listener import Listener
from ..region import REGIONS, get_region
from ..storage import Storage
from .login import LoginFlow


_ID = re.compile(r'[A-Za-z0-9_-]{1,64}')


def _plain(text) -> str:
    """搜索结果里的高亮标记去掉,只留文字。"""
    return re.sub(r'<[^>]*>', '', str(text or '')).strip()


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


class LogBuffer:
    """按账号分桶的环形日志。loguru sink 在任意线程调用,deque.append 是线程安全的。"""
    MAX = 400

    def __init__(self):
        self.buckets = {}
        self.seq = 0

    def sink(self, message):
        rec = message.record
        key = rec['extra'].get('account') or '_system'
        self.seq += 1
        self.buckets.setdefault(key, deque(maxlen=self.MAX)).append({
            'seq': self.seq,
            'time': rec['time'].strftime('%H:%M:%S'),
            'level': rec['level'].name,
            'text': rec['message'],
        })

    def get(self, account_id: str, since: int = 0) -> list:
        return [e for e in list(self.buckets.get(account_id, ())) if e['seq'] > since]

    def drop(self, account_id: str):
        self.buckets.pop(account_id, None)


class Manager:
    CLIENT_RETRY = 60       # 登录失效时,多久才再试着建一次客户端(头像请求是成批来的)
    AVATAR_RETRY = 600      # 取不到的头像多久才再试一次
    PROFILE_RETRY = 600

    def __init__(self):
        self.listeners = {}
        self.logins = {}
        self.storages = {}
        self.clients = {}
        self.logs = LogBuffer()
        self._client_lock = threading.Lock()
        self._client_fail = {}
        self._avatar_miss = {}
        self._profile_tried = {}
        self._runtime_cache = {}
        self._names = {}
        self._loop = None
        self._sink_id = logger.add(self.logs.sink, level='INFO', format='{message}')

    # ---------- 账号 ----------
    def require(self, account_id: str) -> str:
        try:
            account_id = accounts.normalize(account_id)
        except ValueError as e:
            raise NotFound(str(e))
        if not accounts.exists(account_id):
            raise NotFound(f'账号不存在: {account_id}')
        return account_id

    def storage(self, account_id: str) -> Storage:
        if account_id not in self.storages:
            self.storages[account_id] = Storage(account_id=account_id)
        return self.storages[account_id]

    def describe(self, account_id: str) -> dict:
        meta = accounts.read_meta(account_id)
        auth = LarkAuth(account_id)
        listener = self.listeners.get(account_id)
        login = self.logins.get(account_id)
        if listener is not None:
            state, error = listener.state, listener.error
        elif not auth.cookies:
            state, error = 'no_login', ''
        else:
            state, error = 'stopped', ''
        settings = accounts.get_settings(account_id)
        prof = meta.get('profile') or {}
        if auth.cookies:
            self._refresh_profile_soon(account_id, prof)
        return {
            'id': account_id,
            'name': accounts.display_name(account_id),
            'remark': meta.get('name') or '',
            'company': prof.get('company', ''),
            'avatar': f'/api/accounts/{account_id}/avatars/user/{auth.user_id}' if auth.user_id else '',
            'region': auth.region.name,
            'region_label': auth.region.label,
            'autostart': bool(meta.get('autostart')),
            'has_credentials': bool(auth.cookies),
            'user_id': auth.user_id,
            'saved_at': auth.saved_at,
            'state': state,
            'error': error,
            'backend': settings['agent_backend'],
            'memory': bool(settings['memory_enabled']),
            'queue': listener.stats() if listener else {'busy': 0, 'queued': 0},
            'login': login.snapshot() if login and not login.done else None,
        }

    def list(self) -> list:
        return [self.describe(i) for i in accounts.list_ids() if not accounts.read_meta(i).get('pending')]

    def create(self, name: str, region: str, pending: bool = False) -> dict:
        get_region(region)
        account_id = accounts.create(name, region)
        if pending:
            accounts.update_meta(account_id, pending=True)
        return self.describe(account_id)

    def add_by_qr(self, region: str) -> dict:
        """添加账号 = 直接开始扫码。账号先以「待定」存在,登录成功才转正;取消就连同目录删掉。"""
        acc = self.create('', region, pending=True)
        return {'account_id': acc['id'], **self.start_login(acc['id'], region)}

    def cancel_add(self, account_id: str):
        account_id = self.require(account_id)
        self.cancel_login(account_id)
        if accounts.read_meta(account_id).get('pending'):
            self._drop_files(account_id)

    def purge_pending(self):
        for account_id in accounts.list_ids():
            if accounts.read_meta(account_id).get('pending'):
                accounts.delete(account_id)

    def _on_login_success(self, flow: LoginFlow):
        """扫码成功(在登录线程里)。同一个人再次扫码不新增账号,否则两条连接会把同一条消息回复两次。"""
        account_id = flow.account_id
        auth = LarkAuth(account_id)
        same = next((a for a in accounts.list_ids() if a != account_id and LarkAuth(a).user_id == auth.user_id
                     and auth.user_id and not accounts.read_meta(a).get('pending')), None)
        if same and accounts.read_meta(account_id).get('pending'):
            shutil.copyfile(auth.path, LarkAuth(same).path)
            self._drop_files(account_id)
            flow.account_id = account_id = same
        else:
            accounts.update_meta(account_id, pending=False)
        self._after_login(account_id)
        self.refresh_profile(account_id, force=True)

    def _after_login(self, account_id: str):
        """新凭证生效: 清掉基于旧凭证的一切。否则账号会一直停在「需要重新登录」,头像也要等重试时间过了才取。
        账号是因为登录失效才停下的,就自动重新启动。"""
        listener = self.listeners.get(account_id)
        resume = bool(listener and listener.state == 'login_required')
        if listener and not listener.active:
            self.listeners.pop(account_id, None)
        client = self.clients.pop(account_id, None)
        if client:
            client.close()
        self._client_fail.pop(account_id, None)
        self._profile_tried.pop(account_id, None)
        for key in [k for k in self._avatar_miss if k[0] == account_id]:
            self._avatar_miss.pop(key, None)
        if resume and self._loop:
            asyncio.run_coroutine_threadsafe(self._resume(account_id), self._loop)

    async def _resume(self, account_id: str):
        # 扫码登录时,登录流程要等账号资料取完才算结束,结束前不能启动
        for _ in range(300):
            flow = self.logins.get(account_id)
            if not flow or flow.done:
                break
            await asyncio.sleep(0.1)
        log = logger.bind(account=account_id)
        try:
            await self.start(account_id)
            log.info('重新登录成功，已自动恢复运行')
        except Exception as e:
            log.warning(f'重新登录后没能自动启动: {e}')

    def _drop_files(self, account_id: str):
        st = self.storages.pop(account_id, None)
        if st:
            st.close()
        self.clients.pop(account_id, None)
        accounts.delete(account_id)
        self.logs.drop(account_id)

    async def delete(self, account_id: str):
        account_id = self.require(account_id)
        await self.stop(account_id)
        self.cancel_login(account_id)
        self._drop_files(account_id)

    # ---------- 设置 ----------
    def get_settings(self, account_id: str) -> dict:
        account_id = self.require(account_id)
        cfg = accounts.get_settings(account_id)
        meta = accounts.read_meta(account_id)
        return {
            'remark': meta.get('name') or '',
            'autostart': bool(meta.get('autostart')),
            'agent_backend': cfg['agent_backend'],
            'agent_model': cfg['agent_model'],
            'workdir': cfg['workdir'],
            'agent_timeout': cfg['agent_timeout'],
            'system_prompt': cfg['system_prompt'],
            'context_scope': cfg['context_scope'],
            'mark_read': bool(cfg['mark_read']),
            'reply_in_topic': bool(cfg['reply_in_topic']),
            'reply_mode': cfg['reply_mode'],
            'reply_signature': cfg['reply_signature'],
            'ack_reaction': bool(cfg['ack_reaction']),
            'deny_reply': cfg['deny_reply'],
            'memory_enabled': bool(cfg['memory_enabled']),
            'memory_review_at': cfg['memory_review_at'],
            'triggers': cfg['triggers'],
        }

    def save_settings(self, account_id: str, data: dict) -> dict:
        account_id = self.require(account_id)
        workdir = data['workdir'].strip()
        if workdir and not os.path.isdir(workdir):
            raise ValueError(f'工作目录不存在: {workdir}')
        data = {**data, 'workdir': workdir}
        accounts.update_meta(account_id, name=data['remark'].strip(), autostart=data['autostart'])
        accounts.save_settings(account_id, data)
        return {'applied': self._apply_running(account_id)}

    def _apply_running(self, account_id: str) -> bool:
        """保存即生效:把新配置热更新进运行中的监听,不用重启(重启会丢掉排队中的消息)。"""
        listener = self.listeners.get(account_id)
        if listener and listener.active:
            listener.apply_settings(accounts.get_settings(account_id))
            return True
        return False

    def set_chat_agent(self, account_id: str, chat_id: str, enabled: bool) -> dict:
        """按会话开关 agent。复用触发规则的名单,这样设置页和这里看到的永远是同一份。"""
        account_id = self.require(account_id)
        chat_id = str(chat_id)
        meta = accounts.read_meta(account_id)
        settings = dict(meta.get('settings') or {})
        triggers = {**accounts.get_settings(account_id)['triggers'], **(settings.get('triggers') or {})}
        exclude = [c for c in triggers.get('exclude_chats') or [] if str(c) != chat_id]
        include = list(triggers.get('include_chats') or [])
        if enabled:
            if include and chat_id not in [str(c) for c in include]:
                include.append(chat_id)         # 开了白名单时,打开开关要加进白名单才真的生效
        else:
            exclude.append(chat_id)
        settings['triggers'] = {**triggers, 'exclude_chats': exclude, 'include_chats': include}
        accounts.update_meta(account_id, settings=settings)
        self._apply_running(account_id)
        return {'agent_enabled': enabled}

    def _session_key(self, cfg: dict, chat_id: str, anchor: str) -> str:
        scope = cfg['context_scope']
        if scope == 'global':
            return 'global'
        return str(chat_id) if scope == 'chat' else f'{chat_id}:{anchor or ""}'

    def reset_session(self, account_id: str, chat_id: str, anchor: str = '') -> dict:
        """和在飞书里发 /clear 一样: 清排队 + 换新 agent 会话。"""
        account_id = self.require(account_id)
        listener = self.listeners.get(account_id)
        cfg = listener.cfg if listener else accounts.get_settings(account_id)
        key = self._session_key(cfg, chat_id, anchor)
        if listener and listener.dispatcher:
            return {'cleared': listener.dispatcher.clear_session(key)}
        get_backend(storage=self.storage(account_id), cfg=cfg, account_id=account_id).reset_session(key)
        return {'cleared': 0}

    # ---------- 运行 ----------
    async def start(self, account_id: str) -> dict:
        self._loop = asyncio.get_running_loop()
        account_id = self.require(account_id)
        existing = self.listeners.get(account_id)
        if existing and existing.active:
            raise Conflict('账号已在运行')
        login = self.logins.get(account_id)
        if login and not login.done:
            raise Conflict('正在扫码登录，请先完成或取消')
        if not LarkAuth(account_id).cookies:
            raise Conflict('还没有登录凭证，请先登录')
        listener = Listener(account_id, agent=True)
        self.listeners[account_id] = listener
        listener.task = asyncio.create_task(self._supervise(listener))
        return self.describe(account_id)

    async def _supervise(self, listener: Listener):
        try:
            await listener.run()
        except asyncio.CancelledError:
            pass
        except Exception:
            # Listener.run 已记录状态和日志,这里只防止「Task exception never retrieved」
            pass

    async def stop(self, account_id: str) -> dict:
        account_id = self.require(account_id)
        listener = self.listeners.get(account_id)
        if listener and listener.task and not listener.task.done():
            listener.task.cancel()
            await asyncio.gather(listener.task, return_exceptions=True)
        self.listeners.pop(account_id, None)
        return self.describe(account_id)

    async def restart(self, account_id: str) -> dict:
        await self.stop(account_id)
        return await self.start(account_id)

    async def autostart_all(self):
        self.purge_pending()
        for account_id in accounts.list_ids():
            if accounts.read_meta(account_id).get('autostart') and LarkAuth(account_id).cookies:
                try:
                    await self.start(account_id)
                except Exception as e:
                    logger.bind(account=account_id).error(f'自启失败: {e}')

    async def shutdown(self):
        for account_id in list(self.listeners):
            await self.stop(account_id)
        for account_id in list(self.logins):
            self.cancel_login(account_id)
        for st in self.storages.values():
            st.close()
        for client in self.clients.values():
            client.close()
        logger.remove(self._sink_id)

    # ---------- 登录 ----------
    def _ensure_not_running(self, account_id: str):
        listener = self.listeners.get(account_id)
        if listener and listener.active:
            raise Conflict('账号正在运行，请先停止再重新登录')

    def start_login(self, account_id: str, region: str = None) -> dict:
        account_id = self.require(account_id)
        self._ensure_not_running(account_id)
        self.cancel_login(account_id)
        region = region or LarkAuth(account_id).region.name
        flow = LoginFlow(account_id, region, on_success=self._on_login_success)
        self.logins[account_id] = flow
        return flow.snapshot()

    def login_status(self, account_id: str) -> dict:
        flow = self.logins.get(accounts.normalize(account_id))
        if flow:
            return flow.snapshot()
        self.require(account_id)
        return {'state': 'idle', 'message': '', 'qr': '', 'attempt': 0, 'account_id': account_id}

    def cancel_login(self, account_id: str):
        flow = self.logins.pop(account_id, None)
        if flow:
            flow.cancel()

    def cookie_login(self, account_id: str, cookie: str, region: str = None) -> str:
        account_id = self.require(account_id)
        self._ensure_not_running(account_id)
        self.cancel_login(account_id)
        auth = LarkAuth(account_id)
        msg = auth.import_cookie_string(cookie, get_region(region) if region else auth.region)
        accounts.update_meta(account_id, pending=False)
        self._after_login(account_id)
        threading.Thread(target=self.refresh_profile, args=(account_id, True), daemon=True).start()
        return msg

    # ---------- 飞书客户端 ----------
    def api_client(self, account_id: str) -> LarkClient:
        """网页操作用的客户端: 账号在运行就用它的,否则建一个并缓存。有网络请求,在线程里调。"""
        listener = self.listeners.get(account_id)
        if listener and listener.client:
            return listener.client
        with self._client_lock:
            cached = self.clients.get(account_id)
            if cached:
                return cached
            if time.time() < self._client_fail.get(account_id, 0):
                raise AuthExpired('登录已失效，请重新登录')
            try:
                client = LarkClient(LarkAuth(account_id))
            except Exception:
                self._client_fail[account_id] = time.time() + self.CLIENT_RETRY
                raise
            self._client_fail.pop(account_id, None)
            self.clients[account_id] = client
            return client

    def refresh_profile(self, account_id: str, force: bool = False) -> dict:
        """取飞书里的姓名/头像/公司。资料没过期且不强制时直接用缓存。"""
        account_id = self.require(account_id)
        cur = profile.load(account_id)
        if not force and not profile.stale(cur):
            return cur
        try:
            return profile.refresh(account_id, self.api_client(account_id))
        except Exception as e:
            logger.bind(account=account_id).debug(f'刷新账号资料失败(忽略): {e}')
            return cur

    def _refresh_profile_soon(self, account_id: str, prof: dict):
        """老账号(升级前登录的)也要有名字和头像: 资料过期就后台补一次,失败了隔一阵才重试。"""
        if not profile.stale(prof) or time.time() - self._profile_tried.get(account_id, 0) < self.PROFILE_RETRY:
            return
        self._profile_tried[account_id] = time.time()
        threading.Thread(target=self.refresh_profile, args=(account_id,), daemon=True).start()

    def avatar(self, account_id: str, kind: str, ident: str) -> tuple:
        """返回 (字节, content-type);拿不到返回 (b'', ''),前端退回首字母。kind: user | chat。在线程里调。"""
        account_id = self.require(account_id)
        name = kind + '_' + hashlib.sha1(str(ident).encode()).hexdigest()[:20]
        path, ctype = profile.cached_file(account_id, name)
        if path and time.time() - path.stat().st_mtime < profile.AVATAR_TTL:
            return path.read_bytes(), ctype
        if time.time() < self._avatar_miss.get((account_id, name), 0):
            return (path.read_bytes(), ctype) if path else (b'', '')
        try:
            client = self.api_client(account_id)
            info = profile.chatter_info(client, ident) if kind == 'user' else profile.chat_avatar_info(client, ident)
            data, new_ctype = profile.download_avatar(client.auth, info)
        except Exception as e:
            logger.bind(account=account_id).debug(f'取头像失败(退回首字母): {e}')
            data, new_ctype = b'', ''
        if data:
            profile.write_cache(account_id, name, data, new_ctype)
            return data, new_ctype
        self._avatar_miss[(account_id, name)] = time.time() + self.AVATAR_RETRY
        return (path.read_bytes(), ctype) if path else (b'', '')

    # ---------- 网页上的操作 ----------
    def send_message(self, account_id: str, chat_id: str, text: str, root_id: str = None) -> dict:
        """从网页发一条消息。在线程里调。先落库再让回显补全,和 lark send 同一套。"""
        account_id = self.require(account_id)
        client = self.api_client(account_id)
        msg_id = client.send_msg(text, chat_id, root_id=root_id)
        if not msg_id:
            raise ValueError('发送失败，未能确认消息已发出')
        self.storage(account_id).save_sent(msg_id, chat_id, text, client.auth.user_id, root_id=root_id)
        return {'msg_id': msg_id}

    def pull_history(self, account_id: str, chat_id: str, count: int = 50) -> dict:
        """把本地最早一条之前的 count 条历史拉进消息库。在线程里调。"""
        account_id = self.require(account_id)
        client = self.api_client(account_id)
        st = self.storage(account_id)
        oldest = st.oldest_position(chat_id)
        if not oldest:
            info = client.get_chat_info(chat_id) or {}
            oldest = int(info.get('lastMessagePosition') or 0) + 1
        if oldest <= 1:
            return {'pulled': 0, 'at_start': True}
        start = max(1, oldest - count)
        msgs = client.pull_history(chat_id, list(range(start, oldest)))
        names, chat_name, saved = {}, st.get_chat_name(chat_id) or '', 0
        for m in msgs:
            uid = str(m.get('from_id') or '')
            if uid and uid not in names:
                names[uid] = client.get_user_name(uid, chat_id) or ''
            is_own = uid == str(client.auth.user_id)
            if st.save_message(m, sender_name=names.get(uid, ''), chat_name=chat_name, direction='out' if is_own else 'in'):
                saved += 1
        return {'pulled': saved, 'at_start': start <= 1}

    def people(self, account_id: str, query: str = '', ids=()) -> list:
        """按名字搜人(往名单里加人用),或者按 id 取名字(显示名单里已有的人)。在线程里调。"""
        account_id = self.require(account_id)
        if query:
            client = self.api_client(account_id)
            out = []
            for r in client.search(query) or []:
                uid = str(r.get('id') or '')
                if r.get('type') == 'user' and _ID.fullmatch(uid):
                    out.append({'id': uid, 'name': _plain(r.get('title')), 'desc': _plain(r.get('summary'))})
            return [{**p, 'avatar': f'/api/accounts/{account_id}/avatars/user/{p["id"]}'} for p in out[:20]]
        ids = [str(i) for i in ids if _ID.fullmatch(str(i))][:200]
        names = self.storage(account_id).sender_names(ids)
        missing = [i for i in ids if not names.get(i) and not self._names.get((account_id, i))]
        if missing:
            try:
                client = self.api_client(account_id)
                for uid in missing[:30]:
                    self._names[(account_id, uid)] = client.get_user_name(uid, '0') or ''
            except Exception as e:
                logger.bind(account=account_id).debug(f'查名字失败(只显示 id): {e}')
        return [{'id': i, 'name': names.get(i) or self._names.get((account_id, i)) or '', 'desc': '',
                 'avatar': f'/api/accounts/{account_id}/avatars/user/{i}'} for i in ids]

    # ---------- 长期记忆、定时任务 ----------
    def memory(self, account_id: str) -> dict:
        account_id = self.require(account_id)
        items = memory.entries(account_id)
        return {'entries': items, 'used': memory.used(items), 'limit': memory.MEMORY_LIMIT,
                'last_review': accounts.read_meta(account_id).get('memory_review_last') or ''}

    def memory_change(self, account_id: str, action: str, n: int = 0, text: str = '') -> dict:
        account_id = self.require(account_id)
        try:
            if action == 'add':
                memory.add(account_id, text)
            elif action == 'edit':
                memory.edit(account_id, n, text)
            else:
                memory.remove(account_id, n)
        except memory.MemoryEditError as e:
            raise ValueError(str(e))
        return self.memory(account_id)

    def memory_review(self, account_id: str) -> dict:
        """「立即回顾」。在线程里调(要等后台确认开始了没有)。"""
        account_id = self.require(account_id)
        cfg = accounts.get_settings(account_id)
        if not cfg['memory_enabled']:
            raise Conflict('长期记忆没有开启')
        if cfg['agent_backend'] == 'none':
            raise Conflict('没有接入 Agent，无法回顾')
        listener = self.listeners.get(account_id)
        result = listener.review_now() if listener else ''
        if not result:
            raise Conflict('账号运行中才能回顾，请先启动')
        if result == 'empty':
            raise Conflict('最近 24 小时没有聊天，不需要回顾')
        if result == 'busy':
            raise Conflict('上一次回顾还没结束')
        return {'ok': True}

    def tasks(self, account_id: str) -> list:
        account_id = self.require(account_id)
        st = self.storage(account_id)
        names = {c.chat_id: c.name for c in st.list_chats(limit=1000)}
        return [{'id': t.id, 'kind': t.kind, 'when': tasks.describe(t), 'next_run': t.run_at, 'chat_id': t.chat_id,
                 'chat': names.get(t.chat_id) or t.chat_id, 'anchor': t.anchor, 'content': t.content, 'created_by': t.created_by}
                for t in st.task_list()]

    def remove_task(self, account_id: str, task_id: int) -> dict:
        account_id = self.require(account_id)
        if not self.storage(account_id).task_remove(task_id):
            raise NotFound(f'没有这个定时任务: {task_id}')
        return {'ok': True}

    # ---------- 数据 ----------
    def overview(self, account_id: str) -> dict:
        account_id = self.require(account_id)
        st = self.storage(account_id)
        counts = st.message_counts()
        days = st.daily_counts(7)
        names = {c.chat_id: c.name for c in st.list_chats(limit=1000)}
        return {
            'counts': {'in': counts.get('in', 0), 'out': counts.get('out', 0)},
            'chats': len(st.list_chats(limit=1000)),
            'sessions': [{
                'key': s.session_key, 'chat_id': s.chat_id, 'anchor': s.anchor, 'started': bool(s.started),
                'msg_count': s.msg_count,
                'last_active': s.last_active.strftime('%m-%d %H:%M') if s.last_active else '',
            } for s in st.list_sessions(limit=20)],
            'recent': [{
                'id': m.id, 'time': m.create_time, 'direction': m.direction, 'chat_id': m.chat_id, 'chat': m.chat_name or names.get(m.chat_id) or m.chat_id,
                'sender': m.sender_name or m.sender_id, 'sender_id': m.sender_id, 'type': m.msg_type_name,
                'content': (m.content or '')[:200],
            } for m in st.recent_messages(limit=12)],
            'days': days,
        }

    def _agent_enabled(self, triggers: dict, chat_id: str) -> bool:
        include = [str(c) for c in triggers.get('include_chats') or []]
        exclude = [str(c) for c in triggers.get('exclude_chats') or []]
        return chat_id not in exclude and (not include or chat_id in include)

    def chats(self, account_id: str) -> list:
        account_id = self.require(account_id)
        me = LarkAuth(account_id).user_id
        triggers = accounts.get_settings(account_id)['triggers']
        out = self.storage(account_id).chat_summaries(me=me)
        for c in out:
            kind, ident = ('user', c['peer_id']) if c['chat_type'] == 1 and c['peer_id'] else ('chat', c['chat_id'])
            c['avatar'] = f'/api/accounts/{account_id}/avatars/{kind}/{ident}'
            c['agent_enabled'] = self._agent_enabled(triggers, c['chat_id'])
        return out

    def topics(self, account_id: str, chat_id: str) -> list:
        account_id = self.require(account_id)
        return self.storage(account_id).topic_summaries(chat_id)

    def chat_messages(self, account_id: str, chat_id: str, anchor: str = None, before: tuple = None, limit: int = 50) -> dict:
        account_id = self.require(account_id)
        limit = max(1, min(limit, 200))
        st = self.storage(account_id)
        rows, has_more = st.chat_page(chat_id, anchor=anchor, before=before, limit=limit)
        by_agent = st.agent_sent_ids(m.msg_id for m in rows if m.direction == 'out')
        return {
            'has_more': has_more,
            'messages': [{
                'id': m.id, 'msg_id': m.msg_id, 'time': m.create_time, 'direction': m.direction,
                'sender': m.sender_name or m.sender_id, 'sender_id': m.sender_id, 'type': m.msg_type_name,
                'content': m.content or '', 'anchor': m.anchor or '', 'agent': m.msg_id in by_agent,
            } for m in rows],
        }

    def stats(self, account_id: str) -> dict:
        account_id = self.require(account_id)
        days = self.storage(account_id).daily_counts(7)
        return {'days': days, 'total_in': sum(d['in'] for d in days), 'total_out': sum(d['out'] for d in days)}

    def runtimes(self) -> list:
        """本机 agent CLI 的安装情况(路径+版本)。版本查询要起子进程,缓存 60 秒。"""
        now = time.time()
        cached = self._runtime_cache.get('v')
        if cached and now - cached[0] < 60:
            return cached[1]
        out = []
        for key, info in BACKENDS.items():
            if not info['binary']:
                continue
            path = find_binary(key)
            version = ''
            if path:
                try:
                    r = subprocess.run([path, '--version'], capture_output=True, timeout=8, text=True, encoding='utf-8', errors='replace')
                    text = (r.stdout or r.stderr).strip()
                    version = text.splitlines()[0][:80] if text else ''
                except Exception:
                    version = ''
            out.append({'id': key, 'label': info['label'], 'binary': os.path.basename(path) if path else info['binary'], 'installed': bool(path),
                        'path': path or '', 'version': version})
        self._runtime_cache['v'] = (now, out)
        return out

    def meta(self) -> dict:
        from .. import __version__
        return {
            'version': __version__,
            'backends': [{'id': k, 'label': v['label'], 'installed': (not v['binary']) or bool(find_binary(k))}
                         for k, v in BACKENDS.items()],
            'regions': [{'id': r.name, 'label': r.label} for r in REGIONS.values()],
            'server_time': time.time(),
        }
