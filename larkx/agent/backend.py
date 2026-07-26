import asyncio
import json
import subprocess
import uuid

from loguru import logger

from ..config import DATA_DIR, load_config

SESSIONS_PATH = DATA_DIR / 'agent_sessions.json'


class AgentBackend:
    name = 'base'

    async def run(self, session_key: str, prompt: str) -> str:
        raise NotImplementedError

    def reset_session(self, session_key: str):
        pass


CMD_TEMPLATE = 'claude -p --dangerously-skip-permissions'


class ClaudeCodeBackend(AgentBackend):
    name = 'claude'

    def __init__(self, cmd_template: str=None, storage=None):
        self.cmd_template = cmd_template or CMD_TEMPLATE
        if storage is None:
            from ..storage import Storage
            storage = Storage()
        self.storage = storage
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
            logger.info('已从 agent_sessions.json 迁移到 SQLite session 表')
        except Exception as e:
            logger.warning(f'agent_sessions.json 迁移失败(忽略): {e}')

    def _session(self, session_key: str, chat_id: str='', anchor: str='') -> dict:
        row = self.storage.session_get(session_key)
        if not row:
            sid = str(uuid.uuid5(uuid.NAMESPACE_URL, 'larkx:' + session_key))
            self.storage.session_upsert(session_key, chat_id, anchor, sid, False)
            return {'id': sid, 'started': False}
        return {'id': row.agent_session_id, 'started': bool(row.started)}

    def reset_session(self, session_key: str):
        row = self.storage.session_get(session_key)
        if row:
            self.storage.session_upsert(session_key, row.chat_id, row.anchor, str(uuid.uuid4()), False)

    async def run(self, session_key: str, prompt: str, chat_id: str='', anchor: str='') -> str:
        sess = self._session(session_key, chat_id, anchor)
        args = self.cmd_template.split() + (['--resume', sess['id']] if sess['started'] else ['--session-id', sess['id']])
        preview = prompt.replace('\n', ' ')[:300]
        logger.info(f'调 agent [{session_key}]: {" ".join(args)} << {preview}' + ('…' if len(prompt) > 300 else ''))
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate(prompt.encode('utf-8'))
            out = stdout.decode('utf-8', errors='replace').strip()
            if proc.returncode != 0:
                err = stderr.decode('utf-8', errors='replace').strip()
                logger.error(f'agent 返回非零({proc.returncode}): {err[:500]}')
                return ''
            if not sess['started']:
                self.storage.session_upsert(session_key, chat_id, anchor, sess['id'], True)
            self.storage.session_touch(session_key)
            return out
        except FileNotFoundError:
            logger.error('未找到 claude CLI,请确认已安装并在 PATH 中')
            return ''


class NullBackend(AgentBackend):
    name = 'none'

    async def run(self, session_key: str, prompt: str) -> str:
        return ''


def get_backend(name: str=None) -> AgentBackend:
    cfg = load_config()
    name = name or cfg['agent_backend']
    if name == 'claude':
        return ClaudeCodeBackend()
    return NullBackend()
