import argparse
import asyncio
import json
import locale
import os
import re
import sys
from datetime import datetime
from loguru import logger
from . import accounts
from .auth import AuthExpired, LarkAuth
from .client import LarkClient
from .listener import Listener, ListenerError
from .region import REGIONS, get_region
from .storage import Storage

_OPTION_LIKE = re.compile(r'--?[A-Za-z][A-Za-z0-9_-]*(=.*)?', re.S)


def _print_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_auth(args):
    auth = LarkAuth(getattr(args, 'account', None))
    # 新登录的区域: --region > 已有凭证的区域 > LARKX_REGION
    region = get_region(args.region) if args.region else auth.region
    if args.action == 'status':
        _print_json(auth.status())
        return 0
    if args.action == 'import':
        if args.cookie:
            cookie_str = args.cookie
        elif args.file:
            cookie_str = open(args.file, encoding='utf-8').read()
        else:
            logger.info('请粘贴 cookie 串,回车结束:')
            cookie_str = sys.stdin.readline()
        try:
            msg = auth.import_cookie_string(cookie_str, region)
            print(f'导入成功({region.name}): {msg}')
            return 0
        except (ValueError, AuthExpired) as e:
            print(f'导入失败: {e}', file=sys.stderr)
            return 1
    if args.action == 'check':
        ok, msg = auth.validate(fetch_profile=True)
        if ok:
            auth.save()
        print(('OK ' if ok else 'EXPIRED ') + msg)
        return 0 if ok else 1
    if args.action == 'qr':
        try:
            import qrcode as _qrcode
        except ImportError:
            print('需要 qrcode 包: pip install qrcode', file=sys.stderr)
            return 1
        from .auth import QR_STATUS_NAMES, QrLogin
        home = accounts.home_of(getattr(args, 'account', None))
        home.mkdir(parents=True, exist_ok=True)
        png_path = home / 'login_qr.png'

        def on_status(status, step):
            print(f'状态: {QR_STATUS_NAMES.get(status, status)} ({step})', flush=True)

        for attempt in range(1, 7):
            try:
                ql = QrLogin(region)
            except AuthExpired as e:
                print(str(e), file=sys.stderr)
                return 1
            qr = _qrcode.QRCode(border=1)
            qr.add_data(ql.qr_content)
            qr.make_image().save(str(png_path))
            print(f'[{attempt}/6] 二维码已刷新(请用 {region.label} App 扫码): {png_path}', flush=True)
            if attempt == 1:
                try:
                    qr.print_ascii(invert=True)
                except Exception:
                    qr.print_tty()
                sys.stdout.flush()
            ok, data = ql.wait(timeout=45, on_status=on_status)
            if ok:
                try:
                    msg = ql.finish(auth)
                    print(f'登录成功,凭证已保存: {msg}')
                    return 0
                except AuthExpired as e:
                    print(str(e), file=sys.stderr)
                    return 1
            print('当前二维码已失效,自动刷新...', flush=True)
        print('多次刷新后仍未完成登录,请重试', file=sys.stderr)
        return 1


def _ask_login_choice():
    try:
        import questionary
        ans = questionary.select(
            '选择登录方式:',
            choices=[
                questionary.Choice('扫码登录(推荐)', value='qr'),
                questionary.Choice('粘贴 cookie 登录', value='cookie'),
                questionary.Choice('退出', value='quit'),
            ],
        ).ask()
        if ans:
            return ans
    except Exception:
        pass
    print('  [1] 扫码登录(推荐)')
    print('  [2] 粘贴 cookie 登录')
    print('  [q] 退出')
    c = input('选择: ').strip().lower()
    return {'1': 'qr', '2': 'cookie'}.get(c, 'quit')


def _ask_cookie():
    try:
        import questionary
        ans = questionary.text('粘贴完整 cookie 后回车:').ask()
        if ans is not None:
            return ans
    except Exception:
        pass
    return input('粘贴完整 cookie 后回车: ').strip()


def _interactive_login(account_id=None):
    auth = LarkAuth(account_id)
    ok, msg = auth.validate(fetch_profile=True)
    if ok:
        auth.save()
        return auth
    if not sys.stdin.isatty():
        raise AuthExpired(msg)
    print(f'凭证缺失或已失效(区域: {auth.region.name},切换区域用 lark auth qr --region <feishu|lark>): {msg}', flush=True)
    while True:
        choice = _ask_login_choice()
        if choice == 'qr':
            rc = cmd_auth(argparse.Namespace(action='qr', cookie=None, file=None, region=None, account=account_id))
            if rc == 0:
                auth2 = LarkAuth(account_id)
                ok2, _ = auth2.validate()
                if ok2:
                    return auth2
        elif choice == 'cookie':
            cookie_str = _ask_cookie()
            if cookie_str is None:
                raise SystemExit(1)
            try:
                auth.import_cookie_string(cookie_str)
                return auth
            except Exception as e:
                print(f'导入失败: {e}')
        else:
            raise SystemExit(1)


def _is_agent() -> bool:
    """这条命令是不是 agent 执行的(agent 子进程的环境里带 LARKX_AGENT=1,见 agent/backend.py)。"""
    return os.environ.get('LARKX_AGENT') == '1'


def _read_text(parts: list) -> str:
    """命令行里的文字;只写一个 - 时从标准输入读(多行 markdown 用)。"""
    if parts != ['-']:
        return ' '.join(parts)
    data = sys.stdin.buffer.read()
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return data.decode(locale.getpreferredencoding(False), errors='replace')


def _parse_mentions(client, chat_id: str, items: list) -> list:
    """--mention 用户id:名字。没写名字就查一次。"""
    out = []
    for item in items:
        uid, _, name = item.partition(':')
        uid = uid.strip()
        if not uid.isdigit():
            raise ValueError(f'--mention 要写成 用户id:名字,「{item}」不对')
        out.append({'user_id': uid, 'name': name.strip() or client.get_user_name(uid, chat_id) or uid})
    return out


def cmd_send(args):
    from .media import UploadError, upload_file, upload_image
    from .proto.compose import plain_markdown
    text = _read_text(args.text)
    if not text.strip() and not (args.image or args.file):
        print('没有要发送的内容', file=sys.stderr)
        return 1
    client = LarkClient(LarkAuth(args.account))
    st = Storage(account_id=args.account)
    agent = _is_agent()
    target = {'root_id': args.root, 'quote_id': args.quote}

    def done(msg_id, content, msg_type, type_name) -> bool:
        if not msg_id:
            print('发送失败', file=sys.stderr)
            return False
        st.save_sent(msg_id, args.chat_id, content, client.auth.user_id, root_id=args.root, msg_type=msg_type, msg_type_name=type_name)
        if agent:
            st.mark_agent_sent(msg_id, args.chat_id)
        print(f'已发送 msg_id={msg_id}')
        return True

    if text.strip():
        # 回复署名只加在 agent 发的消息上
        sig = (accounts.get_settings(args.account).get('reply_signature') or '').strip() if agent else ''
        if sig:
            text = f'{text.rstrip()}\n\n{sig}'
        try:
            mentions = _parse_mentions(client, args.chat_id, args.mention)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1
        if args.markdown:
            ok = done(client.send(args.chat_id, markdown=text, mentions=mentions, **target), plain_markdown(text), 2, 'POST')
        else:
            ok = done(client.send(args.chat_id, text=text, mentions=mentions, **target), text, 4, 'TEXT')
        if not ok:
            return 1
    try:
        for path in args.image:
            key = upload_image(client.auth, path)
            if not done(client.send(args.chat_id, image_key=key, **target), '[图片]', 5, 'IMAGE'):
                return 1
        for path in args.file:
            info = upload_file(client.auth, path)
            if not done(client.send(args.chat_id, file=info, **target), f'[文件] {info["name"]}', 3, 'FILE'):
                return 1
    except (OSError, UploadError) as e:
        print(f'发送失败: {e}', file=sys.stderr)
        return 1
    return 0


def cmd_recall(args):
    client = LarkClient(LarkAuth(args.account))
    try:
        client.recall(args.msg_id)
    except Exception as e:
        print(f'撤回失败(只能撤回自己发的消息,且有时间限制): {e}', file=sys.stderr)
        return 1
    Storage(account_id=args.account).mark_recalled(args.msg_id)
    print(f'已撤回 msg_id={args.msg_id}')
    return 0


def cmd_forward(args):
    client = LarkClient(LarkAuth(args.account))
    try:
        ids = client.forward(args.msg_id, args.to, merge=args.merge)
    except Exception as e:
        print(f'转发失败: {e}', file=sys.stderr)
        return 1
    if not ids:
        print('转发失败: 服务端没有返回新消息的 id', file=sys.stderr)
        return 1
    st = Storage(account_id=args.account)
    for msg_id in ids:
        # 先按 id 落库,回显到了再补全内容;否则在「和自己的会话」里转发,回显会被当成你亲手发的
        st.save_sent(msg_id, args.to, '[转发的消息]', client.auth.user_id)
        if _is_agent():
            st.mark_agent_sent(msg_id, args.to)
        print(f'已转发 msg_id={msg_id}')
    return 0


def cmd_memory(args):
    from . import memory
    account_id = accounts.normalize(args.account)
    try:
        if args.action == 'add':
            items = memory.add(account_id, ' '.join(args.args))
        elif args.action == 'edit':
            if len(args.args) < 2 or not args.args[0].isdigit():
                print('用法: lark memory edit 编号 "新的内容"', file=sys.stderr)
                return 1
            items = memory.edit(account_id, int(args.args[0]), ' '.join(args.args[1:]))
        elif args.action == 'rm':
            if len(args.args) != 1 or not args.args[0].isdigit():
                print('用法: lark memory rm 编号', file=sys.stderr)
                return 1
            items = memory.remove(account_id, int(args.args[0]))
        else:
            items = memory.entries(account_id)
    except memory.MemoryEditError as e:
        print(str(e), file=sys.stderr)
        return 1
    for i, e in enumerate(items, 1):
        print(f'{i}. {e}')
    if not items:
        print('(还没有记忆)')
    print(memory.usage_text(items))
    return 0


def cmd_task(args):
    from . import tasks
    st = Storage(account_id=args.account)
    if args.action == 'rm':
        if len(args.args) != 1 or not args.args[0].isdigit():
            print('用法: lark task rm 编号', file=sys.stderr)
            return 1
        if not st.task_remove(int(args.args[0])):
            print(f'没有编号 {args.args[0]} 的定时任务', file=sys.stderr)
            return 1
        print(f'已删除定时任务 #{args.args[0]}')
        return 0
    if args.action == 'add':
        return _task_add(args, st, tasks)
    rows = st.task_list()
    for t in rows:
        print(f'#{t.id}\t{tasks.describe(t)}\t{st.get_chat_name(t.chat_id) or t.chat_id}\t{t.content}')
    if not rows:
        print('(没有定时任务)')
    return 0


def _task_add(args, st, tasks) -> int:
    content = ' '.join(args.args).strip()
    # 在 agent 里执行时默认记到当前会话(环境变量由 agent/backend.py 传进来),到点后在这个会话里处理
    chat_id = args.chat or os.environ.get('LARKX_CHAT_ID') or ''
    anchor = args.root or ('' if args.chat else os.environ.get('LARKX_ANCHOR') or '')
    if not content:
        print('要写上到点后做什么,比如: lark task add --in 30m "提醒我交周报"', file=sys.stderr)
        return 1
    if not chat_id:
        print('不知道到点后在哪个会话里处理,请用 --chat 指定会话 id', file=sys.stderr)
        return 1
    try:
        if args.daily:
            daily, kind = tasks.parse_hhmm(args.daily), 'daily'
            run_at = tasks.next_daily(daily, datetime.now())
        else:
            daily, kind = '', 'once'
            run_at = tasks.parse_in(args.in_) if args.in_ else tasks.parse_at(args.at)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    task_id = st.task_add(chat_id, anchor, kind, content, run_at=int(run_at.timestamp()), daily_at=daily,
                          created_by='agent' if _is_agent() else 'user')
    when = f'每天 {daily}' if daily else run_at.strftime('%Y-%m-%d %H:%M')
    print(f'已添加定时任务 #{task_id}: {when} {content}')
    return 0


def cmd_config(args):
    cfg = accounts.get_settings(args.account)
    _print_json(cfg)
    return 0


def cmd_chats(args):
    st = Storage(account_id=args.account)
    rows = st.list_chats(limit=args.limit)
    for c in rows:
        type_name = {1: '私聊', 2: '群聊', 3: '话题群'}.get(c.chat_type, '?')
        print(f"{c.chat_id}\t{type_name}\t{c.name or '(未命名)'}\t更新于 {c.updated_at}")
    return 0


def cmd_sessions(args):
    st = Storage(account_id=args.account)
    rows = st.list_sessions(limit=args.limit)
    for r in rows:
        scope = '话题' if r.anchor else ('全局' if r.session_key == 'global' else '会话')
        started = '已建立' if r.started else '待建立'
        print(f"{r.session_key}\t{scope}\tchat={r.chat_id}\tanchor={r.anchor or '-'}\t{started}\tmsg={r.msg_count}\t活跃于 {r.last_active}")
    return 0


def cmd_messages(args):
    st = Storage(account_id=args.account)
    anchor = None
    if args.anchor is not None:
        anchor = args.anchor
    rows = st.get_messages(args.chat_id, anchor=anchor, limit=args.limit)
    if args.json:
        _print_json([{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows])
        return 0
    for r in rows:
        ts = datetime.fromtimestamp(r.create_time).strftime('%m-%d %H:%M') if r.create_time else ''
        scope = f'[{r.scope}:{r.anchor[:8]}]' if r.anchor else ''
        content = r.content or ''
        shown = content[:120] + ('…' if len(content) > 120 else '')
        print(f'[{ts}]{scope} {r.sender_name or r.sender_id}: {shown}')
    return 0


def cmd_search(args):
    client = LarkClient(LarkAuth(args.account))
    results = client.search(' '.join(args.query))
    _print_json(results)
    return 0


def cmd_api(args):
    client = LarkClient(LarkAuth(args.account))
    data = None
    if args.json_body:
        try:
            data = json.loads(args.json_body)
        except Exception as e:
            print(f'JSON 解析失败: {e}', file=sys.stderr)
            return 1
    try:
        resp = client.api(args.type, data)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    _print_json(resp)
    return 0


def cmd_history(args):
    client = LarkClient(LarkAuth(args.account))
    chat_id = args.chat_id
    if args.start is not None:
        start = args.start
    else:
        info = client.get_chat_info(chat_id)
        if not info or not info.get('lastMessagePosition'):
            print('拿不到会话的最新 position,请用 --start 指定', file=sys.stderr)
            return 1
        start = int(info['lastMessagePosition']) - args.count + 1
        if info.get('name'):
            st = Storage(account_id=args.account)
            st.update_chat_name(chat_id, info['name'], info.get('type', 0) if isinstance(info.get('type'), int) else 0)
    positions = list(range(max(1, start), max(1, start) + args.count))
    st = Storage(account_id=args.account) if args.save else None
    msgs = client.pull_history(chat_id, positions, save_storage=st)
    for m in msgs:
        if args.json:
            continue
        ts = datetime.fromtimestamp(m['create_time']).strftime('%m-%d %H:%M') if m.get('create_time') else ''
        scope = f"[{m['scope']}:{m['anchor'][:8]}]" if m['anchor'] else ''
        content = m['content'] or ''
        shown = content[:120] + ('…' if len(content) > 120 else '')
        print(f"{m['position']:>6} [{ts}]{scope} {m['from_id']}: {shown}")
    if args.json:
        _print_json([{k: v for k, v in m.items() if k != 'content_data'} for m in msgs])
    if args.save:
        print(f'已入库 {len(msgs)} 条')
    return 0


def cmd_download(args):
    from .media import download, extract_resource_key, message_resource_url
    auth = LarkAuth(args.account)
    auth.require_valid()
    file_host = auth.region.file_host
    if args.key:
        if not args.chat:
            print('--key 需要配合 --chat <chat_id>', file=sys.stderr)
            return 1
        url = message_resource_url(args.msg_id or '0', args.key, args.chat, host=file_host)
        msg = None
    else:
        st = Storage(account_id=args.account)
        rows = None
        if args.chat:
            rows = st.get_messages(args.chat, limit=500)
            rows = [r for r in rows if r.msg_id == args.msg_id]
        else:
            from .storage.models import Message
            s = st.Session()
            rows = s.query(Message).filter_by(msg_id=args.msg_id).all()
            s.close()
        if not rows:
            print(f'本地未找到消息 {args.msg_id}(可用 --key/--chat 直接指定)', file=sys.stderr)
            return 1
        r = rows[-1]
        msg = {'msg_id': r.msg_id, 'chat_id': r.chat_id, 'msg_type': r.msg_type, 'content_data': json.loads(r.content_data) if r.content_data else None}
        key = extract_resource_key(r.msg_type, msg['content_data'] or {})
        if not key:
            print(f'消息 {args.msg_id} 类型为 {r.msg_type_name},没有可下载资源', file=sys.stderr)
            return 1
        url = message_resource_url(r.msg_id, key, r.chat_id, host=file_host)
    out = args.out
    if not out:
        print('必须指定 -o/--out 保存路径', file=sys.stderr)
        return 1
    path, content_type, n = download(auth, url, out)
    print(f'已下载: {path} ({content_type}, {n} 字节)')
    return 0


def _print_banner(args, auth, cfg):
    t = cfg.get('triggers') or {}
    st = Storage(account_id=args.account)
    print('─' * 56, flush=True)
    print(f"LarkAgentX 启动  account={auth.account_id}  region={auth.region.name}  user={auth.user_id}  device={auth.device_id[:12]}…", flush=True)
    print(f"  存储: {st.url}", flush=True)
    st.close()
    backend = cfg['agent_backend']
    print(f"  上下文边界: {cfg['context_scope']}  agent后端: {backend}{'  (已启用)' if args.agent else '  (未启用,仅入库)'}", flush=True)
    print(f"  触发前缀: {t.get('prefix') or '(全部消息)'}  自定义提示词: {'有' if cfg.get('system_prompt') else '无'}", flush=True)
    print('─' * 56, flush=True)


def cmd_listen(args):
    try:
        while True:
            try:
                auth = _interactive_login(args.account)
                cfg = accounts.get_settings(args.account)
                _print_banner(args, auth, cfg)
                listener = Listener(args.account, agent=args.agent, cfg=cfg)
                return asyncio.run(listener.run(auth))
            except ListenerError as e:
                print(str(e), file=sys.stderr)
                return 1
            except AuthExpired as e:
                if not sys.stdin.isatty():
                    print(str(e), file=sys.stderr)
                    return 1
                print(f'运行中凭证失效: {e}', flush=True)
    except KeyboardInterrupt:
        print('\n已停止')
        return 0


def cmd_web(args):
    try:
        import uvicorn
        from .web import create_app
    except ImportError as e:
        print(f'缺少 web 依赖,请执行: pip install -e .  ({e})', file=sys.stderr)
        return 1
    from .web.app import resolve_token, is_loopback
    token = resolve_token(args.token)
    if not is_loopback(args.host) and not token:
        print(f'监听 {args.host} 会把控制台暴露给局域网/公网,必须设 --token 或 LARKX_WEB_TOKEN', file=sys.stderr)
        return 1
    app = create_app(token=token, autostart=not args.no_autostart)
    url = f'http://{args.host}:{args.port}'
    print(f'LarkAgentX: {url}' + (f'/#token={token}' if token else '') + f'  (控制台 {url}/console)', flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level='warning')
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    logger.remove()
    logger.add(sys.stderr, level='INFO')
    parser = argparse.ArgumentParser(prog='lark', description='飞书 / Lark 网页版消息通道 CLI')
    sub = parser.add_subparsers(dest='cmd', required=True)
    acct = argparse.ArgumentParser(add_help=False)
    acct.add_argument('--account', default=None, metavar='ID', help='账号 id(默认 default;账号在 lark web 里管理)')
    # 子命令下面的子命令也认 --account;没写时不覆盖上一层已经解析到的值
    sub_acct = argparse.ArgumentParser(add_help=False)
    sub_acct.add_argument('--account', default=argparse.SUPPRESS, metavar='ID', help='账号 id')
    p = sub.add_parser('auth', parents=[acct], help='凭证管理')
    p.add_argument('action', choices=['status', 'import', 'check', 'qr'])
    p.add_argument('--cookie', help='直接传 cookie 串')
    p.add_argument('--file', help='从文件读 cookie')
    p.add_argument('--region', choices=list(REGIONS), help='qr/import 登录的区域: feishu=飞书(国内版) lark=Lark(国际版);默认沿用已有凭证,无凭证时取 LARKX_REGION')
    p.set_defaults(fn=cmd_auth)
    p = sub.add_parser('send', parents=[acct], help='发送消息(文字、markdown、图片、文件)')
    p.add_argument('chat_id')
    p.add_argument('text', nargs='*', help='消息内容;只写 - 时从标准输入读')
    p.add_argument('--root', help='话题/线程根消息 id,回复进话题')
    p.add_argument('--quote', help='引用回复这条消息(留在主会话流)')
    p.add_argument('-m', '--markdown', action='store_true', help='按 markdown 发富文本:代码块、列表、引用、标题、**加粗**、*斜体*、链接')
    p.add_argument('--mention', action='append', default=[], metavar='USER_ID:NAME',
                   help='真正 @ 某人,可重复。正文里写到的「@名字」就地变成 @,没写到的放在最前面')
    p.add_argument('--image', action='append', default=[], metavar='PATH', help='发一张图片,可重复')
    p.add_argument('--file', action='append', default=[], metavar='PATH', help='发一个文件,可重复')
    p.set_defaults(fn=cmd_send)
    p = sub.add_parser('recall', parents=[acct], help='撤回一条自己发的消息')
    p.add_argument('msg_id')
    p.set_defaults(fn=cmd_recall)
    p = sub.add_parser('forward', parents=[acct], help='转发消息到另一个会话')
    p.add_argument('msg_id', nargs='+', help='要转发的消息 id,可以写几个,按顺序逐条转发')
    p.add_argument('--to', required=True, metavar='CHAT_ID', help='转发到哪个会话')
    p.add_argument('--merge', action='store_true', help='合并成一条聊天记录转发(消息要来自同一个会话)')
    p.set_defaults(fn=cmd_forward)
    p = sub.add_parser('memory', parents=[acct], help='长期记忆:查看、添加、修改、删除条目')
    p.set_defaults(fn=cmd_memory, action='list', args=[])
    msub = p.add_subparsers(dest='action')
    msub.add_parser('list', parents=[sub_acct], help='查看全部条目')
    q = msub.add_parser('add', parents=[sub_acct], help='添加一条')
    q.add_argument('args', nargs='+', metavar='内容')
    q = msub.add_parser('edit', parents=[sub_acct], help='修改第 N 条')
    q.add_argument('args', nargs='+', metavar='编号 内容')
    q = msub.add_parser('rm', parents=[sub_acct], help='删除第 N 条')
    q.add_argument('args', nargs=1, metavar='编号')
    p = sub.add_parser('task', parents=[acct], help='定时任务:到点后交给 agent 处理')
    p.set_defaults(fn=cmd_task, action='list', args=[])
    tsub = p.add_subparsers(dest='action')
    tsub.add_parser('list', parents=[sub_acct], help='查看全部定时任务')
    q = tsub.add_parser('add', parents=[sub_acct], help='添加定时任务')
    q.add_argument('args', nargs='+', metavar='要做的事')
    when = q.add_mutually_exclusive_group(required=True)
    when.add_argument('--in', dest='in_', metavar='DURATION', help='多久之后执行一次,如 30m、2h、1d')
    when.add_argument('--at', metavar='TIME', help='指定时间执行一次,如 "2026-11-09 09:00" 或 "09:00"')
    when.add_argument('--daily', metavar='HH:MM', help='每天这个时间执行')
    q.add_argument('--chat', help='到点后在哪个会话里处理(在 agent 里执行时默认是当前会话)')
    q.add_argument('--root', help='话题 id(配合 --chat)')
    q = tsub.add_parser('rm', parents=[sub_acct], help='删除定时任务')
    q.add_argument('args', nargs=1, metavar='编号')
    p = sub.add_parser('config', parents=[acct], help='查看生效中的配置(配置项写在 .env 里)')
    p.set_defaults(fn=cmd_config)
    p = sub.add_parser('chats', parents=[acct], help='列出本地会话')
    p.add_argument('--limit', type=int, default=50)
    p.set_defaults(fn=cmd_chats)
    p = sub.add_parser('sessions', parents=[acct], help='列出 agent 会话(session 表)')
    p.add_argument('--limit', type=int, default=50)
    p.set_defaults(fn=cmd_sessions)
    p = sub.add_parser('messages', parents=[acct], help='读本地消息记录')
    p.add_argument('chat_id')
    p.add_argument('--anchor', default=None, help='话题 id;空字符串=仅主会话流')
    p.add_argument('--limit', type=int, default=50)
    p.add_argument('--json', action='store_true')
    p.set_defaults(fn=cmd_messages)
    p = sub.add_parser('search', parents=[acct], help='搜索用户/群')
    p.add_argument('query', nargs='+')
    p.set_defaults(fn=cmd_search)
    p = sub.add_parser('api', parents=[acct], help='调任意网关接口(类型名见 docs/cmd_table.md)')
    p.add_argument('type', help='proto 请求类型名(如 chats.PullChatsByIdsRequest)或 cmd 数字')
    p.add_argument('json_body', nargs='?', help='请求字段 JSON')
    p.set_defaults(fn=cmd_api)
    p = sub.add_parser('history', parents=[acct], help='拉取会话历史消息')
    p.add_argument('chat_id')
    p.add_argument('--start', type=int, help='起始 position(默认从最新往前)')
    p.add_argument('--count', type=int, default=20)
    p.add_argument('--save', action='store_true', help='同时写入本地库')
    p.add_argument('--json', action='store_true')
    p.set_defaults(fn=cmd_history)
    p = sub.add_parser('download', parents=[acct], help='下载消息里的图片/文件等资源')
    p.add_argument('msg_id', nargs='?', help='消息 id(从本地库查资源 key)')
    p.add_argument('--key', help='直接指定资源 key(img_v3_*/file_v3_*),需配合 --chat')
    p.add_argument('--chat', help='chat_id(配合 --key 或加速本地查找)')
    p.add_argument('-o', '--out', required=True, help='保存路径')
    p.set_defaults(fn=cmd_download)
    p = sub.add_parser('listen', parents=[acct], help='常驻接收消息')
    p.add_argument('--agent', action='store_true', help='接本地 coding agent 自动回复')
    p.set_defaults(fn=cmd_listen)
    p = sub.add_parser('web', help='启动 web 控制台(多账号管理/设置/日志)')
    p.add_argument('--host', default='127.0.0.1', help='监听地址,默认仅本机;非本机地址必须配 --token')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--token', default=None, help='访问令牌(也可用 LARKX_WEB_TOKEN)')
    p.add_argument('--no-autostart', action='store_true', help='不自动启动设置了「自启」的账号')
    p.set_defaults(fn=cmd_web)
    args, extra = parser.parse_known_args()
    if extra:
        # 消息内容是可变长的位置参数,写在选项后面时(lark send c1 -m "内容")argparse 会把它当成多余参数,这里接回去。
        # 只有长得像选项名的(--foo、-x)才算写错;「- 列表项」「-5 度」这种是正文
        target = {cmd_send: 'text', cmd_task: 'args', cmd_memory: 'args'}.get(getattr(args, 'fn', None))
        if not target or any(_OPTION_LIKE.fullmatch(x) for x in extra):
            parser.error('unrecognized arguments: ' + ' '.join(extra))
        setattr(args, target, list(getattr(args, target) or []) + extra)
    if hasattr(args, 'account') and not args.account:
        # agent 里执行时,没写 --account 就用调起它的那个账号(见 agent/backend.py)
        args.account = os.environ.get('LARKX_ACCOUNT') or None
    sys.exit(args.fn(args))


if __name__ == '__main__':
    main()
