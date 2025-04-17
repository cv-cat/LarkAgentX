from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
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