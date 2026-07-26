import asyncio
import sys

sys.path.insert(0, __import__('pathlib').Path(__file__).resolve().parents[1].as_posix())

from larkx.agent import AgentDispatcher, get_backend

msg1 = {
    'msg_id': '7666600000000000001', 'msg_type': 4, 'msg_type_name': 'TEXT',
    'from_id': '7314999000000000001', 'chat_id': '7627124577683934408',
    'chat_type': 1, 'chat_type_name': 'P2P', 'scope': 'chat', 'anchor': '',
    'at_me': False, 'root_id': '', 'parent_id': '', 'cid': '', 'position': 1,
    'create_time': 1785003200,
    'content': '在吗?帮我验证下数字人链路:收到这条后回我一句"链路正常"就行',
    '_chat_name': 'Cato的智能伙伴', '_sender_name': 'Cato的智能伙伴',
}

msg2 = dict(msg1, msg_id='7666600000000000002',
            content='周末愉快呀~ 好好休息😄')


class SpyBackend:
    def __init__(self, inner):
        self.inner = inner
        self.prompts = []

    async def run(self, session_key, prompt, **kwargs):
        self.prompts.append(prompt)
        return await self.inner.run(session_key, prompt, **kwargs)


async def main():
    backend = SpyBackend(get_backend())

    async def reply_fn(chat_id, text, root_id=None):
        print('>>> reply_fn 被调用(新模型下不该发生):', text)

    disp = AgentDispatcher(backend, reply_fn)

    print('=' * 20, '案例 1: 明确要求回复', '=' * 20)
    await disp.handle_message('demo:final', msg1)

    print()
    print('=' * 20, '案例 2: 纯寒暄(不该回)', '=' * 20)
    await disp.handle_message('demo:final', msg2)

    print()
    print('=' * 20, '喂给 agent 的完整 prompt(案例 1)', '=' * 20)
    print(backend.prompts[0])


asyncio.run(main())
