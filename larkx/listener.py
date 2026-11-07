"""一个账号的常驻监听: WS 收消息 -> 入库 -> (可选)交给本地 coding agent。

`lark listen` 和 web 里的「启动账号」共用这一份。
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

from loguru import logger

from . import accounts
from .agent import AgentDispatcher, get_backend
from .auth import AuthExpired, LarkAuth
from .client import LarkClient
from .storage import Storage


class ListenerError(Exception):
    pass


class FileLock:
    """系统文件锁,进程退出(包括崩溃)时自动释放,不会留下要手动删的锁。"""

    def __init__(self, path: Path):
        self.path = path
        self.fh = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, 'a+')
        try:
            if os.name == 'nt':
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self.fh = fh
        return True

    def release(self):
        if not self.fh:
            return
        try:
            if os.name == 'nt':
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self.fh.close()
        self.fh = None


class AccountLock(FileLock):
    """同一账号同一时间只允许一个进程监听(lark listen 和 lark web 之间也互斥),
    否则两条连接会把每条消息各回复一遍。"""

    def __init__(self, account_id: str):
        super().__init__(accounts.home_of(account_id) / 'listener.lock')


class UserLock(FileLock):
    """同一个飞书用户在本机只允许监听一处。AccountLock 按数据目录区分,换一个 LARKX_HOME
    (另一份数据目录、演示服务)就拦不住;这把锁放在系统临时目录,按区域 + user_id 区分。"""

    def __init__(self, region: str, user_id: str):
        super().__init__(Path(tempfile.gettempdir()) / 'larkx-locks' / f'{region}-{user_id}.lock')


class Listener:
    # idle -> starting -> connecting -> running <-> reconnecting
    # 终态: stopped(被取消) / login_required(凭证失效) / error
    ACTIVE = ('starting', 'connecting', 'running', 'reconnecting')
    CLOSED_WAIT = 2     # 服务端正常关闭 WS 后多久重连
    ERROR_WAIT = 10     # 异常断开后多久重连
    SELF_ECHO_WAIT = 3  # 和自己的会话: 等 lark send 把自己发的消息落库,再判断回显是不是用户亲手发的

    def __init__(self, account_id: str=None, agent: bool=True, cfg: dict=None):
        self.account_id = accounts.normalize(account_id)
        self.agent = agent
        self.cfg = cfg if cfg is not None else accounts.get_settings(self.account_id)
        self.log = logger.bind(account=self.account_id)
        self.state = 'idle'
        self.error = ''
        self.client = None
        self.dispatcher = None
        self.storage = None
        self.task = None
        self.locks = []

    @property
    def active(self) -> bool:
        return self.state in self.ACTIVE

    def stats(self) -> dict:
        return self.dispatcher.stats() if self.dispatcher else {'busy': 0, 'queued': 0}

    def _set(self, state: str, error: str=''):
        self.state, self.error = state, error

    def apply_settings(self, new: dict):
        """运行中热更新设置。dispatcher / backend / on_message 共用同一个 cfg 字典,
        只做 update(不 clear),别的线程读到的永远是完整配置;换后端则替换 dispatcher.backend。"""
        old_backend = self.cfg.get('agent_backend')
        self.cfg.update(new)
        if self.dispatcher and new.get('agent_backend') != old_backend:
            self.dispatcher.backend = get_backend(storage=self.storage, cfg=self.cfg, account_id=self.account_id)
        self.log.info('设置已热更新' + (f',agent 后端 {old_backend} -> {new.get("agent_backend")}' if new.get('agent_backend') != old_backend else ''))

    async def run(self, auth: LarkAuth=None):
        """一直跑,直到被取消(stopped)或凭证失效(抛 AuthExpired)。"""
        self._set('starting')
        try:
            await self._run(auth)
        except asyncio.CancelledError:
            self._set('stopped')
            raise
        except AuthExpired as e:
            # 网络抖动导致校验失败不等于凭证失效,别让用户白白重新扫码
            transient = bool(auth and auth.transient_error)
            self._set('error' if transient else 'login_required', str(e))
            self.log.error(str(e))
            raise
        except Exception as e:
            self._set('error', str(e))
            self.log.error(f'监听异常退出: {e}')
            raise
        finally:
            await self._cleanup()

    async def _cleanup(self):
        if self.dispatcher and self.client and self.client._loop_started:
            try:
                fut = asyncio.run_coroutine_threadsafe(self.dispatcher.shutdown(), self.client.loop)
                await asyncio.wait_for(asyncio.wrap_future(fut), timeout=5)
            except Exception as e:
                self.log.debug(f'关闭 agent 队列失败: {e}')
        if self.client:
            self.client.close()
        if self.storage:
            self.storage.close()
        for lock in self.locks:
            lock.release()
        self.locks = []

    async def _run(self, auth: LarkAuth=None):
        lock = AccountLock(self.account_id)
        if not lock.acquire():
            raise ListenerError('该账号已在其他进程中运行（lark listen 或 lark web），同时运行会重复回复。请先停止另一处。')
        self.locks.append(lock)
        if auth is None:
            auth = LarkAuth(self.account_id)
        self.client = client = await asyncio.to_thread(LarkClient, auth)
        self.storage = st = Storage(account_id=self.account_id)
        if self.agent and (not auth.user_id):
            await asyncio.to_thread(auth._fetch_profile)
            auth.save()
        if self.agent and (not auth.user_id):
            raise ListenerError('无法确定当前账号 user_id,--agent 存在自回环风险,已拒绝启动。请先 lark auth check 确认凭证有效。')
        if auth.user_id:
            region = getattr(getattr(auth, 'region', None), 'name', '') or 'feishu'
            user_lock = UserLock(region, str(auth.user_id))
            if not user_lock.acquire():
                raise ListenerError('这个飞书账号已在本机其他地方运行（另一个数据目录或演示服务），同时运行会重复回复。请先停止另一处。')
            self.locks.append(user_lock)
        cfg = self.cfg
        if self.agent:
            backend = get_backend(storage=st, cfg=cfg, account_id=self.account_id)

            async def reply_fn(chat_id, text, root_id=None):
                msg_id = await asyncio.to_thread(client.send_msg, text, chat_id, root_id)
                # 回执也要落库,否则在「和自己的会话」里它的回显会被当成用户发的,又触发一轮 agent
                if msg_id:
                    st.save_sent(msg_id, chat_id, text, auth.user_id, root_id=root_id)
                return msg_id
            self.dispatcher = AgentDispatcher(backend, reply_fn, cfg=cfg, account_id=self.account_id)
        log = self.log
        name_cache = {}

        async def on_message(msg):
            chat_id = msg['chat_id']
            chat_type = msg.get('chat_type', 0)
            is_own = str(msg['from_id']) == str(auth.user_id)
            sender_key = (msg['from_id'], chat_id)
            if sender_key not in name_cache:
                name_cache[sender_key] = await asyncio.to_thread(client.get_user_name, msg['from_id'], chat_id)
            sender_name = name_cache.get(sender_key) or ''
            if chat_id not in name_cache:
                if chat_type in (2, 3):
                    name_cache[chat_id] = await asyncio.to_thread(client.get_group_name, chat_id)
                    if name_cache[chat_id]:
                        st.update_chat_name(chat_id, name_cache[chat_id], chat_type)
                elif chat_type == 1 and not is_own and sender_name:
                    name_cache[chat_id] = sender_name
                    st.update_chat_name(chat_id, sender_name, chat_type)
            chat_name = name_cache.get(chat_id) or ''
            typed_in_self_chat = False
            if is_own and chat_type == 1 and self.dispatcher and (cfg.get('triggers') or {}).get('self_chat_enabled'):
                if await asyncio.to_thread(client.is_self_chat, chat_id):
                    # agent 的回复(lark send)和网页发的消息都按服务端 id 先落库;等落完,库里没有的才是用户亲手发的。
                    # 这一步挡的是死循环: agent 在这个会话里回复,回显回来不能再交给 agent
                    await asyncio.sleep(self.SELF_ECHO_WAIT)
                    typed_in_self_chat = not st.message_exists(msg['msg_id'], chat_id)
            saved = st.save_message(msg, sender_name=sender_name, chat_name=chat_name,
                                    direction='out' if is_own else 'in')
            if saved:
                where = chat_name or chat_id
                content = msg['content'] or ''
                shown = content[:80] + ('…' if len(content) > 80 else '')
                line = f"[{where}] {sender_name or msg['from_id']}: {shown}"
                if is_own and sys.stderr.isatty():
                    line = f'\x1b[36m{line}\x1b[0m'
                log.info(line)
                if cfg.get('mark_read') and not is_own and msg.get('position'):
                    await asyncio.to_thread(client.mark_read, chat_id, msg['position'], [msg['msg_id']])
                if self.dispatcher:
                    await self.dispatcher.submit(msg, chat_name=chat_name, sender_name=sender_name, my_user_id=auth.user_id, self_chat=typed_in_self_chat)

        def connected():
            self._set('running')

        while True:
            self._set('connecting' if self.state != 'reconnecting' else 'reconnecting', self.error)
            reason = ''
            try:
                await client.connect_websocket(on_message, on_connected=connected)
                reason, wait = 'WS 被服务端关闭', self.CLOSED_WAIT
            except AuthExpired:
                raise
            except Exception as e:
                reason, wait = f'WS 断开: {e}', self.ERROR_WAIT
            self._set('reconnecting', reason)
            log.warning(f'{reason},{wait}s 后重连')
            await asyncio.sleep(wait)
