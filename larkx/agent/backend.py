import asyncio
import json
import os
import shutil
import signal
import subprocess
import sysconfig
import uuid

from loguru import logger

from .. import accounts
from ..config import DATA_DIR

SESSIONS_PATH = DATA_DIR / 'agent_sessions.json'

BACKENDS = {
    'claude': {'label': 'Claude Code', 'binary': 'claude'},
    'codex': {'label': 'Codex', 'binary': 'codex'},
    'trae': {'label': 'TRAE CLI', 'binary': 'traecli', 'alt': ('trae-cli',)},
    'doubao': {'label': '豆包工作', 'binary': 'doubao'},
    'pi': {'label': 'Pi', 'binary': 'pi'},
    'opencode': {'label': 'opencode', 'binary': 'opencode'},
    'cursor': {'label': 'Cursor CLI', 'binary': 'cursor-agent', 'alt': ('agent',)},
    'none': {'label': '不接入 agent(仅入库)', 'binary': ''},
}


def find_binary(backend: str) -> str:
    """后端 CLI 在 PATH 里的路径,找不到为空。有的 CLI 换过名字(cursor-agent / agent),按顺序都试一遍。"""
    info = BACKENDS.get(backend) or {}
    for name in (info.get('binary'), *info.get('alt', ())):
        path = name and shutil.which(name)
        if path:
            return path
    return ''


def _agent_path() -> str:
    """agent 里执行的 lark 要和当前进程是同一个安装(同一个 Python、同样版本的依赖)。
    PATH 里先找到的 lark 是别的 Python 装的时,把当前 Python 的脚本目录放到最前面。"""
    path = os.environ.get('PATH', '')
    scripts = sysconfig.get_path('scripts')
    mine = shutil.which('lark', path=scripts) if scripts else None
    if not mine:
        return path
    found = shutil.which('lark', path=path)
    if found and os.path.normcase(os.path.dirname(os.path.abspath(found))) == os.path.normcase(os.path.dirname(os.path.abspath(mine))):
        return path
    return scripts + os.pathsep + path


def _kill_tree(proc):
    """连同子进程一起结束。只杀 agent 进程本身的话,Windows 上 codex 这类 .cmd 包装背后的 node、
    agent 正在执行的命令都还会接着跑,/stop 和超时就等于没停。"""
    if proc.returncode is not None:
        return
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True, timeout=10)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
    except (ProcessLookupError, OSError):
        pass


class AgentBackend:
    name = 'base'

    async def run(self, session_key: str, prompt: str, chat_id: str='', anchor: str='') -> str:
        raise NotImplementedError

    def reset_session(self, session_key: str):
        pass

    def session_started(self, session_key: str) -> bool:
        """这个会话的 agent 上下文是否已经建立(第一轮成功跑完过)。"""
        return True


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

    def _exe(self) -> str:
        info = BACKENDS.get(self.name)
        if info and info['binary'] == self.binary:
            return find_binary(self.name)
        return shutil.which(self.binary) or ''     # 自定义命令模板指定的程序

    def reset_session(self, session_key: str):
        skey = self._key(session_key)
        row = self.storage.session_get(skey)
        if row:
            self.storage.session_upsert(skey, row.chat_id, row.anchor, self._new_session_id(skey, stable=False), False)

    def session_started(self, session_key: str) -> bool:
        row = self.storage.session_get(self._key(session_key))
        return bool(row and row.started)

    def model_args(self) -> list:
        return []

    def build_args(self, sess: dict) -> list:
        raise NotImplementedError

    def prompt_args(self, prompt: str) -> list:
        """不收 stdin 的 CLI(豆包、Cursor)把 prompt 放进命令行参数,返回非空时 stdin 不再写 prompt。"""
        return []

    def parse(self, stdout: str, sess: dict) -> tuple:
        """返回 (给日志用的文本, 需要持久化的 agent session id;拿不到则为空)"""
        raise NotImplementedError

    def parse_output(self, stdout: str, stderr: str, sess: dict) -> tuple:
        """会话 id 写在 stderr 里的 CLI(豆包)覆盖这个。"""
        return self.parse(stdout, sess)

    async def run(self, session_key: str, prompt: str, chat_id: str='', anchor: str='') -> str:
        skey = self._key(session_key)
        sess = self._session(skey, chat_id, anchor)
        exe = self._exe()
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
        extra = self.prompt_args(prompt)
        args += extra
        stdin_data = b'' if extra else prompt.encode('utf-8')
        # 告诉 agent 里调用的 lark 命令:这是 agent 发的(加署名、标记),在哪个会话里(定时任务记到这个会话)
        env = {**os.environ, 'PATH': _agent_path(), 'LARKX_AGENT': '1', 'LARKX_ACCOUNT': self.account_id,
               'LARKX_CHAT_ID': chat_id or '', 'LARKX_ANCHOR': anchor or ''}
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workdir,
                env=env,
                start_new_session=True,     # 非 Windows: 自成一个进程组,结束时整组杀掉(Windows 上忽略)
            )
        except FileNotFoundError:
            self.log.error(f'未找到 {self.binary} CLI,请确认已安装并在 PATH 中')
            return ''
        timeout = int(self.cfg.get('agent_timeout') or 0) or None
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(stdin_data), timeout)
        except asyncio.TimeoutError:
            _kill_tree(proc)
            await proc.wait()
            self._abandon_first_turn(skey, sess, chat_id, anchor)
            self.log.error(f'agent 超过 {timeout}s 未返回,已终止 [{session_key}]')
            return ''
        except asyncio.CancelledError:
            # /stop 打断或账号被停掉: 别留下无人收尾的 agent 进程
            _kill_tree(proc)
            self._abandon_first_turn(skey, sess, chat_id, anchor)
            raise
        out = stdout.decode('utf-8', errors='replace').strip()
        if proc.returncode != 0:
            err = stderr.decode('utf-8', errors='replace').strip()
            self.log.error(f'agent 返回非零({proc.returncode}): {err[-500:]}')
            self._abandon_first_turn(skey, sess, chat_id, anchor)
            return ''
        text, agent_sid = self.parse_output(out, stderr.decode('utf-8', errors='replace'), sess)
        if agent_sid and ((not sess['started']) or agent_sid != sess['id']):
            self.storage.session_upsert(skey, chat_id, anchor, agent_sid, True)
        self.storage.session_touch(skey)
        return text

    def _abandon_first_turn(self, skey: str, sess: dict, chat_id: str, anchor: str):
        """第一轮没跑完就换一个新的会话 id。claude 可能已经按这个 id 建了会话文件,
        下次再用 --session-id 会报「Session ID … is already in use」,这个会话之后的消息就全都失败了。"""
        if sess['started']:
            return
        try:
            self.storage.session_upsert(skey, chat_id, anchor, self._new_session_id(skey, stable=False), False)
        except Exception as e:
            self.log.warning(f'换新的 agent 会话 id 失败: {e}')


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


class TraeBackend(CodexBackend):
    """TRAE CLI(traecli)是 Codex 的分支,exec --json 的事件格式和 Codex 一样。"""
    name = 'trae'
    binary = 'traecli'

    def _key(self, session_key: str) -> str:
        return 'trae|' + session_key

    def build_args(self, sess: dict, extra_dirs=(), read_only: bool = False) -> list:
        flags = list(CODEX_FLAGS)
        if sess['started'] and sess['id']:
            # exec resume 不收 --add-dir,额外目录只在首轮带上
            return ['exec', 'resume'] + flags + self.model_args() + [sess['id'], '-']
        for d in extra_dirs:
            flags += ['--add-dir', str(d)]
        return ['exec'] + flags + self.model_args() + ['-']


DOUBAO_FLAGS = ['--dangerously-bypass-approvals-and-sandbox']


class DoubaoBackend(CliBackend):
    """豆包工作 CLI(doubao)。prompt 只能经 -p 传入;-p 模式下回复写 stdout,
    会话 id 以一行 {"type":"session","session_id":…} 写到 stderr,续聊用 --resume <id>。"""
    name = 'doubao'
    binary = 'doubao'

    def _new_session_id(self, session_key: str, stable: bool) -> str:
        return ''

    def _key(self, session_key: str) -> str:
        return 'doubao|' + session_key

    def model_args(self) -> list:
        model = self.cfg.get('agent_model')
        return ['--model', model] if model else []

    def build_args(self, sess: dict, extra_dirs=(), read_only: bool = False) -> list:
        resume = ['--resume', sess['id']] if sess['started'] and sess['id'] else []
        return resume + DOUBAO_FLAGS + self.model_args()

    def prompt_args(self, prompt: str) -> list:
        return ['-p', prompt]

    def parse(self, stdout: str, sess: dict) -> tuple:
        return stdout, ''

    def parse_output(self, stdout: str, stderr: str, sess: dict) -> tuple:
        sid = ''
        for line in stderr.splitlines():
            line = line.strip()
            if not line.startswith('{'):
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if isinstance(ev, dict) and ev.get('type') == 'session' and ev.get('session_id'):
                sid = str(ev['session_id'])
        return stdout, sid or (sess['id'] if sess['started'] else '')


class PiBackend(CliBackend):
    """Pi(pi-coding-agent)。--session-id 打开当前目录下这个 id 的会话,没有就新建,所以可以像 claude 一样预先指定 id。"""
    name = 'pi'
    binary = 'pi'

    def _key(self, session_key: str) -> str:
        return 'pi|' + session_key

    def model_args(self) -> list:
        model = self.cfg.get('agent_model')
        return ['--model', model] if model else []

    def build_args(self, sess: dict, extra_dirs=(), read_only: bool = False) -> list:
        args = ['-p', '--session-id', sess['id']]
        if read_only:
            args += ['--exclude-tools', 'edit,write']
        return args + self.model_args()

    def parse(self, stdout: str, sess: dict) -> tuple:
        return stdout, sess['id']


class OpencodeBackend(CliBackend):
    """opencode run --format json: 每行一个事件,顶层带 sessionID;type=text 的事件给出回复文本(按 part 增量)。"""
    name = 'opencode'
    binary = 'opencode'

    def _new_session_id(self, session_key: str, stable: bool) -> str:
        return ''

    def _key(self, session_key: str) -> str:
        return 'opencode|' + session_key

    def model_args(self) -> list:
        model = self.cfg.get('agent_model')
        return ['--model', model] if model else []

    def build_args(self, sess: dict, extra_dirs=(), read_only: bool = False) -> list:
        args = ['run', '--format', 'json', '--dangerously-skip-permissions']
        if sess['started'] and sess['id']:
            args += ['--session', sess['id']]
        return args + self.model_args()

    def parse(self, stdout: str, sess: dict) -> tuple:
        session_id, parts = '', {}
        for line in stdout.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            session_id = ev.get('sessionID') or session_id
            kind = ev.get('type')
            if kind == 'text':
                part = ev.get('part') or {}
                msg = part.get('messageID') or ''
                parts.setdefault(msg, {})
                pid = part.get('id') or ''
                parts[msg][pid] = parts[msg].get(pid, '') + (part.get('text') or '')
            elif kind == 'error':
                self.log.warning(f'opencode 出错: {json.dumps(ev.get("error"), ensure_ascii=False)[:300]}')
        text = '\n\n'.join(t for t in parts[list(parts)[-1]].values() if t.strip()) if parts else ''
        return text.strip(), session_id


class CursorBackend(CliBackend):
    """Cursor CLI(cursor-agent,新版叫 agent)。-p --output-format json 输出一个 result 对象,带 result 和 session_id。"""
    name = 'cursor'
    binary = 'cursor-agent'

    def _new_session_id(self, session_key: str, stable: bool) -> str:
        return ''

    def _key(self, session_key: str) -> str:
        return 'cursor|' + session_key

    def model_args(self) -> list:
        model = self.cfg.get('agent_model')
        return ['--model', model] if model else []

    def build_args(self, sess: dict, extra_dirs=(), read_only: bool = False) -> list:
        args = ['-p', '--output-format', 'json', '--trust', '--sandbox', 'disabled']
        if not read_only:
            args.append('--force')
        if sess['started'] and sess['id']:
            args += ['--resume', sess['id']]
        return args + self.model_args()

    def prompt_args(self, prompt: str) -> list:
        return ['--', prompt]

    def parse(self, stdout: str, sess: dict) -> tuple:
        for line in reversed(stdout.splitlines()):
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if isinstance(ev, dict) and ev.get('type') == 'result':
                if ev.get('is_error'):
                    self.log.warning(f'cursor 本轮失败: {str(ev.get("result"))[:300]}')
                return ev.get('result') or '', ev.get('session_id') or ''
        return '', ''


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
    cls = {'codex': CodexBackend, 'trae': TraeBackend, 'doubao': DoubaoBackend, 'pi': PiBackend,
           'opencode': OpencodeBackend, 'cursor': CursorBackend}.get(name)
    if cls:
        return cls(storage=storage, cfg=cfg, account_id=account_id)
    return NullBackend()
