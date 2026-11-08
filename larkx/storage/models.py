from datetime import datetime
from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base
Base = declarative_base()


class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True, autoincrement=True)
    msg_id = Column(String(32), nullable=False)
    chat_id = Column(String(32), nullable=False, index=True)
    chat_name = Column(String(256), default='')
    chat_type = Column(Integer, default=0)
    scope = Column(String(8), default='chat')
    anchor = Column(String(32), default='', index=True)
    root_id = Column(String(32), default='')
    parent_id = Column(String(32), default='')
    sender_id = Column(String(32), default='')
    sender_name = Column(String(256), default='')
    msg_type = Column(Integer, default=0)
    msg_type_name = Column(String(32), default='')
    content = Column(Text, default='')
    content_data = Column(Text, default='')
    position = Column(Integer, default=0)
    create_time = Column(BigInteger, default=0)
    direction = Column(String(4), default='in')
    stored_at = Column(DateTime, default=datetime.now)
    __table_args__ = (UniqueConstraint('msg_id', 'chat_id', name='uq_msg_chat'), Index('ix_chat_anchor_time', 'chat_id', 'anchor', 'create_time'))


class Chat(Base):
    __tablename__ = 'chats'
    chat_id = Column(String(32), primary_key=True)
    name = Column(String(256), default='')
    chat_type = Column(Integer, default=0)
    last_position = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class AgentSession(Base):
    __tablename__ = 'agent_sessions'

    session_key = Column(String(80), primary_key=True)
    chat_id = Column(String(32), default='', index=True)
    anchor = Column(String(32), default='')
    agent_session_id = Column(String(64), default='')
    started = Column(Integer, default=0)
    msg_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    last_active = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class PendingMessage(Base):
    """交给 agent、还没处理完的消息。处理完就删;重启后接着处理。"""
    __tablename__ = 'pending_messages'
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_key = Column(String(80), nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(BigInteger, default=0)


class Task(Base):
    """定时任务。once: 到 run_at 执行一次;daily: 每天 daily_at(HH:MM)执行。到点后交给创建它的那个会话的 agent。"""
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String(32), nullable=False)
    anchor = Column(String(32), default='')
    kind = Column(String(8), nullable=False)
    run_at = Column(BigInteger, default=0)
    daily_at = Column(String(5), default='')
    content = Column(Text, nullable=False)
    created_by = Column(String(8), default='user')
    created_at = Column(DateTime, default=datetime.now)


class AgentSent(Base):
    """agent 发出的消息,聊天记录里据此标出来。"""
    __tablename__ = 'agent_sent'
    msg_id = Column(String(32), primary_key=True)
    chat_id = Column(String(32), default='')
