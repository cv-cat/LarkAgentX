"""多账号注册表: 一个账号 = 一个目录(凭证 + 消息库 + 设置)。

布局:
  LARKX_HOME/                      -> 账号 "default"(沿用旧版单账号的位置,不搬文件)
  LARKX_HOME/accounts/<id>/        -> 其它账号
每个目录里: credentials.json(登录凭证)、messages.db(消息库,SQLite)、account.json(名称/自启/设置)。
"""
import json
import os
import re
import secrets
import shutil
from pathlib import Path

from . import config

DEFAULT_ID = 'default'
_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,32}$')


def normalize(account_id: str = None) -> str:
    """账号 id 会拼进文件路径,必须严格校验,防止 ../ 之类。"""
    account_id = account_id or DEFAULT_ID
    if not _ID_RE.match(account_id):
        raise ValueError(f'非法账号 id: {account_id!r}(只允许字母/数字/_/-,最长 32)')
    return account_id


def home_of(account_id: str = None) -> Path:
    account_id = normalize(account_id)
    if account_id == DEFAULT_ID:
        return Path(config.DATA_DIR)
    return Path(config.DATA_DIR) / 'accounts' / account_id


def credentials_path(account_id: str = None) -> Path:
    return home_of(account_id) / 'credentials.json'


def db_path(account_id: str = None) -> Path:
    return home_of(account_id) / 'messages.db'


def meta_path(account_id: str = None) -> Path:
    return home_of(account_id) / 'account.json'


def read_meta(account_id: str = None) -> dict:
    try:
        return json.loads(meta_path(account_id).read_text(encoding='utf-8'))
    except Exception:
        return {}


def write_meta(account_id: str, meta: dict):
    path = meta_path(account_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def update_meta(account_id: str, **fields) -> dict:
    meta = read_meta(account_id)
    meta.update(fields)
    write_meta(account_id, meta)
    return meta


def exists(account_id: str) -> bool:
    return credentials_path(account_id).exists() or meta_path(account_id).exists()


def list_ids() -> list:
    ids = []
    if exists(DEFAULT_ID):
        ids.append(DEFAULT_ID)
    root = Path(config.DATA_DIR) / 'accounts'
    if root.is_dir():
        for d in sorted(root.iterdir()):
            if d.is_dir() and _ID_RE.match(d.name) and exists(d.name):
                ids.append(d.name)
    return ids


def create(name: str, region: str) -> str:
    while True:
        account_id = 'a' + secrets.token_hex(3)
        if not exists(account_id):
            break
    write_meta(account_id, {'name': name.strip(), 'region': region, 'autostart': False})
    return account_id


def display_name(account_id: str) -> str:
    """备注名 > 飞书里的姓名 > 默认账号/账号 id。"""
    meta = read_meta(account_id)
    return meta.get('name') or (meta.get('profile') or {}).get('name') or ('默认账号' if account_id == DEFAULT_ID else account_id)


def get_settings(account_id: str = None) -> dict:
    """这个账号实际生效的配置(默认值 < 环境变量 < 账号设置)。"""
    return config.load_config(read_meta(account_id).get('settings'))


def save_settings(account_id: str, settings: dict):
    update_meta(account_id, settings={k: settings[k] for k in config.SETTING_KEYS if k in settings})


def delete(account_id: str):
    """default 账号就是 LARKX_HOME 本身,绝不能整目录删,只清登录凭证和设置(消息库保留)。"""
    account_id = normalize(account_id)
    if account_id == DEFAULT_ID:
        for p in (credentials_path(account_id), meta_path(account_id)):
            p.unlink(missing_ok=True)
    else:
        shutil.rmtree(home_of(account_id), ignore_errors=True)
