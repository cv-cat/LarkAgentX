import json
import os
from pathlib import Path

from dotenv import load_dotenv

# 测试里设 LARKX_NO_DOTENV=1,不读本机的 .env,免得本地配置影响测试结果
if not os.environ.get('LARKX_NO_DOTENV'):
    load_dotenv()

_home_env = os.environ.get("LARKX_HOME") or str(Path.home() / ".larkx")
DATA_DIR = Path(os.path.expanduser(_home_env))
CREDENTIALS_PATH = DATA_DIR / "credentials.json"
DB_DEFAULT_PATH = DATA_DIR / "messages.db"

DEFAULTS = {
    "region": "feishu",
    "storage_url": f"sqlite:///{DB_DEFAULT_PATH}",
    "context_scope": "anchor",
    "agent_backend": "claude",
    "agent_model": "",
    "workdir": "",
    "agent_timeout": 7200,
    "system_prompt": "",
    "mark_read": True,
    "reply_in_topic": True,
    "reply_mode": "direct",
    "reply_signature": "",
    "ack_reaction": False,
    "deny_reply": "",
    "memory_enabled": False,
    "memory_review_at": "00:00",
    "chat_configs": [],        # [{chat_id, workdir}]「只处理这些会话」里每个会话(私聊或群聊)单独的设置
    "triggers": {
        "prefix": "",
        "chat_types": [],
        "include_chats": [],
        "exclude_chats": [],
        "include_senders": [],
        "exclude_senders": [],
        "keywords": [],
        "group_at_only": False,
        "dm_enabled": True,
        "self_chat_enabled": False,
    },
}

# 可以按账号覆盖(web 里设置)的配置项
SETTING_KEYS = ("agent_backend", "agent_model", "workdir", "agent_timeout", "system_prompt", "context_scope", "mark_read", "reply_in_topic",
                "reply_mode", "reply_signature", "ack_reaction", "deny_reply", "memory_enabled", "memory_review_at", "triggers",
                "chat_configs")

TRIGGER_ENV = {
    "prefix": "LARKX_TRIGGER_PREFIX",
    "chat_types": "LARKX_TRIGGER_CHAT_TYPES",
    "include_chats": "LARKX_TRIGGER_INCLUDE_CHATS",
    "exclude_chats": "LARKX_TRIGGER_EXCLUDE_CHATS",
    "include_senders": "LARKX_TRIGGER_INCLUDE_SENDERS",
    "exclude_senders": "LARKX_TRIGGER_EXCLUDE_SENDERS",
    "keywords": "LARKX_TRIGGER_KEYWORDS",
    "group_at_only": "LARKX_TRIGGER_GROUP_AT_ONLY",
    "dm_enabled": "LARKX_TRIGGER_DM_ENABLED",
    "self_chat_enabled": "LARKX_TRIGGER_SELF_CHAT_ENABLED",
}


def _as_list(v: str):
    v = v.strip()
    if v.startswith("["):
        try:
            return json.loads(v)
        except Exception:
            return []
    return [x.strip() for x in v.split(",") if x.strip()]


def _as_bool(v: str):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _as_seconds(v) -> int:
    try:
        return max(0, int(float(v)))
    except (TypeError, ValueError):
        return 0


def load_config(overrides: dict = None) -> dict:
    """默认值 < 环境变量/.env < overrides(账号在 web 里保存的设置)。"""
    cfg = dict(DEFAULTS)
    for key in cfg:
        if key == "triggers":
            continue
        v = os.environ.get("LARKX_" + key.upper())
        if v:
            cfg[key] = v
    for flag in ("mark_read", "reply_in_topic", "ack_reaction", "memory_enabled"):
        if isinstance(cfg.get(flag), str):
            cfg[flag] = _as_bool(cfg[flag])
    triggers = dict(DEFAULTS["triggers"])
    for key, env_name in TRIGGER_ENV.items():
        v = os.environ.get(env_name)
        if v is None:
            continue
        if key in ("group_at_only", "dm_enabled", "self_chat_enabled"):
            triggers[key] = _as_bool(v)
        elif isinstance(DEFAULTS["triggers"][key], list):
            triggers[key] = _as_list(v)
        else:
            triggers[key] = v
    cfg["triggers"] = triggers
    for key, v in (overrides or {}).items():
        if key == "triggers" and isinstance(v, dict):
            cfg["triggers"] = {**triggers, **v}
        elif key in SETTING_KEYS:
            cfg[key] = v
    cfg["agent_timeout"] = _as_seconds(cfg.get("agent_timeout"))
    return cfg
