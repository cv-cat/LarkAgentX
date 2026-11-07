"""登录后从飞书取资料: 账号自己的姓名/头像/公司,以及会话和发送者的头像。

这些都不让用户手填。每一步都允许失败:拿不到就留空,界面退回首字母头像,绝不影响收发消息。
"""
import time

import requests
from loguru import logger

from . import accounts

PROFILE_TTL = 6 * 3600      # 账号资料多久刷新一次
AVATAR_TTL = 7 * 86400      # 头像缓存多久重新下载一次
AVATAR_MAX = 2 * 1024 * 1024
# 头像只从飞书/Lark 自家域名取,不做开放代理
ALLOWED_SUFFIXES = ('feishu.cn', 'larksuite.com', 'feishucdn.com', 'larksuitecdn.com', 'larkoffice.com')
_EXT = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp', 'image/gif': '.gif'}
_CTYPE = {v: k for k, v in _EXT.items()}


def _pick(d, *names):
    for n in names:
        v = d.get(n)
        if v:
            return v
    return ''


def _image_key(img) -> str:
    """Image / ImageSet 里取一个可下载的 key:优先缩略图(够当头像用,体积小)。"""
    if not isinstance(img, dict):
        return ''
    for part in ('thumbnail', 'middle', 'origin'):
        sub = img.get(part)
        if isinstance(sub, dict) and sub.get('key'):
            return sub['key']
    return img.get('key') or img.get('imageKey') or ''


def _image_url(img) -> str:
    if not isinstance(img, dict):
        return ''
    for part in (img, img.get('thumbnail'), img.get('middle'), img.get('origin')):
        if isinstance(part, dict):
            urls = part.get('urls') or part.get('secureUrls') or []
            if urls:
                return urls[0]
    return ''


def extract_chatter(chatter: dict) -> dict:
    """把 entities.Chatter(已转成 dict)压成界面要的几个字段。"""
    img, img2 = chatter.get('avatarImage'), chatter.get('avatar')
    return {'name': _pick(chatter, 'name', 'enUsName', 'alias'),
            'avatar_key': _image_key(img) or _image_key(img2),
            'avatar_url': chatter.get('avatarUrl') or _image_url(img) or _image_url(img2) or '',
            'tenant_id': chatter.get('tenantId') or ''}


def extract_tenant(tenant: dict) -> dict:
    return {'company': _pick(tenant, 'name', 'domain')}


def extract_web_user(user: dict) -> dict:
    """/accounts/web/user 的 data.user。字段名没有 proto 约束,按常见写法都试一遍。"""
    tenant = user.get('tenant') if isinstance(user.get('tenant'), dict) else {}
    avatar = user.get('avatar') if isinstance(user.get('avatar'), dict) else {}
    return {'name': _pick(user, 'name', 'cn_name', 'en_name'),
            'avatar_url': _pick(user, 'avatar_url', 'avatarUrl', 'avatar_thumb') or _pick(avatar, 'url', 'avatar_72', 'avatar_240'),
            'company': _pick(tenant, 'name', 'full_name') or _pick(user, 'tenant_name', 'tenantName')}


def fetch(client) -> dict:
    """client: 已登录的 LarkClient。返回 {name, avatar_key, avatar_url, company};任何一步失败都只是缺字段。"""
    uid = str(client.auth.user_id or '')
    out = {'name': '', 'avatar_key': '', 'avatar_url': '', 'company': '', 'fetched_at': time.time()}
    if not uid:
        return out
    try:
        hint = extract_web_user(client.auth.fetch_web_user())
        out.update({k: hint[k] for k in ('name', 'avatar_url', 'company') if hint[k]})
    except Exception as e:
        logger.bind(account=client.auth.account_id).debug(f'读取网页用户信息失败(不影响使用): {e}')
    try:
        info = chatter_info(client, uid)
        out.update({k: info[k] for k in ('name', 'avatar_key', 'avatar_url') if info[k]})
        if info['tenant_id'] and not out['company']:
            resp = client.api('tenant.PullTenantsByIDsRequest', {'tenantIds': [info['tenant_id']]})
            tenant = ((resp or {}).get('tenants') or {}).get(info['tenant_id'])
            if tenant:
                out['company'] = extract_tenant(tenant)['company']
    except Exception as e:
        logger.bind(account=client.auth.account_id).debug(f'获取账号资料失败(不影响使用): {e}')
    return out


def chatter_info(client, user_id: str) -> dict:
    resp = client.api('chatters.PullChattersByIdsRequest', {'chatterIds': [str(user_id)]})
    chatters = (resp or {}).get('chatters') or {}
    chatter = chatters.get(str(user_id)) or next(iter(chatters.values()), None)
    return extract_chatter(chatter or {})


def chat_avatar_info(client, chat_id: str) -> dict:
    img = (client.get_chat_info(chat_id) or {}).get('avatar')
    return {'avatar_key': _image_key(img), 'avatar_url': _image_url(img)}


def load(account_id: str) -> dict:
    return accounts.read_meta(account_id).get('profile') or {}


def save(account_id: str, profile: dict):
    accounts.update_meta(account_id, profile=profile)


def stale(profile: dict) -> bool:
    return not profile or time.time() - profile.get('fetched_at', 0) > PROFILE_TTL


def refresh(account_id: str, client) -> dict:
    """拿账号资料存进元数据。会发网络请求,在线程里调用。什么都没拿到时不覆盖旧资料。"""
    p = fetch(client)
    if p.get('name') or p.get('avatar_key') or p.get('avatar_url'):
        save(account_id, p)
    else:
        save(account_id, {**load(account_id), 'fetched_at': p['fetched_at']})    # 记下时间,别每次都重试
    return p


# ---------- 头像下载 ----------
def avatar_candidates(auth, info: dict) -> list:
    """头像可能的下载地址,按可能性排序依次尝试。
    服务端直接给的 url 最准;否则用资源 key 拼文件主机地址(网页版用 static-resource 路径)。"""
    urls = []
    direct = info.get('avatar_url') or ''
    if direct.startswith('https://'):
        urls.append(direct)
    key = info.get('avatar_key')
    if key:
        host = auth.region.file_host
        urls.append(f'{host}/static-resource/v1/{key}~?image_size=240x240&cut_type=default-face&quality=&format=webp&sticker_format=.webp')
        urls.append(f'{host}/download/avatar/{key}')
    return urls


def _host(url: str) -> str:
    return requests.utils.urlparse(url).hostname or ''


def _allowed(url: str) -> bool:
    host = _host(url)
    return any(host == s or host.endswith('.' + s) for s in ALLOWED_SUFFIXES)


def _cookies_for(auth, url: str):
    """登录 cookie 只发给所属区域的主站域名,CDN 不需要。"""
    domain = auth.region.domain
    host = _host(url)
    return auth.cookies if host == domain or host.endswith('.' + domain) else None


def download_avatar(auth, info: dict) -> tuple:
    """返回 (字节, content-type);全部候选都失败返回 (b'', '')。限制域名、类型、体积。"""
    for url in avatar_candidates(auth, info):
        if not _allowed(url):
            continue
        try:
            r = requests.get(url, cookies=_cookies_for(auth, url), timeout=10, stream=True, allow_redirects=False)
            if r.status_code in (301, 302, 307, 308):          # 重定向只跟一次,且目标也必须在白名单内
                target = r.headers.get('location', '')
                if not _allowed(target):
                    continue
                r = requests.get(target, cookies=_cookies_for(auth, target), timeout=10, stream=True, allow_redirects=False)
            if r.status_code != 200:
                continue
            ctype = r.headers.get('content-type', '').split(';')[0].strip()
            if ctype not in _EXT:
                continue
            buf, ok = b'', True
            for chunk in r.iter_content(1 << 14):
                buf += chunk
                if len(buf) > AVATAR_MAX:
                    ok = False
                    break
            if ok and buf:
                return buf, ctype
        except Exception:
            continue
    return b'', ''


def cache_dir(account_id: str):
    return accounts.home_of(account_id) / 'avatars'


def cached_file(account_id: str, name: str):
    """已缓存的头像文件和 content-type;没有返回 (None, '')。name 是调用方校验过的安全文件名。"""
    d = cache_dir(account_id)
    for ext, ctype in _CTYPE.items():
        p = d / (name + ext)
        if p.exists():
            return p, ctype
    return None, ''


def write_cache(account_id: str, name: str, data: bytes, ctype: str):
    d = cache_dir(account_id)
    d.mkdir(parents=True, exist_ok=True)
    old, _ = cached_file(account_id, name)
    if old:
        old.unlink(missing_ok=True)
    (d / (name + _EXT[ctype])).write_bytes(data)
