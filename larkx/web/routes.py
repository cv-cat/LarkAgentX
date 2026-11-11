import asyncio
import re
from typing import Literal, Optional

from fastapi import APIRouter, Query
from fastapi.responses import Response

from ..auth import AuthExpired
from .manager import Manager, NotFound
from .schemas import AccountCreate, AddAccount, ChatAgentIn, CookieLogin, HistoryIn, LoginStart, MemoryIn, ResetIn, SendIn, SettingsIn

_CURSOR = re.compile(r'^(\d+)_(\d+)$')
_IDENT = r'^[A-Za-z0-9_-]{1,64}$'


def _parse_cursor(before: Optional[str]) -> Optional[tuple]:
    m = _CURSOR.match(before or '')
    return (int(m.group(1)), int(m.group(2))) if m else None


def build_router(mgr: Manager, auth_required: bool) -> APIRouter:
    r = APIRouter()

    @r.get('/meta')
    async def meta():
        return {**mgr.meta(), 'auth_required': auth_required}

    @r.get('/runtimes')
    async def runtimes():
        # 起子进程查版本会阻塞,放线程里跑,别卡住事件循环
        return await asyncio.to_thread(mgr.runtimes)

    @r.get('/accounts')
    async def list_accounts():
        return mgr.list()

    @r.post('/accounts')
    async def create_account(body: AccountCreate):
        return mgr.create(body.name, body.region)

    @r.post('/accounts/add')
    async def add_account(body: AddAccount):
        return await asyncio.to_thread(mgr.add_by_qr, body.region)

    @r.get('/accounts/{account_id}')
    async def get_account(account_id: str):
        return mgr.describe(mgr.require(account_id))

    @r.delete('/accounts/{account_id}')
    async def delete_account(account_id: str):
        await mgr.delete(account_id)
        return {'ok': True}

    @r.get('/accounts/{account_id}/avatars/{kind}/{ident}')
    async def avatar(account_id: str, kind: Literal['user', 'chat'], ident: str):
        if not re.match(_IDENT, ident):
            return Response(status_code=404)
        data, ctype = await asyncio.to_thread(mgr.avatar, account_id, kind, ident)
        if not data:
            # 失败不让浏览器缓存: 后端自己有失败缓存(重新登录时清掉),浏览器再缓存会拖住重新登录后的恢复
            return Response(status_code=404, headers={'Cache-Control': 'no-store'})
        return Response(data, media_type=ctype, headers={'Cache-Control': 'private, max-age=3600'})

    @r.post('/accounts/{account_id}/start')
    async def start(account_id: str):
        return await mgr.start(account_id)

    @r.post('/accounts/{account_id}/stop')
    async def stop(account_id: str):
        return await mgr.stop(account_id)

    @r.post('/accounts/{account_id}/restart')
    async def restart(account_id: str):
        return await mgr.restart(account_id)

    @r.get('/accounts/{account_id}/settings')
    async def get_settings(account_id: str):
        return mgr.get_settings(account_id)

    @r.put('/accounts/{account_id}/settings')
    async def put_settings(account_id: str, body: SettingsIn):
        return mgr.save_settings(account_id, body.model_dump())

    @r.post('/accounts/{account_id}/login/qr')
    async def login_qr(account_id: str, body: LoginStart = None):
        return mgr.start_login(account_id, body.region if body else None)

    @r.get('/accounts/{account_id}/login/status')
    async def login_status(account_id: str):
        return mgr.login_status(account_id)

    @r.delete('/accounts/{account_id}/login')
    async def login_cancel(account_id: str):
        mgr.cancel_add(account_id)
        return {'ok': True}

    @r.post('/accounts/{account_id}/login/cookie')
    async def login_cookie(account_id: str, body: CookieLogin):
        msg = await asyncio.to_thread(mgr.cookie_login, account_id, body.cookie, body.region)
        return {'ok': True, 'message': msg}

    @r.get('/accounts/{account_id}/overview')
    async def overview(account_id: str):
        return mgr.overview(account_id)

    @r.get('/accounts/{account_id}/stats')
    async def stats(account_id: str):
        return mgr.stats(account_id)

    @r.get('/accounts/{account_id}/chats')
    async def chats(account_id: str):
        return mgr.chats(account_id)

    @r.get('/accounts/{account_id}/chats/{chat_id}/topics')
    async def topics(account_id: str, chat_id: str):
        return mgr.topics(account_id, chat_id)

    @r.get('/accounts/{account_id}/chats/{chat_id}/messages')
    async def chat_messages(account_id: str, chat_id: str, anchor: Optional[str] = None,
                            before: Optional[str] = Query(None, pattern=r'^\d+_\d+$'), limit: int = Query(50, ge=1, le=200)):
        return mgr.chat_messages(account_id, chat_id, anchor=anchor, before=_parse_cursor(before), limit=limit)

    @r.post('/accounts/{account_id}/chats/{chat_id}/messages')
    async def send_message(account_id: str, chat_id: str, body: SendIn):
        return await asyncio.to_thread(mgr.send_message, account_id, chat_id, body.text, body.root_id)

    @r.post('/accounts/{account_id}/chats/{chat_id}/history')
    async def pull_history(account_id: str, chat_id: str, body: HistoryIn = None):
        return await asyncio.to_thread(mgr.pull_history, account_id, chat_id, body.count if body else 50)

    @r.put('/accounts/{account_id}/chats/{chat_id}/agent')
    async def chat_agent(account_id: str, chat_id: str, body: ChatAgentIn):
        return mgr.set_chat_agent(account_id, chat_id, body.enabled)

    @r.post('/accounts/{account_id}/chats/{chat_id}/reset')
    async def chat_reset(account_id: str, chat_id: str, body: ResetIn = None):
        return mgr.reset_session(account_id, chat_id, body.anchor if body else '')

    @r.get('/accounts/{account_id}/people')
    async def people(account_id: str, q: str = Query('', max_length=50), ids: str = Query('', max_length=4000)):
        """q: 按名字搜人;ids: 逗号分隔的 user_id,取名字。"""
        try:
            return await asyncio.to_thread(mgr.people, account_id, q.strip(), [i for i in ids.split(',') if i])
        except (AuthExpired, NotFound):
            raise
        except Exception as e:
            raise ValueError(f'搜索失败: {e}')

    @r.get('/accounts/{account_id}/chat-targets')
    async def chat_targets(account_id: str, q: str = Query('', max_length=50), ids: str = Query('', max_length=4000),
                           groups: bool = False):
        """q: 按名字搜人和群(groups=true 只搜群);ids: 逗号分隔的会话 id,取名字和类型(私聊/群聊)。"""
        try:
            return await asyncio.to_thread(mgr.chat_targets, account_id, q.strip(), [i for i in ids.split(',') if i], groups)
        except (AuthExpired, NotFound):
            raise
        except Exception as e:
            raise ValueError(f'搜索失败: {e}')

    @r.get('/accounts/{account_id}/dm-chat')
    async def dm_chat(account_id: str, user: str = Query(..., max_length=64), name: str = Query('', max_length=100)):
        """和某人的私聊会话 id,往会话名单里加人时用。"""
        try:
            return await asyncio.to_thread(mgr.dm_chat, account_id, user, name)
        except (AuthExpired, NotFound, ValueError):
            raise
        except Exception as e:
            raise ValueError(f'获取私聊会话失败: {e}')

    @r.get('/accounts/{account_id}/memory')
    async def get_memory(account_id: str, chat: str = Query('', max_length=64)):
        return mgr.memory(account_id, chat)

    @r.post('/accounts/{account_id}/memory')
    async def add_memory(account_id: str, body: MemoryIn, chat: str = Query('', max_length=64)):
        return await asyncio.to_thread(mgr.memory_change, account_id, 'add', text=body.text, chat=chat)

    @r.put('/accounts/{account_id}/memory/{n}')
    async def edit_memory(account_id: str, n: int, body: MemoryIn, chat: str = Query('', max_length=64)):
        return await asyncio.to_thread(mgr.memory_change, account_id, 'edit', n=n, text=body.text, chat=chat)

    @r.delete('/accounts/{account_id}/memory/{n}')
    async def remove_memory(account_id: str, n: int, chat: str = Query('', max_length=64)):
        return await asyncio.to_thread(mgr.memory_change, account_id, 'rm', n=n, chat=chat)

    @r.post('/accounts/{account_id}/memory/review')
    async def review_memory(account_id: str):
        return await asyncio.to_thread(mgr.memory_review, account_id)

    @r.get('/accounts/{account_id}/tasks')
    async def list_tasks(account_id: str):
        return mgr.tasks(account_id)

    @r.delete('/accounts/{account_id}/tasks/{task_id}')
    async def remove_task(account_id: str, task_id: int):
        return mgr.remove_task(account_id, task_id)

    @r.get('/accounts/{account_id}/logs')
    async def logs(account_id: str, since: int = 0):
        mgr.require(account_id)
        return mgr.logs.get(account_id, since)

    return r
