import json
from datetime import datetime
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
from ..config import load_config
from .models import AgentSession, Base, Chat, Message


class Storage:
    def __init__(self, url: str=None):
        cfg = load_config()
        self.url = url or cfg['storage_url']
        self.engine = create_engine(self.url, pool_pre_ping=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def save_message(self, msg: dict, sender_name='', chat_name='', direction='in') -> bool:
        s = self.Session()
        try:
            exists = s.query(Message).filter_by(msg_id=str(msg['msg_id']), chat_id=str(msg['chat_id'])).first()
            if exists:
                return False
            row = Message(msg_id=str(msg['msg_id']), chat_id=str(msg['chat_id']), chat_name=chat_name or '', chat_type=msg.get('chat_type', 0), scope=msg.get('scope', 'chat'), anchor=msg.get('anchor', '') or '', root_id=msg.get('root_id', '') or '', parent_id=msg.get('parent_id', '') or '', sender_id=str(msg.get('from_id') or ''), sender_name=sender_name or '', msg_type=msg.get('msg_type', 0), msg_type_name=msg.get('msg_type_name', ''), content=msg.get('content', '') or '', content_data=json.dumps(msg.get('content_data'), ensure_ascii=False, default=str)[:20000] if msg.get('content_data') is not None else '', position=msg.get('position') or 0, create_time=msg.get('create_time') or 0, direction=direction)
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
