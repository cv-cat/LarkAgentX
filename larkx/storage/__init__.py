import json
from datetime import datetime
from sqlalchemy import and_, create_engine, desc, exists, func, or_
from sqlalchemy.orm import aliased, sessionmaker
from .. import accounts
from ..config import load_config
from .models import AgentSent, AgentSession, Base, Chat, Message, PendingMessage, Task


def _json_default(o):
    # 内联缩略图等原始字节对入库无用,转成字符串会撑爆长度上限、截断出非法 JSON
    if isinstance(o, (bytes, bytearray)):
        return f'<{len(o)} bytes>'
    return str(o)


def _without_echo_twins(q):
    """旧版 lark send 用本地 id 落库,WS 回显又插了一条,同一条消息存了两份。
    没有 position 的那份是多余的:只在读取时滤掉,不动用户数据。没有孪生的(监听没开时发的)照常显示。"""
    twin = aliased(Message)
    has_twin = exists().where(and_(twin.chat_id == Message.chat_id, twin.sender_id == Message.sender_id, twin.content == Message.content,
                                   twin.position > 0, func.abs(twin.create_time - Message.create_time) <= 60))
    return q.filter(or_(Message.position > 0, ~has_twin))


class Storage:
    def __init__(self, url: str=None, account_id: str=None):
        account_id = accounts.normalize(account_id)
        if url:
            self.url = url
        elif account_id == accounts.DEFAULT_ID:
            # 默认账号沿用 LARKX_STORAGE_URL(可切 MySQL);其它账号各用自己目录下的 SQLite
            self.url = load_config()['storage_url']
        else:
            accounts.home_of(account_id).mkdir(parents=True, exist_ok=True)
            self.url = f'sqlite:///{accounts.db_path(account_id)}'
        self.engine = create_engine(self.url, pool_pre_ping=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def close(self):
        self.engine.dispose()

    def save_sent(self, msg_id: str, chat_id: str, text: str, user_id: str, root_id: str=None, msg_type: int=4, msg_type_name: str='TEXT') -> bool:
        """发送成功后用服务端 id 落库,监听收到回显时会补全这条而不是再插一条。"""
        return self.save_message({'msg_id': msg_id, 'chat_id': chat_id, 'chat_type': 0, 'scope': 'topic' if root_id else 'chat', 'anchor': root_id or '', 'from_id': user_id, 'msg_type': msg_type, 'msg_type_name': msg_type_name, 'content': text, 'create_time': int(datetime.now().timestamp())}, sender_name='我', direction='out')

    def message_exists(self, msg_id: str, chat_id: str) -> bool:
        s = self.Session()
        try:
            return s.query(Message.id).filter_by(msg_id=str(msg_id), chat_id=str(chat_id)).first() is not None
        finally:
            s.close()

    def oldest_position(self, chat_id: str) -> int:
        s = self.Session()
        try:
            return s.query(func.min(Message.position)).filter(Message.chat_id == str(chat_id), Message.position > 0).scalar() or 0
        finally:
            s.close()

    def save_message(self, msg: dict, sender_name='', chat_name='', direction='in') -> bool:
        s = self.Session()
        try:
            fields = dict(msg_id=str(msg['msg_id']), chat_id=str(msg['chat_id']), chat_name=chat_name or '', chat_type=msg.get('chat_type', 0), scope=msg.get('scope', 'chat'), anchor=msg.get('anchor', '') or '', root_id=msg.get('root_id', '') or '', parent_id=msg.get('parent_id', '') or '', sender_id=str(msg.get('from_id') or ''), sender_name=sender_name or '', msg_type=msg.get('msg_type', 0), msg_type_name=msg.get('msg_type_name', ''), content=msg.get('content', '') or '', content_data=json.dumps(msg.get('content_data'), ensure_ascii=False, default=_json_default)[:20000] if msg.get('content_data') is not None else '', position=msg.get('position') or 0, create_time=msg.get('create_time') or 0, direction=direction)
            row = s.query(Message).filter_by(msg_id=fields['msg_id'], chat_id=fields['chat_id']).first()
            if row:
                # lark send 先落的记录没有 position;WS 回显到达时用回显补全,并视作首次入库
                if row.position or not fields['position']:
                    return False
                for k, v in fields.items():
                    setattr(row, k, v)
            else:
                row = Message(**fields)
                s.add(row)
            self._touch_chat(s, row)
            s.commit()
            return True
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def _touch_chat(self, s, row: Message):
        chat = s.query(Chat).filter_by(chat_id=row.chat_id).first()
        if not chat:
            chat = Chat(chat_id=row.chat_id, chat_type=row.chat_type)
            s.add(chat)
        if row.chat_name and (not chat.name):
            chat.name = row.chat_name
        if row.position and row.position > (chat.last_position or 0):
            chat.last_position = row.position
        chat.updated_at = datetime.now()

    def update_chat_name(self, chat_id: str, name: str, chat_type: int=0):
        s = self.Session()
        try:
            chat = s.query(Chat).filter_by(chat_id=str(chat_id)).first()
            if not chat:
                chat = Chat(chat_id=str(chat_id), chat_type=chat_type)
                s.add(chat)
            chat.name = name
            s.commit()
        finally:
            s.close()

    def list_chats(self, limit=50):
        s = self.Session()
        try:
            return s.query(Chat).order_by(desc(Chat.updated_at)).limit(limit).all()
        finally:
            s.close()

    def get_messages(self, chat_id: str, anchor: str=None, limit=50, before_ts: int=None):
        s = self.Session()
        try:
            q = s.query(Message).filter(Message.chat_id == str(chat_id))
            if anchor is not None:
                q = q.filter(Message.anchor == anchor)
            if before_ts:
                q = q.filter(Message.create_time < before_ts)
            rows = q.order_by(desc(Message.create_time)).limit(limit).all()
            rows.reverse()
            return rows
        finally:
            s.close()

    def daily_counts(self, days=7, now=None):
        """最近 days 天(含今天)每天的收/发消息数。按本地日期分桶,在 Python 里做以兼容 SQLite/MySQL。"""
        from datetime import timedelta
        today = datetime.fromtimestamp(now).date() if now else datetime.now().date()
        start = today - timedelta(days=days - 1)
        cutoff = int(datetime.combine(start, datetime.min.time()).timestamp())
        buckets = {start + timedelta(days=i): {'in': 0, 'out': 0} for i in range(days)}
        s = self.Session()
        try:
            for ts, direction in _without_echo_twins(s.query(Message.create_time, Message.direction)).filter(Message.create_time >= cutoff).all():
                d = datetime.fromtimestamp(ts).date()
                if d in buckets and direction in ('in', 'out'):
                    buckets[d][direction] += 1
        finally:
            s.close()
        return [{'date': d.strftime('%m-%d'), **v} for d, v in buckets.items()]

    def chat_summaries(self, limit=200, me: str=''):
        """会话列表: 每个会话的名称/类型/消息数/最后一条消息/对方 id,按最后消息时间倒序。"""
        s = self.Session()
        try:
            latest = (_without_echo_twins(s.query(Message.chat_id, func.max(Message.create_time).label('t'), func.count(Message.id).label('n')))
                      .group_by(Message.chat_id).subquery())
            rows = (_without_echo_twins(s.query(Message, latest.c.n)
                    .join(latest, (Message.chat_id == latest.c.chat_id) & (Message.create_time == latest.c.t)))
                    .order_by(desc(Message.create_time), desc(Message.id)).all())
            peers = dict(s.query(Message.chat_id, func.max(Message.sender_id))
                         .filter(Message.sender_id != str(me), Message.sender_id != '').group_by(Message.chat_id).all())
            names = {c.chat_id: (c.name, c.chat_type) for c in s.query(Chat).all()}
            out, seen = [], set()
            for m, n in rows:
                if m.chat_id in seen:      # 同一秒的多条只取最新一条
                    continue
                seen.add(m.chat_id)
                name, ctype = names.get(m.chat_id, ('', 0))
                out.append({'chat_id': m.chat_id, 'name': name or m.chat_name or '', 'chat_type': ctype or m.chat_type,
                            'count': n, 'last_time': m.create_time, 'last_sender': m.sender_name or m.sender_id,
                            'last_direction': m.direction, 'last_content': (m.content or '')[:80],
                            'peer_id': peers.get(m.chat_id, '')})
                if len(out) >= limit:
                    break
            return out
        finally:
            s.close()

    def topic_summaries(self, chat_id: str):
        """某会话下的话题(anchor 非空)及各自消息数、最近时间。"""
        s = self.Session()
        try:
            rows = (s.query(Message.anchor, func.count(Message.id), func.max(Message.create_time))
                    .filter(Message.chat_id == str(chat_id), Message.anchor != '')
                    .group_by(Message.anchor).all())
            out = []
            for anchor, n, last in rows:
                first = (s.query(Message).filter(Message.chat_id == str(chat_id), Message.anchor == anchor)
                         .order_by(Message.create_time, Message.id).first())
                out.append({'anchor': anchor, 'count': n, 'last_time': last, 'title': (first.content or '')[:40] if first else ''})
            out.sort(key=lambda t: t['last_time'] or 0, reverse=True)
            return out
        finally:
            s.close()

    def recent_messages(self, limit=30):
        s = self.Session()
        try:
            return _without_echo_twins(s.query(Message)).order_by(desc(Message.create_time), desc(Message.id)).limit(limit).all()
        finally:
            s.close()

    def message_counts(self) -> dict:
        s = self.Session()
        try:
            rows = _without_echo_twins(s.query(Message.direction, func.count(Message.id))).group_by(Message.direction).all()
            return {d: n for d, n in rows}
        finally:
            s.close()

    def chat_page(self, chat_id: str, anchor: str=None, before: tuple=None, limit=50):
        """倒序翻页取一页消息(返回按时间正序)。before 是上一页最老那条的 (create_time, id):
        回填的历史主键比新消息大,不能按主键排;带上主键是为了同一秒的消息不漏页。"""
        s = self.Session()
        try:
            q = _without_echo_twins(s.query(Message)).filter(Message.chat_id == str(chat_id))
            if anchor is not None:
                q = q.filter(Message.anchor == anchor)
            if before:
                q = q.filter(or_(Message.create_time < before[0], and_(Message.create_time == before[0], Message.id < before[1])))
            rows = q.order_by(desc(Message.create_time), desc(Message.id)).limit(limit + 1).all()
            has_more = len(rows) > limit
            rows = rows[:limit]
            rows.reverse()
            return rows, has_more
        finally:
            s.close()

    def get_chat_name(self, chat_id: str) -> str:
        s = self.Session()
        try:
            chat = s.query(Chat).filter_by(chat_id=str(chat_id)).first()
            return chat.name if chat else ''
        finally:
            s.close()

    def session_get(self, session_key: str):
        s = self.Session()
        try:
            return s.query(AgentSession).filter_by(session_key=session_key).first()
        finally:
            s.close()

    def session_upsert(self, session_key: str, chat_id: str, anchor: str, agent_session_id: str, started: bool):
        s = self.Session()
        try:
            row = s.query(AgentSession).filter_by(session_key=session_key).first()
            if not row:
                row = AgentSession(session_key=session_key, chat_id=chat_id, anchor=anchor or '')
                s.add(row)
            row.agent_session_id = agent_session_id
            row.started = 1 if started else 0
            s.commit()
        finally:
            s.close()

    def session_touch(self, session_key: str):
        s = self.Session()
        try:
            row = s.query(AgentSession).filter_by(session_key=session_key).first()
            if row:
                row.msg_count = (row.msg_count or 0) + 1
                row.last_active = datetime.now()
                s.commit()
        finally:
            s.close()

    def list_sessions(self, limit=50):
        s = self.Session()
        try:
            return s.query(AgentSession).order_by(desc(AgentSession.last_active)).limit(limit).all()
        finally:
            s.close()

    # ---- 交给 agent 还没处理完的消息 ----
    def pending_add(self, session_key: str, payload: dict) -> int:
        s = self.Session()
        try:
            row = PendingMessage(session_key=session_key, payload=json.dumps(payload, ensure_ascii=False, default=_json_default),
                                 created_at=int(datetime.now().timestamp()))
            s.add(row)
            s.commit()
            return row.id
        finally:
            s.close()

    def pending_done(self, pending_id: int):
        s = self.Session()
        try:
            s.query(PendingMessage).filter(PendingMessage.id == pending_id).delete()
            s.commit()
        finally:
            s.close()

    def pending_clear(self, session_key: str = None):
        s = self.Session()
        try:
            q = s.query(PendingMessage)
            if session_key is not None:
                q = q.filter(PendingMessage.session_key == session_key)
            q.delete()
            s.commit()
        finally:
            s.close()

    def pending_all(self) -> list:
        """[(id, session_key, payload, created_at)],按先后顺序。"""
        s = self.Session()
        try:
            rows = s.query(PendingMessage).order_by(PendingMessage.id).all()
            return [(r.id, r.session_key, json.loads(r.payload), r.created_at) for r in rows]
        finally:
            s.close()

    # ---- 定时任务 ----
    def task_add(self, chat_id: str, anchor: str, kind: str, content: str, run_at: int = 0, daily_at: str = '', created_by: str = 'user') -> int:
        s = self.Session()
        try:
            row = Task(chat_id=str(chat_id), anchor=anchor or '', kind=kind, run_at=int(run_at), daily_at=daily_at, content=content, created_by=created_by)
            s.add(row)
            s.commit()
            return row.id
        finally:
            s.close()

    def task_list(self) -> list:
        s = self.Session()
        try:
            return s.query(Task).order_by(Task.run_at, Task.id).all()
        finally:
            s.close()

    def task_remove(self, task_id: int) -> bool:
        s = self.Session()
        try:
            n = s.query(Task).filter(Task.id == int(task_id)).delete()
            s.commit()
            return n > 0
        finally:
            s.close()

    def task_reschedule(self, task_id: int, run_at: int):
        s = self.Session()
        try:
            s.query(Task).filter(Task.id == int(task_id)).update({'run_at': int(run_at)})
            s.commit()
        finally:
            s.close()

    def p2p_peers(self, chat_ids, me: str = '') -> dict:
        """{私聊会话 id: 对方 user_id},从本地消息里找不是我发的那一方。"""
        chat_ids = [str(c) for c in chat_ids]
        if not chat_ids:
            return {}
        s = self.Session()
        try:
            return dict(s.query(Message.chat_id, func.max(Message.sender_id))
                        .filter(Message.chat_id.in_(chat_ids), Message.sender_id != str(me), Message.sender_id != '')
                        .group_by(Message.chat_id).all())
        finally:
            s.close()

    def chat_info(self, chat_ids) -> dict:
        """{chat_id: (名字, chat_type)},只含本地有记录的。"""
        chat_ids = [str(c) for c in chat_ids]
        if not chat_ids:
            return {}
        s = self.Session()
        try:
            return {r.chat_id: (r.name or '', r.chat_type or 0) for r in s.query(Chat).filter(Chat.chat_id.in_(chat_ids)).all()}
        finally:
            s.close()

    def sender_names(self, user_ids) -> dict:
        """这些人在本地消息里出现过的名字 {user_id: name}。"""
        user_ids = [str(u) for u in user_ids]
        if not user_ids:
            return {}
        s = self.Session()
        try:
            rows = (s.query(Message.sender_id, Message.sender_name)
                    .filter(Message.sender_id.in_(user_ids), Message.sender_name != '', Message.sender_name != '我').all())
            return {uid: name for uid, name in rows}
        finally:
            s.close()

    def mark_recalled(self, msg_id: str):
        """撤回后本地也标一下,聊天记录里不再显示原文。"""
        s = self.Session()
        try:
            s.query(Message).filter(Message.msg_id == str(msg_id)).update({'content': '[已撤回]'})
            s.commit()
        finally:
            s.close()

    # ---- agent 发出的消息 ----
    def mark_agent_sent(self, msg_id: str, chat_id: str):
        s = self.Session()
        try:
            if not s.get(AgentSent, str(msg_id)):
                s.add(AgentSent(msg_id=str(msg_id), chat_id=str(chat_id)))
                s.commit()
        finally:
            s.close()

    def agent_sent_ids(self, msg_ids) -> set:
        msg_ids = [str(m) for m in msg_ids if m]
        if not msg_ids:
            return set()
        s = self.Session()
        try:
            return {r.msg_id for r in s.query(AgentSent.msg_id).filter(AgentSent.msg_id.in_(msg_ids)).all()}
        finally:
            s.close()

    # ---- 补收 ----
    def catchup_range(self, chat_id: str, before_ts: int) -> tuple:
        """补收用: (起点, 起点之后本地已有的 position 集合)。起点是 before_ts 之前本地最后一条消息的 position,没有就是 0。
        只按 before_ts 之前的消息定起点: 长连接后来推到的新消息不会把中间漏掉的那段跳过去。"""
        s = self.Session()
        try:
            base = (s.query(func.max(Message.position))
                    .filter(Message.chat_id == str(chat_id), Message.position > 0, Message.create_time < int(before_ts)).scalar() or 0)
            have = {p for (p,) in s.query(Message.position).filter(Message.chat_id == str(chat_id), Message.position > base)}
            return base, have
        finally:
            s.close()

    def latest_message_time(self) -> int:
        s = self.Session()
        try:
            return int(s.query(func.max(Message.create_time)).filter(Message.position > 0).scalar() or 0)
        finally:
            s.close()

    def last_out_content(self, chat_id: str) -> str:
        """这个会话里最近一条我发出的消息内容。"""
        s = self.Session()
        try:
            row = (s.query(Message.content).filter(Message.chat_id == str(chat_id), Message.direction == 'out')
                   .order_by(desc(Message.create_time), desc(Message.id)).first())
            return (row[0] or '').strip() if row else ''
        finally:
            s.close()

    def messages_since(self, since_ts: int, limit: int = 500) -> list:
        """since_ts 之后的消息(按时间正序,最多 limit 条,取最新的那些)。每日回顾用。"""
        s = self.Session()
        try:
            rows = (_without_echo_twins(s.query(Message)).filter(Message.create_time >= int(since_ts))
                    .order_by(desc(Message.create_time), desc(Message.id)).limit(limit).all())
            rows.reverse()
            return rows
        finally:
            s.close()
