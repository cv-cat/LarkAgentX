"""长期记忆:每个账号一个 memory.md,条目之间用 § 分隔,每条一句话。

列在「只处理这些会话」里的会话(私聊或群聊)各有一份独立记忆 memories/<会话id>.md,
那个会话里的 agent 只读写它自己的;没列出的会话(比如和自己的会话)共用 memory.md。

总长度有硬上限(MEMORY_LIMIT 字),写满了 add 直接失败,由 agent 自己删掉或合并旧条目腾出地方,
不会悄悄丢掉内容。记忆不是每条消息都附带:同一个会话第一次处理消息、或者记忆有变化时才附上最新版,
避免会话历史越堆越长。
"""
import os
import re
from pathlib import Path

from . import accounts
from .locks import FileLock

MEMORY_LIMIT = 2000
SEPARATOR = '\n§\n'


class MemoryEditError(Exception):
    pass


_CHAT_ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


def scope_for(cfg: dict, chat_id) -> str:
    """这个会话用哪份记忆: 在「只处理这些会话」名单里就是它自己的(返回会话 id),否则共用(返回空)。"""
    chat_id = str(chat_id or '')
    listed = [str(c) for c in ((cfg or {}).get('triggers') or {}).get('include_chats') or []]
    return chat_id if chat_id and chat_id in listed else ''


def path_of(account_id: str = None, chat: str = '') -> Path:
    if chat:
        if not _CHAT_ID.match(str(chat)):
            raise MemoryEditError('会话 id 不合法')
        return accounts.home_of(account_id) / 'memories' / f'{chat}.md'
    return accounts.home_of(account_id) / 'memory.md'


def entries(account_id: str = None, chat: str = '') -> list:
    p = path_of(account_id, chat)
    if not p.exists():
        return []
    text = p.read_text(encoding='utf-8')
    return [e.strip() for e in text.split('§') if e.strip()]


def used(items: list) -> int:
    return sum(len(e) for e in items)


def _write(account_id: str, items: list, chat: str = ''):
    p = path_of(account_id, chat)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.md.tmp')
    tmp.write_text(SEPARATOR.join(items) + ('\n' if items else ''), encoding='utf-8')
    os.replace(tmp, p)


def _change(account_id: str, fn, chat: str = ''):
    """加锁读-改-写,多个会话同时改也不会互相覆盖。fn 收到当前条目,返回新条目。"""
    p = path_of(account_id, chat)
    p.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(p.with_suffix('.lock')):
        items = fn(entries(account_id, chat))
        if used(items) > MEMORY_LIMIT:
            raise MemoryEditError(f'记忆已用 {used(entries(account_id, chat))}/{MEMORY_LIMIT} 字,改完会超出上限。'
                               f'先用 lark memory rm 删掉过时的条目,或用 lark memory edit 合并精简,再重试。')
        _write(account_id, items, chat)
        return items


def _clean(text: str) -> str:
    text = ' '.join((text or '').replace('§', ' ').split())
    if not text:
        raise MemoryEditError('内容不能为空')
    return text


def _index(items: list, n: int) -> int:
    if not 1 <= n <= len(items):
        raise MemoryEditError(f'没有第 {n} 条(共 {len(items)} 条)')
    return n - 1


def add(account_id: str, text: str, chat: str = '') -> list:
    text = _clean(text)

    def fn(items):
        if text in items:
            raise MemoryEditError('已经有这一条了')
        return items + [text]
    return _change(account_id, fn, chat)


def edit(account_id: str, n: int, text: str, chat: str = '') -> list:
    text = _clean(text)

    def fn(items):
        items = list(items)
        items[_index(items, n)] = text
        return items
    return _change(account_id, fn, chat)


def remove(account_id: str, n: int, chat: str = '') -> list:
    def fn(items):
        items = list(items)
        items.pop(_index(items, n))
        return items
    return _change(account_id, fn, chat)


def usage_text(items: list) -> str:
    return f'已用 {used(items)}/{MEMORY_LIMIT} 字'


REVIEW_MAX_MESSAGES = 500
REVIEW_MAX_CHARS = 200
REVIEW_PROMPT = ('现在是每日回顾:下面是最近 24 小时的聊天记录。请据此整理长期记忆:'
                 '新出现的、值得长期记住的事(人物、偏好、约定、待办)用 lark memory add "内容"{acct} 记下;'
                 '过时的、已经办完的用 lark memory rm 编号{acct} 删掉;重复或啰嗦的用 lark memory edit 编号 "内容"{acct} 合并精简。'
                 '记忆要保持精简,宁缺毋滥。不要给任何人发消息,整理完直接结束。')


def review_transcript(storage, since_ts: int, my_user_id: str = '', exclude_chats=()) -> str:
    """每日回顾要读的聊天记录:最多 REVIEW_MAX_MESSAGES 条,每条最多 REVIEW_MAX_CHARS 字。
    exclude_chats: 有独立记忆的会话,它们的内容不能进共用记忆。"""
    lines, chat = [], None
    exclude = {str(c) for c in exclude_chats}
    for m in storage.messages_since(since_ts, REVIEW_MAX_MESSAGES):
        if str(m.chat_id) in exclude:
            continue
        name = m.chat_name or storage.get_chat_name(m.chat_id) or m.chat_id
        if name != chat:
            chat = name
            lines.append(f'## {name}')
        who = '我' if my_user_id and str(m.sender_id) == str(my_user_id) else (m.sender_name or m.sender_id)
        text = ' '.join((m.content or '').split())
        lines.append(f'{who}: {text[:REVIEW_MAX_CHARS]}')
    return '\n'.join(lines)


def prompt_block(account_id: str, chat: str = '') -> str:
    """附在给 agent 的消息前面的记忆和用法说明。chat 非空: 这个会话的独立记忆。"""
    items = entries(account_id, chat)
    acct = '' if accounts.normalize(account_id) == accounts.DEFAULT_ID else f' --account {account_id}'
    lines = ['<memory>']
    lines += [f'{i}. {e}' for i, e in enumerate(items, 1)] or ['(还没有记忆)']
    lines.append('</memory>')
    whose = '这个会话独立的长期记忆,只在这个会话里可见' if chat else '你的长期记忆,没有单独设置的会话共用'
    lines.append(f'以上是{whose}({usage_text(items)})。值得长期记住的事(人物、偏好、约定、待办)'
                 f'用 lark memory add "内容"{acct} 记下,一条一句话,开头写人名或会话名;过时的用 lark memory rm 编号{acct} 删掉,'
                 f'要改用 lark memory edit 编号 "内容"{acct}。写满了会失败,先删或合并旧的。不要把一个会话里的事透露给其他会话里的人。')
    return '\n'.join(lines)
