"""
Database session management and initialization
"""
from loguru import logger
from app.db.models import Base
from app.config.settings import settings
from sqlalchemy import create_engine, text, exc
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool

def get_db_uri_without_db():
    """获取不包含特定数据库名的URI"""
    uri_parts = settings.SQLALCHEMY_DATABASE_URI.split('/')
    uri_parts[-1] = ''
    return '/'.join(uri_parts)

def create_database_if_not_exists():
    """如果数据库不存在则创建"""
    try:
        uri = get_db_uri_without_db()
        temp_engine = create_engine(uri)
        
        with temp_engine.connect() as conn:
            create_db_sql = text(f"CREATE DATABASE IF NOT EXISTS {settings.DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            conn.execute(create_db_sql)
            conn.commit()
        
        logger.info(f"数据库 '{settings.DB_NAME}' 已确认存在或已创建")
    except Exception as e:
        logger.error(f"创建数据库时出错: {str(e)}")
        raise

engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True,
    pool_timeout=30,
    poolclass=QueuePool
)

session_factory = sessionmaker(bind=engine)
SessionLocal = scoped_session(session_factory)

def init_db():
    """初始化数据库，如果不存在则创建"""
    try:
        create_database_if_not_exists()
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.error(f"初始化数据库时出错: {str(e)}")
        raise

def get_db_session():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise

def close_db_session(db):
    """关闭数据库会话"""
    if db:
        db.close() 