"""FastAPI 应用: 控制台 API + 静态前端。

安全模型: 控制台能启动 agent(= 在本机执行命令)并管理登录凭证,等同本机 shell 权限。
- 默认只监听 127.0.0.1;监听非本机地址必须设令牌(见 cli.cmd_web)
- 配了令牌就所有 /api 都要带。网页先 POST /api/login 换一个 HttpOnly cookie,之后靠 cookie,
  令牌不出现在网址里(不进代理日志和 Referer);脚本可以用 Authorization: Bearer / X-Token
- 校验 Host 头防 DNS rebinding;写操作校验 Origin 防跨站请求(CSRF)
"""
import hmac
import ipaddress
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..auth import AuthExpired
from .manager import Conflict, Manager, NotFound
from .routes import build_router
from .schemas import LoginIn

STATIC_DIR = Path(__file__).parent / 'static'
LOOPBACK_NAMES = {'localhost', '127.0.0.1', '::1'}
TOKEN_COOKIE = 'larkx_token'
TOKEN_COOKIE_AGE = 180 * 86400


def resolve_token(cli_token: str = None) -> str:
    return (cli_token or os.environ.get('LARKX_WEB_TOKEN') or '').strip()


def is_loopback(host: str) -> bool:
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _host_only(host_header: str) -> str:
    h = (host_header or '').strip()
    if h.startswith('['):
        return h[1:h.find(']')] if ']' in h else h
    return h.rsplit(':', 1)[0] if h.count(':') == 1 else h


def _bearer(request: Request) -> str:
    auth = request.headers.get('authorization', '')
    if auth.lower().startswith('bearer '):
        return auth[7:].strip()
    return request.headers.get('x-token') or request.cookies.get(TOKEN_COOKIE) or ''


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))


def create_app(token: str = '', autostart: bool = True, manager: Manager = None) -> FastAPI:
    mgr = manager or Manager()

    @asynccontextmanager
    async def lifespan(app):
        if autostart:
            await mgr.autostart_all()
        yield
        await mgr.shutdown()

    app = FastAPI(title='LarkAgentX', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.manager = mgr

    @app.middleware('http')
    async def guard(request: Request, call_next):
        host = _host_only(request.headers.get('host', ''))
        # 没配令牌 = 只信任回环地址,Host 不是回环名就拒绝(挡 DNS rebinding)
        if not token and host not in LOOPBACK_NAMES and not is_loopback(host):
            return JSONResponse({'detail': 'Host 不允许;监听非本机地址请设置 --token'}, status_code=403)
        if request.url.path.startswith('/api'):
            if token and request.url.path != '/api/login' and not _same(_bearer(request), token):
                return JSONResponse({'detail': '需要访问令牌'}, status_code=401)
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                origin = request.headers.get('origin')
                if origin and urlparse(origin).netloc != request.headers.get('host'):
                    return JSONResponse({'detail': '跨站请求被拒绝'}, status_code=403)
        return await call_next(request)

    @app.exception_handler(NotFound)
    async def _not_found(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=404)

    @app.exception_handler(Conflict)
    async def _conflict(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409)

    @app.exception_handler(AuthExpired)
    async def _auth_expired(request, exc):
        return JSONResponse({'detail': '登录已失效，请重新登录'}, status_code=409)

    @app.exception_handler(ValueError)
    async def _bad_value(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=400)

    @app.post('/api/login', include_in_schema=False)
    async def login(body: LoginIn, request: Request):
        """用访问令牌换 cookie。没配令牌时直接成功。"""
        if not token:
            return {'ok': True}
        if not _same(body.token.strip(), token):
            return JSONResponse({'detail': '访问令牌不对'}, status_code=401)
        resp = JSONResponse({'ok': True})
        https = request.url.scheme == 'https' or request.headers.get('x-forwarded-proto') == 'https'
        resp.set_cookie(TOKEN_COOKIE, token, max_age=TOKEN_COOKIE_AGE, httponly=True, samesite='strict', secure=https, path='/')
        return resp

    app.include_router(build_router(mgr, bool(token)), prefix='/api')

    index = STATIC_DIR / 'index.html'
    app.mount('/assets', StaticFiles(directory=STATIC_DIR / 'assets', check_dir=False), name='assets')

    @app.get('/{path:path}', include_in_schema=False)
    async def spa(path: str):
        if path == 'api' or path.startswith('api/'):
            return JSONResponse({'detail': '接口不存在'}, status_code=404)
        # 构建产物根目录下的文件(图标等)直接给;其余路径交给前端路由,回 index.html
        target = (STATIC_DIR / path).resolve()
        if path and target.is_file() and target.is_relative_to(STATIC_DIR.resolve()):
            return FileResponse(target)
        return FileResponse(index, headers={'Cache-Control': 'no-cache'})

    return app

