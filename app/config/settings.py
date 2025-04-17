import os

from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Application settings"""

    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
    DB_NAME = os.getenv("DB_NAME", "lark_messages")

    SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    LARK_COOKIE = os.getenv("LARK_COOKIE", "")
    LARK_BASE_URL = "https://internal-api-lark-api.feishu.cn/im/gateway/"
    LARK_CSRF_TOKEN_URL = "https://internal-api-lark-api.feishu.cn/accounts/csrf"
    LARK_USER_INFO_URL = "https://internal-api-lark-api.feishu.cn/accounts/web/user"
    LARK_WS_URL = "wss://msg-frontier.feishu.cn/ws/v2"
    
    FUNCTION_TRIGGER_FLAG = os.getenv("FUNCTION_TRIGGER_FLAG", "/run")

    AI_BOT_PREFIX = os.getenv("AI_BOT_PREFIX", "AI Bot:")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_API_BASE_URL = os.getenv("OPENAI_API_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    OPENAI_API_MODEL = os.getenv("OPENAI_API_MODEL", "qwen-plus")
    # ENVIRON = {}
    # for i in os.getenv("ENVIRON", "").split(";"):
    #     if '=' not in i:
    #         continue
    #     ENVIRON.update({i.split("=")[0]: i.split("=")[1]})


settings = Settings()
