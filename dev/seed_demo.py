"""造一份演示数据并(可选)起 web 控制台,用来调 UI,不碰真实账号。

用法(必须显式指定一个临时数据目录):
    LARKX_HOME=/tmp/larkx_demo python dev/seed_demo.py --serve
"""
import argparse
import hashlib
import os
import sys
import time
from pathlib import Path

_home = os.environ.get('LARKX_HOME')
if not _home or Path(os.path.expanduser(_home)).resolve() == (Path.home() / '.larkx').resolve():
    sys.exit('必须把 LARKX_HOME 设为一个临时目录(不能是真实的 ~/.larkx),避免污染真实账号数据')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from larkx import accounts, memory, profile  # noqa: E402
from larkx.auth import LarkAuth  # noqa: E402
from larkx.storage import Storage  # noqa: E402

NOW = int(time.time())
H, D = 3600, 86400
# 头像和首页共用一份,来源和授权见该目录的 SOURCE.md;人名都是虚构的
AVATARS = Path(__file__).resolve().parent.parent / 'webui' / 'src' / 'assets' / 'avatars'


def fake_login(account_id, user_id, name, company):
    auth = LarkAuth(account_id)
    auth.cookies = {'session': 'demo', 'passport_web_did': '1'}
    auth.device_id, auth.user_id, auth.saved_at = '1', user_id, NOW - 2 * H
    auth.save()
    accounts.update_meta(account_id, profile={'name': name, 'company': company, 'fetched_at': time.time() + 30 * 86400})


def fake_avatar(account_id, kind, ident, filename):
    """把演示头像写进真实的头像缓存路径。真实账号的头像来自飞书。"""
    name = kind + '_' + hashlib.sha1(ident.encode()).hexdigest()[:20]
    ctype = 'image/jpeg' if filename.endswith('.jpg') else 'image/png'
    profile.write_cache(account_id, name, (AVATARS / filename).read_bytes(), ctype)


PEOPLE = {'u_chen': ('陈思远', '会员中心 · 后端'), 'u_zhou': ('周雨桐', '会员中心 · 后端'), 'u_xu': ('许嘉禾', '数据平台'),
          'u_song': ('宋以宁', '设计中心')}


class DemoApi:
    """演示用的飞书客户端: 发消息只落库,不联网。"""
    def __init__(self, user_id):
        class A:
            pass
        self.auth = A()
        self.auth.user_id = user_id
        self.n = 0

    def send_msg(self, text, chat_id, root_id=None, quote_id=None):
        self.n += 1
        return f'demo-{NOW}-{self.n}'

    def get_chat_info(self, chat_id):
        return {'lastMessagePosition': 1}

    def search(self, query):
        return [{'type': 'user', 'id': uid, 'title': name, 'summary': dept} for uid, (name, dept) in PEOPLE.items() if query in name]

    def get_user_name(self, user_id, chat_id):
        return PEOPLE.get(user_id, ('', ''))[0]

    def close(self):
        pass


def msg(st, mid, chat, ctype, frm, sender, text, ago, chat_name, pos=0, out=False, anchor='', mtype='TEXT'):
    st.save_message({
        'msg_id': mid, 'chat_id': chat, 'chat_type': ctype, 'scope': 'topic' if anchor else 'chat', 'anchor': anchor,
        'from_id': frm, 'msg_type': 4, 'msg_type_name': mtype, 'content': text, 'create_time': NOW - ago, 'position': pos,
    }, sender_name=sender, chat_name=chat_name, direction='out' if out else 'in')


def seed_work(a):
    st = Storage(account_id=a)
    n = [0]

    def m(*args, **kw):
        n[0] += 1
        msg(st, f'm{n[0]}', *args, pos=n[0], **kw)

    g = ('c_proj', 2)
    m(*g, 'u_chen', '陈思远', '早，今天的发版窗口定在下午 4 点，大家确认下', D + 3 * H, '会员中心重构')
    m(*g, 'u_zhou', '周雨桐', '后端这边没问题，迁移脚本已经在预发跑过了', D + 2 * H, '会员中心重构')
    m(*g, 'u_me', '林知夏', '收到，我会盯着发版，有异常随时同步', D + 2 * H - 120, '会员中心重构', out=True)
    m(*g, 'u_chen', '陈思远', '@林知夏 帮忙看一下这个报错:\nTypeError: Cannot read properties of undefined (reading \'id\')\n    at renderRow (list.js:42)', 5 * H, '会员中心重构')
    m(*g, 'u_me', '林知夏', '看了下，是 renderRow 里没判空，row.owner 在新建草稿时是 undefined。加个 row.owner?.id 就行，我顺手把对应的测试也补了。', 5 * H - 90, '会员中心重构', out=True)
    m(*g, 'u_chen', '陈思远', '', 4 * H, '会员中心重构', mtype='IMAGE')
    m(*g, 'u_chen', '陈思远', '[图片] 这是复现的截图', 4 * H - 5, '会员中心重构', mtype='IMAGE')
    m(*g, 'u_zhou', '周雨桐', '灰度方案放在文档里了，周五前定一下', 40 * 60, '会员中心重构')
    m(*g, 'u_me', '林知夏', '方案我过了一遍，有两点想确认:1) 灰度比例是否按城市拆;2) 回滚是不是只回前端。其余没问题。', 38 * 60, '会员中心重构', out=True)

    p = ('c_p2p', 1)
    m(*p, 'u_xu', '许嘉禾', '在吗，上次那个导出脚本能再给我一份吗', 2 * D + H, '许嘉禾')
    m(*p, 'u_me', '林知夏', '在的，稍等，我发你', 2 * D + H - 60, '许嘉禾', out=True)
    m(*p, 'u_xu', '许嘉禾', '好的谢谢', 2 * D, '许嘉禾')
    m(*p, 'u_xu', '许嘉禾', '周末有空一起吃饭吗', 25 * 60, '许嘉禾')

    t = ('c_topic', 3)
    m(*t, 'u_song', '宋以宁', '首页改版的初稿放在文档里了，大家有意见在这里讨论', D + H, '产品设计讨论', anchor='t_home')
    m(*t, 'u_zhou', '周雨桐', '我倾向把搜索入口放到顶部', D, '产品设计讨论', anchor='t_home')
    m(*t, 'u_me', '林知夏', '搜索放顶部没问题，不过移动端要考虑拇指热区，建议底部再留一个快捷入口。', D - 300, '产品设计讨论', out=True, anchor='t_home')
    m(*t, 'u_song', '宋以宁', '下周一对齐 Q3 OKR，各组先把草稿填一下', 3 * H, '产品设计讨论', anchor='t_okr')

    w = ('c_weekly', 2)
    m(*w, 'bot', '周报助手', '[卡片] 本周周报提交提醒:请在周五 18:00 前提交', 6 * H, '研发周报', mtype='CARD')

    # 长期记忆、定时任务;Agent 发的消息在聊天记录里会标出来
    accounts.update_meta(a, settings={'memory_enabled': True})     # 每日回顾用默认的 00:00
    for text in ('陈思远：会员中心重构的后端负责人，喜欢先看结论再看细节',
                 '会员中心重构群：每周五 16:00 发版，发版前在群里确认',
                 '许嘉禾：要过导出脚本，之后可能还会再要',
                 '我：周报每周五 18:00 前交'):
        memory.add(a, text)
    st.task_add('c_proj', '', 'daily', '汇总群里昨天没人回复的问题，发给我', run_at=NOW + 14 * H, daily_at='09:30', created_by='agent')
    st.task_add('c_p2p', '', 'once', '提醒我把导出脚本发给许嘉禾', run_at=NOW + 2 * H, created_by='agent')
    for mid in ('m5', 'm9'):
        st.mark_agent_sent(mid, 'c_proj')

    st.session_upsert('c_proj:', 'c_proj', '', 'sess-1', True)
    st.session_upsert('c_p2p:', 'c_p2p', '', 'sess-2', True)
    st.session_upsert('c_topic:t_home', 'c_topic', 't_home', 'sess-3', True)
    for key, times in (('c_proj:', 4), ('c_p2p:', 2), ('c_topic:t_home', 1)):
        for _ in range(times):
            st.session_touch(key)
    st.close()


def seed_personal(a):
    st = Storage(account_id=a)
    msg(st, 'p1', 'c_fam', 1, 'u_m', '妈妈', '晚上回家吃饭吗', 3 * H, '妈妈', pos=1)
    msg(st, 'p2', 'c_fam', 1, 'u_me2', 'Zhixia Lin', '回，七点前到', 3 * H - 60, '妈妈', pos=2, out=True)
    st.close()


def block_real_login(mgr):
    """演示服务里不能登录或启动真实账号。否则真实账号会在演示进程里多跑一份,同一条消息被回复两次。"""
    from larkx.web.manager import Conflict

    def refuse(*args, **kwargs):
        raise Conflict('这是演示服务，不能登录或启动真实账号。请用 lark web 打开真实控制台。')

    async def refuse_async(*args, **kwargs):
        refuse()

    mgr.add_by_qr = mgr.start_login = mgr.cookie_login = refuse
    mgr.start = mgr.restart = refuse_async


def public_readonly(app):
    """放到公网上的演示: 只能看,所有修改都拒绝,免得访客把演示数据改乱。
    控制台没配令牌时只认本机 Host(防 DNS rebinding),这里请求本来就来自本机的反向代理,所以把 Host 换成本机。"""
    import json
    body = json.dumps({'detail': '在线演示只能查看，不能修改。'}, ensure_ascii=False).encode()

    async def wrapped(scope, receive, send):
        if scope['type'] == 'http':
            if scope['path'].startswith('/api') and scope['method'] not in ('GET', 'HEAD', 'OPTIONS'):
                await send({'type': 'http.response.start', 'status': 403,
                            'headers': [(b'content-type', b'application/json; charset=utf-8'), (b'content-length', str(len(body)).encode())]})
                await send({'type': 'http.response.body', 'body': body})
                return
            scope = dict(scope, headers=[(k, v) for k, v in scope['headers'] if k != b'host'] + [(b'host', b'127.0.0.1')])
        await app(scope, receive, send)
    return wrapped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--serve', action='store_true', help='造完数据后起 web 控制台')
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--public', action='store_true', help='放到公网上(反向代理后面): 只读,不能修改任何数据')
    args = ap.parse_args()

    work = accounts.create('', 'feishu')
    personal = accounts.create('', 'lark')
    fake_login(work, 'u_me', '林知夏', '北岸科技')
    fake_login(personal, 'u_me2', 'Zhixia Lin', 'Brightline Labs')
    seed_work(work)
    seed_personal(personal)
    for kind, ident, filename in (
        ('user', 'u_me', 'lin-zhixia.jpg'), ('user', 'u_chen', 'chen-siyuan.jpg'), ('user', 'u_zhou', 'zhou-yutong.jpg'),
        ('user', 'u_xu', 'xu-jiahe.jpg'), ('user', 'u_song', 'song-yining.jpg'), ('user', 'bot', 'bot-weekly.png'),
        ('chat', 'c_proj', 'group-member-center.png'), ('chat', 'c_topic', 'group-product-design.png'), ('chat', 'c_weekly', 'group-weekly.png'),
    ):
        fake_avatar(work, kind, ident, filename)
    fake_avatar(personal, 'user', 'u_me2', 'lin-zhixia.jpg')
    fake_avatar(personal, 'user', 'u_m', 'mom.jpg')
    print(f'已生成演示账号: {work} {personal}  (数据目录 {_home})')

    if not args.serve:
        return

    import uvicorn
    from larkx.listener import Listener
    from larkx.web import create_app

    app = create_app(autostart=False)
    mgr = app.state.manager
    block_real_login(mgr)
    # 假装工作号在运行、个人号凭证失效,方便看各种状态的样式;不会真的联网
    running = Listener(work)
    running.state = 'running'
    mgr.listeners[work] = running
    mgr.clients[work] = DemoApi('u_me')
    dead = Listener(personal)
    dead.state, dead.error = 'login_required', '会话已被服务端注销,请重新登录'
    mgr.listeners[personal] = dead
    log = logger.bind(account=work)
    log.info('WS 已连接')
    log.info('[会员中心重构] 周雨桐: 灰度方案放在文档里了，周五前定一下')
    log.info("调 agent [c_proj:]: claude -p --dangerously-skip-permissions --resume sess-1 << <message>…")
    log.warning('WS 断开: 网络抖动,2s 后重连')
    log.info('WS 已连接')
    log.error('agent 返回非零(1): rate limit exceeded')
    uvicorn.run(public_readonly(app) if args.public else app, host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
