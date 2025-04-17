from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


class Message(Base):
    """Model for storing Lark chat messages"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(String(255), nullable=False, comment="User display name")
    user_id = Column(String(255), nullable=False, comment="User ID from Lark")
    content = Column(Text, nullable=False, comment="Message content")
    is_group_chat = Column(Boolean, default=False, comment="Whether the message is from a group chat")
    group_name = Column(String(255), nullable=True, comment="Group chat name (if applicable)")
    chat_id = Column(String(255), nullable=False, comment="Chat ID")
    message_time = Column(DateTime, default=datetime.now, comment="Time when the message was sent")
    created_at = Column(DateTime, default=func.now(), comment="Record creation time")

    def __repr__(self):
        return f"<Message(id={self.id}, user_name='{self.user_name}', content='{self.content[:20]}...', is_group_chat={self.is_group_chat})>"


class Schedule(Base):
    """Model for Scheduled task"""
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    module_name = Column(String(255), nullable=False, comment="Module name")
    function_name = Column(String(255), nullable=False, comment="Function name")
    arguments = Column(JSON, nullable=True, comment="Arguments")
    cron = Column(String(255), nullable=False, comment="Cron")
    active = Column(Boolean, default=True, comment="Whether the schedule is active")
    created_at = Column(DateTime, default=func.now(), comment="Record creation time")
    created_by = Column(String(255), nullable=False, comment="Username from Lark")

    def __repr__(self):
        return f"<Schedule(id={self.id}, module_name='{self.module_name}', function_name='{self.function_name}', arguments='{self.arguments}', created_by='{self.created_by}', cron='{self.cron}', active={self.active})>"