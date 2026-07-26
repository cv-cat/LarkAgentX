import asyncio
import sys

sys.path.insert(0, __import__('pathlib').Path(__file__).resolve().parents[1].as_posix())

from larkx.agent import AgentDispatcher, get_backend
from larkx.agent.dispatcher import build_xml_message

msg1 = {
    'msg_id': '7666999999999999001', 'msg_type': 4, 'msg_type_name': 'TEXT',
    'from_id': '7314999000000000001', 'chat_id': '7627124577683934408',
    'chat_type': 1, 'chat_type_name': 'P2P', 'scope': 'chat', 'anchor': '',
    'at_me': False, 'root_id': '', 'parent_id': '', 'cid': '', 'position': 1,
    'create_time': 1785000000,
    'content': '在吗?帮我确认一下现在的消息链路是不是通的,顺便说一句你好',
    'content_data': None,
}

msg2 = dict(msg1, msg_id='7666999999999999002',
            content='[系统消息] type=605 群公告已更新')


class SpyBackend:
    def __init__(self, inner):
        self.inner = inner
        self.prompts = []

    async def run(self, session_key, prompt):
        self.prompts.append(prompt)
        return await self.inner.run(session_key, prompt)


async def main():
    backend = SpyBackend(get_backend())

    async def reply_fn(chat_id, text, root_id=None):
        print('>>> reply_fn 被调用(新模型下不该发生):', text)

    disp = AgentDispatcher(backend, reply_fn)

    print('=' * 20, '案例 1: 需要回复的消息', '=' * 20)
    print(build_xml_message(msg1))
    print('-' * 60)
    await disp.handle_message('demo:2', msg1)

    print()
    print('=' * 20, '案例 2: 系统通知(不该回复)', '=' * 20)
    print(build_xml_message(msg2))
    print('-' * 60)
    await disp.handle_message('demo:2', msg2)


asyncio.run(main())
