import asyncio
import json
import os
import shutil
import subprocess
import uuid

from loguru import logger

from .. import accounts
from ..config import DATA_DIR

SESSIONS_PATH = DATA_DIR / 'agent_sessions.json'

BACKENDS = {
    'claude': {'label': 'Claude Code', 'binary': 'claude'},
    'codex': {'label': 'Codex', 'binary': 'codex'},
    'none': {'label': '不接入 agent(仅入库)', 'binary': ''},
}


class AgentBackend:
    name = 'base'

    async def run(self, session_key: str, prompt: str, chat_id: str='', anchor: str='') -> str:
        raise NotImplementedError

    def reset_session(self, session_key: str):
        pass


class CliBackend(AgentBackend):
    """把 prompt 经 stdin 交给本地 coding agent CLI,按 session_key 持久续聊。子类只管命令行和输出解析。"""
    binary = ''

    def __init__(self, storage=None, cfg: dict=None, account_id: str=None):
        self.account_id = accounts.normalize(account_id)
        self.log = logger.bind(account=self.account_id)
        self.cfg = cfg if cfg is not None else accounts.get_settings(self.account_id)
        if storage is None:
            from ..storage import Storage
            storage = Storage(account_id=self.account_id)
        self.storage = storage
        if self.account_id == accounts.DEFAULT_ID:
            self._migrate_json_sessions()

    def _migrate_json_sessions(self):
        if not SESSIONS_PATH.exists():
            return
        try:
            old = json.loads(SESSIONS_PATH.read_text(encoding='utf-8'))
            for key, v in old.items():
                chat_id, _, anchor = key.partition(':')
                if key == 'global':
                    chat_id, anchor = 'global', ''
                self.storage.session_upsert(key, chat_id, anchor if key != chat_id else '',
                                            v.get('id', ''), bool(v.get('started')))
            SESSIONS_PATH.rename(SESSIONS_PATH.with_suffix('.json.migrated'))
            self.log.info('已从 agent_sessions.json 迁移到 SQLite session 表')
        except Exception as e:
            self.log.warning(f'agent_sessions.json 迁移失败(忽略): {e}')

    def _new_session_id(self, session_key: str, stable: bool) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, 'larkx:' + session_key)) if stable else str(uuid.uuid4())

    def _key(self, session_key: str) -> str:
        """落库用的 key。不同 agent 的会话 id 互不通用,非默认后端加前缀,切后端不会拿错 id 去续聊。"""
        return session_key

    def _session(self, skey: str, chat_id: str='', anchor: str='') -> dict:
        row = self.storage.session_get(skey)
        if not row:
            sid = self._new_session_id(skey, stable=True)
            self.storage.session_upsert(skey, chat_id, anchor, sid, False)
            return {'id': sid, 'started': False}
        return {'id': row.agent_session_id, 'started': bool(row.started)}

    def reset_session(self, session_key: str):
        skey = self._key(session_key)
        row = self.storage.session_get(skey)
        if row:
            self.storage.session_upsert(skey, row.chat_id, row.anchor, self._new_session_id(skey, stable=False), False)

    def model_args(self) -> list:
        return []

    def build_args(self, sess: dict) -> list:
        raise NotImplementedError

    def parse(self, stdout: str, sess: dict) -> tuple:
        """返回 (给日志用的文本, 需要持久化的 agent session id;拿不到则为空)"""
        raise NotImplementedError

    async def run(self, session_key: str, prompt: str, chat_id: str='', anchor: str='') -> str:
        skey = self._key(session_key)
        sess = self._session(skey, chat_id, anchor)
        exe = shutil.which(self.binary)
        if not exe:
            self.log.error(f'未找到 {self.binary} CLI,请确认已安装并在 PATH 中')
            return ''
        workdir = self.cfg.get('workdir') or None
        if workdir and not os.path.isdir(workdir):
            self.log.error(f'agent 工作目录不存在: {workdir}')
            return ''
        args = [exe] + self.build_args(sess)
        preview = prompt.replace('\n', ' ')[:300]
        self.log.info(f'调 agent [{session_key}]: {" ".join(args)} << {preview}' + ('…' if len(prompt) > 300 else ''))
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workdir,
            )
        except FileNotFoundError:
            self.log.error(f'未找到 {self.binary} CLI,请确认已安装并在 PATH 中')
            return ''
        timeout = int(self.cfg.get('agent_timeout') or 0) or None
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(prompt.encode('utf-8')), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            self.log.error(f'agent 超过 {timeout}s 未返回,已终止 [{session_key}]')
            return ''
        except asyncio.CancelledError:
            # 账号被停掉时别留下无人收尾的 agent 子进程
            proc.kill()
            raise
        out = stdout.decode('utf-8', errors='replace').strip()
        if proc.returncode != 0:
            err = stderr.decode('utf-8', errors='replace').strip()
            self.log.error(f'agent 返回非零({proc.returncode}): {err[-500:]}')
            return ''
        text, agent_sid = self.parse(out, sess)
        if agent_sid and ((not sess['started']) or agent_sid != sess['id']):
            self.storage.session_upsert(skey, chat_id, anchor, agent_sid, True)
        self.storage.session_touch(skey)
        return text


CLAUDE_FLAGS = ['-p', '--dangerously-skip-permissions']


class ClaudeCodeBackend(CliBackend):
    name = 'claude'
    binary = 'claude'

    def __init__(self, cmd_template: str=None, storage=None, cfg: dict=None, account_id: str=None):
        super().__init__(storage=storage, cfg=cfg, account_id=account_id)
        self.cmd_template = cmd_template
        if cmd_template:
            self.binary = cmd_template.split()[0]

    def model_args(self) -> list:
        model = self.cfg.get('agent_model')
        return ['--model', model] if model else []

    def build_args(self, sess: dict) -> list:
        base = self.cmd_template.split()[1:] if self.cmd_template else CLAUDE_FLAGS
        return base + self.model_args() + (['--resume', sess['id']] if sess['started'] else ['--session-id', sess['id']])

    def parse(self, stdout: str, sess: dict) -> tuple:
        return stdout, sess['id']


CODEX_FLAGS = ['--json', '--skip-git-repo-check', '--dangerously-bypass-approvals-and-sandbox']


class CodexBackend(CliBackend):
    """codex exec --json: 会话 id 由 Codex 自己分配(thread.started),不能像 claude 那样预先指定,首轮跑完再记下来。"""
    name = 'codex'
    binary = 'codex'

    def _new_session_id(self, session_key: str, stable: bool) -> str:
        return ''

    def _key(self, session_key: str) -> str:
        return 'codex|' + session_key

    def model_args(self) -> list:
        model = self.cfg.get('agent_model')
        return ['-m', model] if model else []

    def build_args(self, sess: dict) -> list:
        if sess['started'] and sess['id']:
            return ['exec', 'resume'] + CODEX_FLAGS + self.model_args() + [sess['id'], '-']
        return ['exec'] + CODEX_FLAGS + self.model_args() + ['-']

    def parse(self, stdout: str, sess: dict) -> tuple:
        thread_id, text = '', ''
        for line in stdout.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            kind = ev.get('type')
            if kind == 'thread.started':
                thread_id = ev.get('thread_id') or thread_id
            elif kind == 'item.completed':
                item = ev.get('item') or {}
                if item.get('type') == 'agent_message':
                    text = item.get('text') or text
            elif kind == 'turn.failed':
                self.log.warning(f'codex 本轮失败: {json.dumps(ev.get("error"), ensure_ascii=False)[:300]}')
        return text, thread_id


class NullBackend(AgentBackend):
    name = 'none'

    async def run(self, session_key: str, prompt: str, chat_id: str='', anchor: str='') -> str:
        return ''


def get_backend(name: str=None, storage=None, cfg: dict=None, account_id: str=None) -> AgentBackend:
    account_id = accounts.normalize(account_id)
    cfg = cfg if cfg is not None else accounts.get_settings(account_id)
    name = name or cfg['agent_backend']
    if name == 'claude':
        return ClaudeCodeBackend(storage=storage, cfg=cfg, account_id=account_id)
    if name == 'codex':
        return CodexBackend(storage=storage, cfg=cfg, account_id=account_id)
    return NullBackend()
