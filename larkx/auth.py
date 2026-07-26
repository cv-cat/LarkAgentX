import json
import time
from pathlib import Path
import requests
from loguru import logger
from .config import CREDENTIALS_PATH, DATA_DIR
TICKET_URL = 'https://login.feishu.cn/suite/passport/frontier_ticket/'
USER_INFO_URL = 'https://internal-api-lark-api.feishu.cn/accounts/web/user'
CSRF_URL = 'https://internal-api-lark-api.feishu.cn/accounts/csrf'
APPKEY_PAGE_URL = 'https://open-dev.feishu.cn/messenger/'


class AuthExpired(Exception):
    pass


class LarkAuth:
    def __init__(self, path: Path=CREDENTIALS_PATH):
        self.path = path
        self.cookies: dict = {}
        self.saved_at: float = 0
        self.device_id: str = ''
        self.app_key: str = ''
        self.user_id: str = ''
        self.csrf_token: str = ''
        self.load()

    def load(self) -> bool:
        if not self.path.exists():
            return False
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            self.cookies = data.get('cookies', {})
            self.saved_at = data.get('saved_at', 0)
            self.device_id = data.get('device_id', '')
            self.app_key = data.get('app_key', '')
            self.user_id = data.get('user_id', '')
            self.csrf_token = data.get('csrf_token', '')
            return bool(self.cookies)
        except Exception as e:
            logger.warning(f'读取凭证文件失败: {e}')
            return False

    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({'cookies': self.cookies, 'saved_at': self.saved_at, 'device_id': self.device_id, 'app_key': self.app_key, 'user_id': self.user_id, 'csrf_token': self.csrf_token}, ensure_ascii=False, indent=2), encoding='utf-8')
        logger.info(f'凭证已保存到 {self.path}')

    def import_cookie_string(self, cookie_str: str):
        cookies = {}
        for part in cookie_str.strip().split(';'):
            if '=' not in part:
                continue
            k, v = part.strip().split('=', 1)
            cookies[k] = v
        if 'session' not in cookies:
            raise ValueError('cookie 中缺少 session,请确认复制完整')
        self.cookies = cookies
        self.saved_at = time.time()
        self.device_id = cookies.get('passport_web_did', '')
        self.csrf_token = cookies.get('swp_csrf_token', '')
        self.app_key = ''
        ok, msg = self.validate(fetch_profile=True)
        self.save()
        if not ok:
            raise AuthExpired(f'导入的 cookie 校验失败: {msg}')
        return msg

    def validate(self, fetch_profile: bool=False) -> tuple:
        if not self.cookies:
            return (False, '无凭证,请先 lark auth import')
        if not self.device_id:
            self.device_id = self.cookies.get('passport_web_did', '')
        try:
            r = requests.get(TICKET_URL, params={'local_device_id': self.device_id}, cookies=self.cookies, timeout=10)
            j = r.json()
            ticket = j.get('ticket')
            if not ticket:
                reason = j.get('message', str(j))
                age_h = (time.time() - self.saved_at) / 3600 if self.saved_at else -1
                return (False, f'会话已被服务端注销(凭证保存于 {age_h:.1f}h 前): {reason}\n请重新登录: lark auth qr 或 lark auth import')
        except Exception as e:
            return (False, f'ticket 探针网络异常(先检查网络,不一定是凭证问题): {e}')
        if fetch_profile:
            self._fetch_profile()
        age_h = (time.time() - self.saved_at) / 3600 if self.saved_at else -1
        return (True, f"有效(user_id={self.user_id or '?'}, 已保存 {age_h:.1f}h)")

    def _fetch_profile(self):
        ua = {'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'}
        try:
            headers = {**ua, 'x-app-id': '12', 'x-api-version': '1.0.8', 'x-csrf-token': self.csrf_token or self.cookies.get('swp_csrf_token', ''), 'x-device-info': 'platform=websdk', 'x-lgw-os-type': '1', 'x-lgw-terminal-type': '2', 'origin': 'https://open-dev.feishu.cn', 'referer': 'https://open-dev.feishu.cn/'}
            r = requests.get(USER_INFO_URL, params={'app_id': '12', '_t': int(time.time() * 1000)}, headers=headers, cookies=self.cookies, timeout=10)
            self.user_id = str(r.json()['data']['user']['id'])
        except Exception as e:
            logger.warning(f'获取用户信息失败: {e}')
        if not self.app_key:
            try:
                import re
                text = requests.get(APPKEY_PAGE_URL, headers=ua, cookies=self.cookies, timeout=15).text
                m = re.findall('appKey: "(.*?)"', text)
                if m:
                    self.app_key = m[0]
                else:
                    logger.warning('appKey 抓取失败: 页面里没有 appKey(UA/页面结构变化?)')
            except Exception as e:
                logger.warning(f'获取 appKey 失败: {e}')
        if not self.app_key:
            logger.error('app_key 为空,WS 会被拒(access_key 无法计算)')

    def require_valid(self) -> str:
        ok, msg = self.validate()
        if not ok:
            raise AuthExpired(f'凭证已过期或无效: {msg}\n请从浏览器重新复制 cookie 后执行: lark auth import')
        return msg

    def get_ticket(self) -> str:
        r = requests.get(TICKET_URL, params={'local_device_id': self.device_id}, cookies=self.cookies, timeout=10)
        j = r.json()
        ticket = j.get('ticket')
        if not ticket:
            raise AuthExpired(f'获取 ticket 失败: {j}')
        return ticket

    def refresh_csrf(self) -> str:
        r = requests.post(CSRF_URL, params={'_t': int(time.time() * 1000)}, cookies=self.cookies, timeout=10)
        token = r.cookies.get('swp_csrf_token')
        if token:
            self.csrf_token = token
            self.save()
        return self.csrf_token

    def status(self) -> dict:
        return {'has_credentials': bool(self.cookies), 'saved_at': self.saved_at, 'device_id': self.device_id, 'user_id': self.user_id, 'app_key': self.app_key, 'path': str(self.path)}


QR_INIT_URL = "https://accounts.feishu.cn/accounts/qrlogin/init"
QR_POLLING_URL = "https://accounts.feishu.cn/accounts/qrlogin/polling"
QR_STATUS_NAMES = {0: "SUCCESS", 1: "等待扫码", 2: "已扫码待确认", 3: "已取消", 4: "错误", 5: "已过期"}


def _qr_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "X-App-Id": "1",
        "X-Api-Version": "1.0.8",
        "X-Device-Info": "platform=websdk",
        "X-Terminal-Type": "2",
        "Origin": "https://accounts.feishu.cn",
        "Referer": "https://accounts.feishu.cn/accounts/page/login?app_id=1",
    })
    return s


class QrLogin:
    def __init__(self, redirect_uri="https://open-dev.feishu.cn/next/messenger"):
        self.session = _qr_session()
        r = self.session.post(QR_INIT_URL, json={"redirect_uri": redirect_uri}, timeout=15)
        j = r.json()
        if j.get("code") != 0:
            raise AuthExpired(f"qr init 失败: {j}")
        self.flow_key = r.headers.get("x-flow-key", "")
        self.token = j["data"]["step_info"]["token"]
        self.qr_content = json.dumps({"qrlogin": {"token": self.token}}, separators=(",", ":"))
        self.session.headers.update({"X-Flow-Key": self.flow_key})

    def wait(self, timeout=180, interval=2, on_status=None):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            r = self.session.post(QR_POLLING_URL, json={}, timeout=15)
            j = r.json()
            data = j.get("data") or {}
            step = data.get("next_step")
            status = (data.get("step_info") or {}).get("status")
            if status != last and on_status:
                on_status(status, step)
                last = status
            if step != "qr_login_polling" or self.session.cookies.get("session") or status == 0:
                return True, data
            if status in (3, 4, 5):
                return False, data
            time.sleep(interval)
        return False, None

    def finish(self, auth: LarkAuth) -> str:
        cookies = {}
        for c in self.session.cookies:
            cookies[c.name] = c.value
        if "session" not in cookies:
            raise AuthExpired("登录流程结束但未拿到 session cookie")
        auth.cookies = cookies
        auth.saved_at = time.time()
        auth.device_id = cookies.get("passport_web_did", "")
        auth.csrf_token = cookies.get("swp_csrf_token", "")
        ok, msg = auth.validate(fetch_profile=True)
        auth.save()
        if not ok:
            raise AuthExpired(f"登录成功但凭证校验失败: {msg}")
        return msg
