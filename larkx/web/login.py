"""网页扫码登录: 后台线程跑 QrLogin(阻塞轮询),前端轮询 snapshot() 拿二维码和状态。"""
import base64
import io
import threading

from loguru import logger

from ..auth import LarkAuth, QrLogin
from ..region import get_region


class _Cancelled(Exception):
    pass


def qr_data_url(content: str) -> str:
    import qrcode
    buf = io.BytesIO()
    qrcode.make(content, border=2, box_size=8).save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


class LoginFlow:
    MAX_ATTEMPTS = 6        # 和 lark auth qr 一样: 二维码过期自动刷新,最多 6 张
    ATTEMPT_TIMEOUT = 45

    def __init__(self, account_id: str, region_name: str, on_success=None):
        self.account_id = account_id
        self.on_success = on_success
        self.region = get_region(region_name)
        self.state = 'starting'     # starting | waiting | scanned | success | failed
        self.message = '正在获取二维码…'
        self.qr = ''
        self.attempt = 0
        self._cancelled = threading.Event()
        threading.Thread(target=self._run, daemon=True, name=f'qr-login-{account_id}').start()

    def cancel(self):
        self._cancelled.set()

    @property
    def done(self) -> bool:
        return self.state in ('success', 'failed')

    def snapshot(self) -> dict:
        return {'state': self.state, 'message': self.message, 'qr': self.qr, 'attempt': self.attempt, 'account_id': self.account_id}

    def _on_status(self, status, step):
        if self._cancelled.is_set():
            raise _Cancelled()
        if status == 2:
            self.state, self.message = 'scanned', '已扫码，请在手机上确认登录'

    def _fail(self, message: str):
        self.state, self.message = 'failed', message

    def _run(self):
        try:
            for attempt in range(1, self.MAX_ATTEMPTS + 1):
                if self._cancelled.is_set():
                    return
                self.attempt = attempt
                ql = QrLogin(self.region)
                self.qr = qr_data_url(ql.qr_content)
                self.state, self.message = 'waiting', f'请用 {self.region.label} App 扫码'
                ok, data = ql.wait(timeout=self.ATTEMPT_TIMEOUT, on_status=self._on_status)
                if self._cancelled.is_set():
                    return
                if ok:
                    ql.finish(LarkAuth(self.account_id))
                    self.state, self.message, self.qr = 'scanned', '登录成功，正在获取账号信息…', ''
                    if self.on_success:
                        # 资料(姓名/头像)取完才算结束,界面一跳转就能看到真名;取失败不影响登录结果
                        try:
                            self.on_success(self)
                        except Exception as e:
                            logger.bind(account=self.account_id).warning(f'登录后处理失败(不影响登录): {e}')
                    self.state, self.message = 'success', '登录成功'
                    return
                status = ((data or {}).get('step_info') or {}).get('status')
                if status in (3, 4):
                    return self._fail('扫码已取消或出错，请重试')
            self._fail('二维码多次过期仍未登录，请重试')
        except _Cancelled:
            pass
        except Exception as e:
            self._fail(str(e))
