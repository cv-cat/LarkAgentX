import asyncio
import threading
import time
from urllib.parse import urlencode
import requests
import websockets
from loguru import logger
from .auth import LarkAuth
from .proto import builders, compose, decoders, proto_pb2 as P
from .proto.ids import generate_access_key, generate_long_request_id, generate_request_id

CMD_PUSH_MESSAGES = 6    # 新消息推送
CMD_BATCH_COPY = 134     # 逐条转发:只推来消息 id 和最后一条
CMD_PUSH_SID = 6000      # 只推来 sid,完整内容要按 sid 再拉


class LarkClient:
    def __init__(self, auth: LarkAuth):
        self.auth = auth
        self.log = logger.bind(account=auth.account_id)
        self.auth.require_valid()
        if not self.auth.app_key or not self.auth.user_id:
            self.auth.validate(fetch_profile=True)
            self.auth.save()
        self.loop = asyncio.new_event_loop()
        self._loop_started = False
        self._thread_chats = {}
        self._self_chats = {}
        self._bots = {}
        self._bad_frames = 0
        self._bad_frame_warned = 0.0

    def build_ws_url(self) -> str:
        device_id = self.auth.device_id
        access_key = generate_access_key(f'2{self.auth.app_key}{device_id}f8a69f1719916z')
        ticket = self.auth.get_ticket()
        params = {
            'accept_encoding': 'gzip',
            'sdk_version': '7.72.8',
            'version_code': '7.72.8',
            'type': 'sdk_main',
            'platform': '',
            'terminal_type': '2',
            'device_model': '',
            'lark_version': '7.72.0',
            'net_status': '5',
            'lark_env': 'online',
            'request_id': generate_request_id(),
            'aid': '1',
            'fpid': '2',
            'device_id': device_id,
            'access_key': access_key,
            'ticket': ticket,
        }
        return f'{self.auth.region.ws_url}?{urlencode(params)}'

    @staticmethod
    def _wrap_frame(packet: P.Packet) -> bytes:
        frame = P.Frame()
        seconds = int(time.time())
        frame.seqid = seconds
        frame.logid = seconds
        frame.service = 1
        frame.method = 1
        entry = P.ExtendedEntry()
        entry.key = 'x-request-time'
        entry.value = str(int(time.time() * 1000))
        frame.headers.append(entry)
        frame.payloadType = 'pb'
        frame.payload = packet.SerializeToString()
        return frame.SerializeToString()

    async def send_ack(self, ws, sid: str):
        pkt = P.Packet()
        pkt.cmd = 1
        pkt.payloadType = 1
        pkt.sid = sid
        pkt.payload = b'\x08\x00'
        await ws.send(self._wrap_frame(pkt))

    async def send_heartbeat(self, ws):
        pkt = P.Packet()
        pkt.cmd = 4
        pkt.payloadType = 1
        await ws.send(self._wrap_frame(pkt))

    async def heartbeat_loop(self, ws, interval=30):
        try:
            while True:
                await asyncio.sleep(interval)
                await self.send_heartbeat(ws)
        except Exception as e:
            self.log.warning(f'心跳停止: {e}')

    def _ensure_loop(self):
        if not self._loop_started:
            def run_loop(loop):
                asyncio.set_event_loop(loop)
                loop.run_forever()
            threading.Thread(target=run_loop, args=(self.loop,), daemon=True).start()
            self._loop_started = True

    def close(self):
        if self._loop_started:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self._loop_started = False
        elif not self.loop.is_closed():
            self.loop.close()

    async def connect_websocket(self, on_message, on_connected=None):
        self._ensure_loop()
        url = self.build_ws_url()
        async with websockets.connect(url) as ws:
            self.log.info('WS 已连接')
            if on_connected:
                on_connected()
            heartbeat_task = asyncio.create_task(self.heartbeat_loop(ws))
            try:
                async for raw in ws:
                    try:
                        _, packet = decoders.parse_ws_frame(raw)
                        if 'json' in packet:
                            continue   # payloadEncoding=json 的帧不是消息推送,也不带 sid
                        sid, cmd = (packet.get('sid'), packet.get('cmd'))
                        if sid is not None:
                            await self.send_ack(ws, sid)
                        if cmd == CMD_PUSH_MESSAGES:
                            for msg in decoders.push_messages(packet.get('payload') or b''):
                                if msg.get('from_id'):
                                    asyncio.run_coroutine_threadsafe(self._dispatch(msg, on_message), self.loop)
                        elif cmd == CMD_PUSH_SID:
                            # 服务端只推来 sid(机器人卡片等很多消息这样推),要按 sid 再拉一次
                            asyncio.run_coroutine_threadsafe(self._pull_sids(decoders.push_sids(raw), on_message), self.loop)
                        elif cmd == CMD_BATCH_COPY:
                            # 有人一次逐条转发几条消息
                            asyncio.run_coroutine_threadsafe(self._batch_copy(packet.get('payload') or b'', on_message), self.loop)
                    except Exception as e:
                        self._warn_bad_frame(e)
            finally:
                heartbeat_task.cancel()

    def _warn_bad_frame(self, error):
        """解不开的帧:限频告警(每 10 分钟最多一条),不再静默跳过。"""
        self._bad_frames += 1
        now = time.time()
        if now - self._bad_frame_warned >= 600:
            self.log.warning(f'有 {self._bad_frames} 个 WS 帧解析失败,已跳过。最近一次: {error!r}')
            self._bad_frame_warned, self._bad_frames = now, 0

    async def _pull_sids(self, sids, on_message):
        if not sids:
            return
        try:
            resp = await asyncio.to_thread(self.api, 'improto.PullPacketsBySidsRequest', {'sids': sids})
            msgs = [m for p in ((resp or {}).get('packets') or {}).values() if int(p.get('cmd') or 0) == CMD_PUSH_MESSAGES
                    for m in decoders.push_messages(p.get('payload') or b'') if m.get('from_id')]
        except Exception as e:
            self.log.warning(f'按 sid 拉取推送失败,这几条等补收: {e}')
            return
        for msg in msgs:
            await self._dispatch(msg, on_message)

    async def _batch_copy(self, payload: bytes, on_message):
        try:
            ids, msgs = decoders.batch_copy_messages(payload)
            have = {str(m.get('msg_id')) for m in msgs}
            rest = [i for i in ids if i not in have]
            if rest:
                msgs += await asyncio.to_thread(self.messages_by_ids, rest)
            msgs = sorted((m for m in msgs if m.get('from_id')), key=lambda m: int(m.get('position') or 0))
        except Exception as e:
            self.log.warning(f'处理逐条转发的消息失败,这几条等补收: {e}')
            return
        for msg in msgs:
            await self._dispatch(msg, on_message)

    async def _dispatch(self, msg, on_message):
        try:
            # 推送里没有会话模式,话题群的根消息要查过 chatMode 才能归到它自己的话题
            if msg['scope'] == 'chat' and msg.get('chat_type') == 2 and await asyncio.to_thread(self.is_thread_chat, msg['chat_id']):
                msg['scope'], msg['anchor'] = decoders.resolve_scope(msg['msg_id'], msg['msg_type'], 2, '', '', thread_chat=True)
            await on_message(msg)
        except Exception as e:
            self.log.error(f'消息回调异常: {e}')

    def _gateway_post(self, packet: P.Packet) -> bytes:
        headers = {
            'content-type': 'application/x-protobuf',
            'accept': '*/*',
            'origin': self.auth.region.web_origin,
            'referer': self.auth.region.web_origin + '/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36',
            'x-appid': self.auth.gateway_app_id,
            'x-command': str(packet.cmd),
            'x-command-version': '5.7.0',
            'x-lgw-os-type': '1',
            'x-lgw-terminal-type': '2',
            'x-source': 'web',
            'x-web-version': '3.9.32',
            'x-request-id': generate_long_request_id(),
        }
        resp = requests.post(self.auth.region.gateway_url, headers=headers, cookies=self.auth.cookies, data=packet.SerializeToString(), timeout=15)
        resp.raise_for_status()
        return resp.content

    def send_msg(self, text: str, chat_id: str, root_id: str=None, quote_id: str=None, markdown: bool=False, mentions=None):
        """发文字(markdown=True 时按 markdown 发富文本;mentions 是 [{'user_id', 'name'}],正文里的「@名字」变成真正的 @)。
        返回服务端分配的消息 id;未能确认发送成功时返回 None。"""
        body = {'markdown': text} if markdown else {'text': text}
        return self.send(chat_id, root_id=root_id, quote_id=quote_id, mentions=mentions, **body)

    def send(self, chat_id: str, *, text: str=None, markdown: str=None, mentions=None, image_key: str=None, file: dict=None,
             root_id: str=None, quote_id: str=None):
        """发一条消息,返回消息 id;没发出去返回 None。root_id 回进话题,quote_id 在主会话里引用回复。"""
        target = root_id or quote_id
        thread_chat = bool(root_id) and self.is_thread_chat(chat_id)
        req = compose.message_request(str(chat_id), text=text, markdown=markdown, mentions=mentions or (), image_key=image_key,
                                      file=file, root_id=target, thread_chat=thread_chat, quote=bool(quote_id and not root_id))
        pkt = builders.wrap_packet(5, req, generate_long_request_id())
        try:
            content = self._gateway_post(pkt)
        except Exception as e:
            self.log.error(f'发送消息失败: {e}')
            return None
        try:
            msg_id = builders.decode_put_message_response(content)
        except Exception as e:
            self.log.error(f'服务端已接受发送请求,但响应解析失败,无法确认是否发出: {e}')
            return None
        if not msg_id or msg_id.startswith('-'):
            # 被拒收时(比如回复了不能当话题根的消息)返回的 id 是 -1,会话里并没有这条
            self.log.error(f'服务端没有返回有效的消息 id({msg_id or "空"}),消息没有发出')
            return None
        return msg_id

    def recall(self, msg_id: str):
        """撤回一条消息(只能撤回自己发的,且有时间限制)。失败时抛异常。"""
        self.api('messages.DeleteMessageRequest', {'id': str(msg_id)})

    def forward(self, msg_ids, chat_id: str, merge: bool=False) -> list:
        """把消息转发到 chat_id,返回新消息的 id 列表。merge=True 时合并成一条聊天记录(消息要来自同一个会话)。"""
        from .proto.ids import generate_request_cid
        chat_id = str(chat_id)
        if merge:
            resp = self.api('messages.PutMergeForwardMessageRequest', {
                'messageIds': [str(m) for m in msg_ids], 'toChatIds': [chat_id], 'cids': {chat_id: generate_request_cid()},
                'type': 'MESSAGE', 'locale': self.auth.region.locale})
            return self._forwarded_ids(resp, chat_id)
        out = []
        for m in msg_ids:
            resp = self.api('messages.PutTransmitMessageRequest', {'chatIds': [chat_id], 'messageId': str(m), 'cids': {chat_id: generate_request_cid()}})
            out += self._forwarded_ids(resp, chat_id)
        return out

    @staticmethod
    def _forwarded_ids(resp, chat_id: str) -> list:
        resp = resp or {}
        v = (resp.get('messages') or {}).get(chat_id) or {}
        if not v:
            for info in (resp.get('threadMessages') or {}).values():
                if info and not info.get('failed') and info.get('message'):
                    v = info['message']
        msg_id = str(v.get('id') or '')
        return [msg_id] if msg_id and not msg_id.startswith('-') else []

    def add_reaction(self, msg_id: str, reaction: str='OK'):
        """给一条消息加个表情回应(OK 是 👌)。注意:加在别人的消息上,那条消息会变成已读。"""
        self.api('reactions.PutReactionRequest', {'messageId': str(msg_id), 'reactionType': reaction})

    def messages_by_ids(self, msg_ids) -> list:
        """按 id 取消息(只读,不改变已读状态)。"""
        resp = self.api('messages.PullMessagesByIdsRequest', {'messageIds': [str(m) for m in msg_ids]})
        wanted = {str(m) for m in msg_ids}
        return [decoders.message_dict(v) for v in ((resp or {}).get('messages') or {}).values() if str(v.get('id')) in wanted]

    def feed_chats(self, since: float, max_pages: int=10) -> list:
        """消息列表里 since(秒级时间戳)之后有更新的会话 id。只读地翻收件箱卡片,不改变已读状态;
        折叠的会话盒子也展开。卡片按更新时间从新到旧排,翻到比 since 早就停。"""
        def chat_ids(cards):
            return [str(c['id']) for c in cards if c.get('type') in (1, 'CHAT') and int(c.get('updateTime') or 0) >= since]

        out, cursor = [], 0
        for _ in range(max_pages):
            data = {'type': 'INBOX', 'pullType': 'LOAD_MORE' if cursor else 'REFRESH', 'count': 100}
            if cursor:
                data['cursor'] = cursor
            resp = self.api('feed.PullFeedCardsRequest', data) or {}
            cards = resp.get('cards') or []
            out += chat_ids(cards)
            for box in cards:
                if box.get('type') in (5, 'BOX') and int(box.get('updateTime') or 0) >= since:
                    inner = self.api('feed.PullFeedCardsRequest', {'type': 'INBOX', 'pullType': 'REFRESH', 'count': 100,
                                                                   'parentCardId': int(box['id'])}) or {}
                    out += chat_ids(inner.get('cards') or [])
            cursor = int(resp.get('nextCursor') or 0)
            if not cards or not cursor or min(int(c.get('updateTime') or 0) for c in cards) < since:
                break
        return list(dict.fromkeys(out))

    def last_positions(self, chat_ids) -> dict:
        """各会话在服务端最新一条消息的 position。"""
        out = {}
        chat_ids = [str(c) for c in chat_ids]
        for i in range(0, len(chat_ids), 20):
            resp = self.api('chats.PullChatsByIdsRequest', {'chatIds': chat_ids[i:i + 20]})
            for cid, info in ((resp or {}).get('chats') or {}).items():
                out[str(cid)] = int(info.get('lastMessagePosition') or 0)
        return out

    def is_bot(self, user_id: str) -> bool:
        """这个 id 是不是机器人。消息上的发送者类型不可靠(机器人发的私聊也标成用户),要查一次,查过的记住。"""
        uid = str(user_id)
        if uid not in self._bots:
            try:
                resp = self.api('chatters.PullChattersByIdsRequest', {'chatterIds': [uid]}) or {}
                v = (resp.get('chatters') or {}).get(uid) or {}
            except Exception as e:
                self.log.debug(f'查询 {uid} 是否机器人失败,按真人处理: {e}')
                return False
            # Chatter.Type: 1 用户, 2 机器人, 3 AI 助手
            self._bots[uid] = v.get('type') in (2, 3, 'BOT', 'AI')
        return self._bots[uid]

    def search(self, query: str):
        pkt = builders.build_search_packet(query, generate_long_request_id(), self.auth.region.locale)
        return builders.decode_search_response(self._gateway_post(pkt))

    def create_chat(self, user_id: str):
        pkt = builders.build_create_chat_packet(str(user_id), generate_long_request_id())
        return builders.decode_put_chat_response(self._gateway_post(pkt))

    def get_user_name(self, user_id: str, chat_id: str):
        try:
            pkt = builders.build_user_info_packet(str(user_id), str(chat_id), generate_long_request_id())
            return builders.decode_user_info_response(self._gateway_post(pkt), self.auth.region.locale)
        except Exception:
            return None

    def mark_read(self, chat_id: str, max_position: int, message_ids=None) -> bool:
        data = {'chatId': str(chat_id), 'maxPosition': int(max_position)}
        if message_ids:
            data['messageIds'] = [str(m) for m in message_ids]
        try:
            self.api('messages.PutReadMessagesRequest', data)
            return True
        except Exception as e:
            self.log.debug(f'标记已读失败: {e}')
            return False

    def get_group_name(self, chat_id: str):
        try:
            pkt = builders.build_group_info_packet(str(chat_id), generate_long_request_id())
            return builders.decode_group_info_response(self._gateway_post(pkt))
        except Exception:
            return None

    def api(self, type_or_cmd, data: dict=None, raw: bytes=None):
        from .proto import gateway
        cmd, req_cls, resp_cls = gateway.resolve_cmd(type_or_cmd)
        req_msg = None
        if req_cls is not None:
            req_msg = gateway.request_from_dict(req_cls, data or {})
        pkt = gateway.build_packet(cmd, generate_long_request_id(), req_msg=req_msg, req_bytes=raw if req_msg is None else None)
        content = self._gateway_post(pkt)
        resp_pkt = P.Packet()
        resp_pkt.ParseFromString(content)
        if resp_cls is not None and resp_pkt.payload:
            return gateway.response_to_dict(resp_cls, resp_pkt.payload)
        from protobuf_to_dict import protobuf_to_dict
        return protobuf_to_dict(resp_pkt)

    def get_chat_info(self, chat_id: str):
        resp = self.api('chats.PullChatsByIdsRequest', {'chatIds': [str(chat_id)]})
        chats = (resp or {}).get('chats') or {}
        for _, chat in chats.items():
            return chat
        return None

    def is_thread_chat(self, chat_id: str) -> bool:
        chat_id = str(chat_id)
        if chat_id not in self._thread_chats:
            try:
                info = self.get_chat_info(chat_id)
            except Exception as e:
                self.log.debug(f'查询会话模式失败,按普通会话处理: {e}')
                return False
            if info is None:
                return False
            self._thread_chats[chat_id] = decoders.is_thread_chat(info)
        return self._thread_chats[chat_id]

    def is_self_chat(self, chat_id: str) -> bool:
        """「和自己的会话」。查询失败一律当不是,宁可不触发也不要误把发给别人的消息交给 agent。"""
        chat_id = str(chat_id)
        if chat_id not in self._self_chats:
            try:
                info = self.get_chat_info(chat_id)
            except Exception as e:
                self.log.debug(f'查询会话成员失败,按普通私聊处理: {e}')
                return False
            if info is None:
                return False
            self._self_chats[chat_id] = decoders.is_self_chat(info)
        return self._self_chats[chat_id]

    def pull_history(self, chat_id: str, positions, save_storage=None):
        resp = self.api('messages.PullMessagesByPositionsRequest', {'chatId': str(chat_id), 'positions': [int(p) for p in positions]})
        messages = (resp or {}).get('messages') or {}
        thread_chat = self.is_thread_chat(chat_id)
        out = []
        for pos_key, v in sorted(messages.items(), key=lambda kv: int(kv[0])):
            msg = decoders.message_dict(v, thread_chat=thread_chat, chat_id=chat_id)
            msg['position'] = msg['position'] or int(pos_key)
            out.append(msg)
            if save_storage is not None:
                try:
                    save_storage.save_message(msg)
                except Exception:
                    pass
        return out
