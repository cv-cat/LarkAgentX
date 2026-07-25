import asyncio
import threading
import time

import requests
import websockets
import static.proto_pb2 as FLY_BOOK_PROTO
from loguru import logger
from urllib.parse import urlencode
from app.api.auth import get_auth
from builder.header import HeaderBuilder
from builder.proto import ProtoBuilder
from app.config.settings import settings



# Command constants
CMD_DELETE_MESSAGE = 9
CMD_PUT_REACTION = 25
CMD_DELETE_REACTION = 26
CMD_MARK_READ = 40
CMD_CREATE_PIN = 5100
CMD_DELETE_PIN = 5103
CMD_EDIT_MESSAGE = 900010

# Emoji reaction aliases
EMOJI_ALIASES = {
    "thumbsup": "THUMBSUP", "赞": "THUMBSUP", "ok": "OK",
    "heart": "HEART", "❤️": "HEART", "love": "HEART",
    "laugh": "LAUGH", "笑": "LAUGH", "smile": "SMILE",
    "sad": "SAD", "cry": "SAD", "shocked": "SHOCKED",
    "angry": "ANGRY", "fire": "FIRE", "🔥": "FIRE",
    "clap": "CLAP", "👏": "CLAP", "party": "PARTY",
    "pray": "FINGERHEART", "cool": "COOL",
    "jiayi": "JIAYI", "+1": "JIAYI", "加一": "JIAYI",
}


class LarkClient:
    loop = asyncio.new_event_loop()
    """Client for interacting with Lark APIs"""

    def __init__(self, auth):
        self.auth = auth
        self.base_url = settings.LARK_BASE_URL
        self.csrf_token_url = settings.LARK_CSRF_TOKEN_URL
        self.user_info_url = settings.LARK_USER_INFO_URL
        self.ws_base_url = settings.LARK_WS_URL

        _, self.x_csrf_token = self.get_csrf_token()
        _, self.me_id = self.get_self_user_info()
        self.me_id = str(self.me_id)

    def get_csrf_token(self):
        from builder.params import ParamsBuilder
        """Get CSRF token"""
        headers = HeaderBuilder.build_get_csrf_token_header().get()
        params = ParamsBuilder.build_get_csrf_token_param().get()
        response = requests.post(self.csrf_token_url, headers=headers, cookies=self.auth.cookie, params=params)
        res_json = response.json()
        x_csrf_token = response.cookies.get('swp_csrf_token')
        if not x_csrf_token:
            logger.error("未在响应中找到swp_csrf_token")
        return res_json, x_csrf_token

    def get_self_user_info(self):
        from builder.params import ParamsBuilder
        """Get current user info"""
        headers = HeaderBuilder.build_get_user_info_header(self.x_csrf_token).get()
        params = ParamsBuilder.build_get_user_info_param().get()
        response = requests.get(self.user_info_url, headers=headers, cookies=self.auth.cookie, params=params)
        res_json = response.json()
        user_id = res_json['data']['user']['id']
        return res_json, user_id

    def search_some(self, query):
        """Search for users or groups"""
        headers = HeaderBuilder.build_search_header().get()
        Packet = ProtoBuilder.build_search_request_proto(headers['x-request-id'], query)
        response = requests.post(self.base_url, headers=headers, cookies=self.auth.cookie, data=Packet.SerializeToString())
        SearchResponsePacket, userAndGroupIds = ProtoBuilder.decode_search_response_proto(response.content)
        return SearchResponsePacket, userAndGroupIds

    def create_chat(self, userId):
        """Create a chat with a user or group"""
        headers = HeaderBuilder.build_create_chat_header().get()
        Packet = ProtoBuilder.build_create_chat_request_proto(headers['x-request-id'], userId)
        response = requests.post(self.base_url, headers=headers, cookies=self.auth.cookie, data=Packet.SerializeToString())
        PutChatResponsePacket, chatId = ProtoBuilder.decode_create_chat_response_proto(response.content)
        return PutChatResponsePacket, chatId

    def send_msg(self, sends_text, chatId):
        """Send a message to a chat"""
        headers = HeaderBuilder.build_send_msg_header().get()
        Packet = ProtoBuilder.build_send_message_request_proto(sends_text, headers['x-request-id'], chatId)
        response = requests.post(self.base_url, headers=headers, cookies=self.auth.cookie, data=Packet.SerializeToString())
        return response

    def get_other_user_all_name(self, user_id, chat_id):
        """Get another user's display name"""
        headers = HeaderBuilder.build_get_user_all_name_header().get()
        packet = ProtoBuilder.build_get_user_all_name_request_proto(headers['x-request-id'], user_id, chat_id)
        response = requests.post(self.base_url, headers=headers, cookies=self.auth.cookie, data=packet.SerializeToString())
        content = response.content
        user_name = ProtoBuilder.decode_info_response_proto(content)
        return user_name

    def get_group_name(self, chat_id):
        """Get group chat name"""
        headers = HeaderBuilder.build_get_group_name_header().get()
        packet = ProtoBuilder.build_get_group_name_request_proto(headers['x-request-id'], chat_id)
        response = requests.post(self.base_url, headers=headers, cookies=self.auth.cookie, data=packet.SerializeToString())
        group_name = ProtoBuilder.decode_group_info_response_proto(response.content)
        return group_name

    def recall_message(self, chat_id, message_id):
        """Recall/delete a message (cmd=9)"""
        headers = HeaderBuilder.build_proto_header(CMD_DELETE_MESSAGE, "1.0.0").get()
        packet = ProtoBuilder.build_delete_message_request_proto(headers['x-request-id'], message_id, chat_id)
        response = requests.post(self.base_url, headers=headers, cookies=self.auth.cookie, data=packet.SerializeToString())
        return self._check_response(response)

    def edit_message(self, message_id, new_text):
        """Edit a text message (cmd=900010)"""
        headers = HeaderBuilder.build_proto_header(CMD_EDIT_MESSAGE, "7.63.0").get()
        packet = ProtoBuilder.build_edit_message_request_proto(headers['x-request-id'], message_id, new_text)
        response = requests.post(self.base_url, headers=headers, cookies=self.auth.cookie, data=packet.SerializeToString())
        return self._check_response(response)

    def add_reaction(self, message_id, reaction_type):
        """Add emoji reaction to a message (cmd=25)"""
        reaction_type = EMOJI_ALIASES.get(reaction_type, reaction_type)
        headers = HeaderBuilder.build_proto_header(CMD_PUT_REACTION, "7.63.0").get()
        packet = ProtoBuilder.build_reaction_request_proto(headers['x-request-id'], CMD_PUT_REACTION, message_id, reaction_type)
        response = requests.post(self.base_url, headers=headers, cookies=self.auth.cookie, data=packet.SerializeToString())
        return self._check_response(response)

    def remove_reaction(self, message_id, reaction_type):
        """Remove emoji reaction from a message (cmd=26)"""
        reaction_type = EMOJI_ALIASES.get(reaction_type, reaction_type)
        headers = HeaderBuilder.build_proto_header(CMD_DELETE_REACTION, "7.63.0").get()
        packet = ProtoBuilder.build_reaction_request_proto(headers['x-request-id'], CMD_DELETE_REACTION, message_id, reaction_type)
        response = requests.post(self.base_url, headers=headers, cookies=self.auth.cookie, data=packet.SerializeToString())
        return self._check_response(response)

    def pin_message(self, chat_id, message_id):
        """Pin a message (cmd=5100)"""
        headers = HeaderBuilder.build_proto_header(CMD_CREATE_PIN, "7.63.0").get()
        packet = ProtoBuilder.build_pin_request_proto(headers['x-request-id'], chat_id, message_id)
        response = requests.post(self.base_url, headers=headers, cookies=self.auth.cookie, data=packet.SerializeToString())
        result = self._check_response(response)
        # Try to extract pin ID from response for later unpin
        if response.status_code == 200:
            pin_id = ProtoBuilder.decode_pin_response_proto(response.content)
            if pin_id:
                if not hasattr(self, '_pin_cache'):
                    self._pin_cache = {}
                self._pin_cache[str(message_id)] = pin_id
        return result

    def unpin_message(self, chat_id, message_id):
        """Unpin a message (cmd=5103)"""
        pin_id = getattr(self, '_pin_cache', {}).get(str(message_id), message_id)
        headers = HeaderBuilder.build_proto_header(CMD_DELETE_PIN, "7.63.0").get()
        packet = ProtoBuilder.build_unpin_request_proto(headers['x-request-id'], chat_id, pin_id)
        response = requests.post(self.base_url, headers=headers, cookies=self.auth.cookie, data=packet.SerializeToString())
        result = self._check_response(response)
        if response.status_code == 200 and hasattr(self, '_pin_cache'):
            self._pin_cache.pop(str(message_id), None)
        return result

    def mark_read(self, chat_id, message_id):
        """Mark messages as read up to given message (cmd=40)"""
        headers = HeaderBuilder.build_proto_header(CMD_MARK_READ, "7.63.0").get()
        packet = ProtoBuilder.build_mark_read_request_proto(headers['x-request-id'], chat_id, message_id)
        response = requests.post(self.base_url, headers=headers, cookies=self.auth.cookie, data=packet.SerializeToString())
        return self._check_response(response)

    def send_msg_in_thread(self, sends_text, chatId, rootId):
        """Send a message in a thread (cmd=5 with rootId)"""
        headers = HeaderBuilder.build_proto_header(5, "5.7.0").get()
        packet = ProtoBuilder.build_send_message_in_thread_request_proto(sends_text, headers['x-request-id'], chatId, rootId)
        response = requests.post(self.base_url, headers=headers, cookies=self.auth.cookie, data=packet.SerializeToString())
        return response

    def _check_response(self, response):
        """Check protobuf response status"""
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
        try:
            packet = FLY_BOOK_PROTO.Packet()
            packet.ParseFromString(response.content)
            if packet.status != 0:
                raise Exception(f"API error: status={packet.status}")
            return True
        except Exception as e:
            if "status" in str(e):
                raise
            return True

    async def send_ack(self, ws, packet_sid):
        """Send acknowledgment for received messages"""
        payload = FLY_BOOK_PROTO.Packet()
        payload.cmd = 1
        payload.payloadType = 1
        payload.sid = packet_sid
        payload = payload.SerializeToString()

        frame = FLY_BOOK_PROTO.Frame()
        current = int(time.time() * 1000)
        frame.seqid = current
        frame.logid = current
        frame.service = 1
        frame.method = 1

        extended_entry = FLY_BOOK_PROTO.ExtendedEntry()
        extended_entry.key = 'x-request-time'
        extended_entry.value = f'{current}000'
        frame.headers.append(extended_entry)
        frame.payloadType = "pb"
        frame.payload = payload

        serialized_frame = frame.SerializeToString()
        await ws.send(serialized_frame)

    @staticmethod
    def start_message_processor():
        def run_loop(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()
        threading.Thread(target=run_loop, args=(LarkClient.loop,)).start()

    async def connect_websocket(self, message_handler):
        """Connect to Lark websocket and handle messages"""
        from builder.params import ParamsBuilder
        params = ParamsBuilder.build_receive_msg_param(self.auth).get()
        url = f"{self.ws_base_url}?{urlencode(params)}"
        async with websockets.connect(url) as websocket:
            LarkClient.start_message_processor()
            async for message in websocket:
                try:
                    packet_sid = ProtoBuilder.extra_packet_id(message)
                    await self.send_ack(websocket, packet_sid)
                    ReceiveTextContent = ProtoBuilder.decode_receive_msg_proto(message)
                    asyncio.run_coroutine_threadsafe(self.process_msg(ReceiveTextContent, message_handler), LarkClient.loop)
                except Exception as e:
                    # logger.error(f"Error processing message: {e}")
                    continue

    async def process_msg(self, msg, message_handler):
        from_id, chat_id, chat_type, content = msg['fromId'], msg['chatId'], msg['chatType'], msg['content']
        message_id = msg.get('messageId')
        user_name = self.get_other_user_all_name(from_id, chat_id)
        is_group_chat = (chat_type == 2)
        group_name = None
        if is_group_chat:
            group_name = self.get_group_name(chat_id)
        await message_handler(
            user_name=user_name,
            user_id=from_id,
            content=content,
            is_group_chat=is_group_chat,
            group_name=group_name,
            chat_id=chat_id,
            message_id=message_id
        )


if __name__ == '__main__':
    auth = get_auth()
    lark_client = LarkClient(auth)
    fromId = 7478340774602522627
    chatId = 7478340637890854916
    chatId = 7373962691750363140
    user_name = lark_client.get_other_user_all_name(fromId, chatId)
    print(user_name)

    group_name = lark_client.get_group_name(chatId)
    print(group_name)
