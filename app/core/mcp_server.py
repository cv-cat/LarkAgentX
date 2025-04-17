# -*- coding: utf-8 -*-
import os
import sys
import random
import datetime
from loguru import logger
from sqlalchemy import func, desc
from mcp.server.fastmcp import FastMCP


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from app.core.llm_service import LLMService
from app.db.session import get_db_session, close_db_session
from app.db.models import Message, Schedule
from app.api.auth import get_auth
from app.api.lark_client import LarkClient

mcp = FastMCP("LARK_MCP_SERVER")
registered_tools = []
llm_service = LLMService()



def register_tool(name: str, description: str):
    def decorator(func):
        nonlocal description
        __func_name__ = func.__name__
        __module_name__ = __file__.split(f'{BASE_DIR}\\')[-1]
        __module_name__ = __module_name__.split('.')[0]
        __module_name__ = __module_name__.replace('\\', '.')
        description += f"\nmodule_name: {__module_name__}\nfunction_name: {__func_name__}\n"
        mcp.tool(name=name, description=description)(func)
        registered_tools.append((name, description))
        return func
    return decorator

@register_tool(name="add_schedule_job",
               description=""
                           "Add a schedule job"
                           "@invoker 当前调用的用户名"
                           "@module_name 工具的模块名称\n"
                           "@function_name 工具的函数名称\n"
                           "@args 工具的入参(以列表形式)\n"
                           "@cron cron表达式 (例如：'0/5 * * * * *' 表示每5秒执行一次)\n"
                           "")
def add_schedule_job(invoker:str, module_name: str,function_name: str, args, cron: str):
    db = get_db_session()
    try:
        cron.replace('?', '*')
        new_schedule = Schedule(
            module_name=module_name,
            function_name=function_name,
            arguments=args,
            cron=cron,
            created_by=invoker
        )
        db.add(new_schedule)
        db.commit()
        return f'新增定时任务成功 {new_schedule}'
    except Exception as e:
        return f'定时任务新增失败 : module_name:{module_name}, function_name:{function_name}, args:{args}, cron:{cron}, 原因: {e}'
    finally:
        close_db_session(db)

@register_tool(name="list_schedule_job",
               description=""
                           "list all schedule jobs"
                           "@invoker 当前调用的用户名"
                           "")
def list_schedule_job(invoker:str):
    db = get_db_session()
    try:
        tasks = db.query(Schedule).filter(Schedule.created_by==invoker).all()
        task_str = ''
        for task in tasks:
            task_str += f"任务ID: {task.id}, 模块名称: {task.module_name}, 函数名称: {task.function_name}, 入参: {task.arguments}, cron表达式: {task.cron}, 状态: {'激活' if task.active else '禁用'}\n"
        return f'你的定时任务列表：\n{task_str}'
    except Exception as e:
        return f'定时任务查询失败 原因: {e}'
    finally:
        close_db_session(db)

@register_tool(name="deactivate_schedule_job",
               description=""
                           "deactivate schedule job by task id"
                           "@invoker 当前调用的用户名"
                           "@task_id 要禁用的任务ID"
                           "")
def deactivate_schedule_job(invoker:str, task_id):
    if isinstance(task_id, str):
        try:
            task_id = int(task_id)
        except ValueError:
            return f'任务ID:{task_id} 格式错误'
    db = get_db_session()
    try:
        task = db.query(Schedule).filter(Schedule.id==task_id, Schedule.created_by==invoker).first()
        if not task:
            return f'任务:{task_id} 不存在'
        task.active = False
        db.commit()
        return f'任务:{task_id} 已禁用'
    except Exception as e:
        return f'定时任务禁用失败 原因: {e}'
    finally:
        close_db_session(db)

@register_tool(name="activate_schedule_job",
               description=""
                           "activate schedule job by task id"
                           "@invoker 当前调用的用户名"
                           "@task_id 要激活的任务ID"
                           "")
def activate_schedule_job(invoker:str, task_id):
    if isinstance(task_id, str):
        try:
            task_id = int(task_id)
        except ValueError:
            return f'任务ID:{task_id} 格式错误'
    db = get_db_session()
    try:
        task = db.query(Schedule).filter(Schedule.id==task_id, Schedule.created_by==invoker).first()
        if not task:
            return f'任务:{task_id} 不存在'
        task.active = True
        db.commit()
        return f'任务:{task_id} 已激活'
    except Exception as e:
        return f'定时任务激活失败 原因: {e}'
    finally:
        close_db_session(db)

@register_tool(name="list_tools", description="List all available tools and their descriptions")
def list_tools() -> str:
    result = "🛠️ 当前可用功能列表：\n"
    for name, desc in registered_tools:
        result += f"- `{name}`：{desc}\n"
    return result

@register_tool(name="extra_order_from_content", description="提取文字中的订单信息，包括订单号、商品名称、数量等，以json格式返回")
def extra_order_from_content(content: str) -> str:
    """
    提取订单信息
    :param content: 消息内容
    :return: 提取的订单信息
    """
    res = llm_service.chat_completion(
        messages=[
            {"role": "user", "content": content},
            {"role": "system", "content": "请提取订单信息，包括订单号、商品名称、数量等，以json格式返回"},
        ],
        tools=None,
        model="qwen-plus"
    )
    if res and res.choices:
        content = res.choices[0].message.content
        if content:
            return content
    return "未能提取到订单信息，请检查消息内容是否包含有效的订单信息。"


@register_tool(name="tell_joke", description="Tell a random joke")
def tell_joke() -> str:
    jokes = [
        "为什么程序员都喜欢黑色？因为他们不喜欢 bug 光。",
        "Python 和蛇有什么共同点？一旦缠上你就放不下了。",
        "为什么 Java 开发者很少被邀去派对？因为他们总是抛出异常。",
    ]
    return random.choice(jokes)


@register_tool(name="get_time", description="Get the current time")
def get_time() -> str:
    now = datetime.datetime.now()
    return f"当前时间是 {now.strftime('%Y-%m-%d %H:%M:%S')}"


@register_tool(name="fortune", description="Draw a random fortune")
def fortune() -> str:
    fortunes = [
        "大吉：今天适合尝试新事物！✨",
        "中吉：平稳的一天，保持专注。",
        "小吉：会有小惊喜出现～",
        "凶：注意不要过度疲劳。",
        "大凶：小心电子设备出问题 🧯"
    ]
    return random.choice(fortunes)


@register_tool(name="count_daily_speakers", description="获取今天发言的人数统计")
def count_daily_speakers() -> str:
    """查询数据库统计今天有多少人发言"""
    db = get_db_session()
    try:
        today = datetime.datetime.now().date()
        today_start = datetime.datetime.combine(today, datetime.time.min)
        today_end = datetime.datetime.combine(today, datetime.time.max)
        speaker_count = db.query(func.count(func.distinct(Message.user_id)))\
            .filter(Message.message_time >= today_start)\
            .filter(Message.message_time <= today_end)\
            .scalar()
        message_count = db.query(func.count(Message.id))\
            .filter(Message.message_time >= today_start)\
            .filter(Message.message_time <= today_end)\
            .scalar()

        return f"今天已有 {speaker_count} 人发言，共发送了 {message_count} 条消息。"
    except Exception as e:
        logger.error(f"查询今日发言人数时出错: {str(e)}")
        return f"查询失败: {str(e)}"
    finally:
        close_db_session(db)

@register_tool(name="get_top_speaker_today", description="获取今天发言最多的用户")
def get_top_speaker_today() -> str:
    """查询数据库统计今天谁的发言最多"""
    db = get_db_session()
    try:
        today = datetime.datetime.now().date()
        today_start = datetime.datetime.combine(today, datetime.time.min)
        today_end = datetime.datetime.combine(today, datetime.time.max)
        result = db.query(
                Message.user_name,
                Message.user_id,
                func.count(Message.id).label('message_count')
            )\
            .filter(Message.message_time >= today_start)\
            .filter(Message.message_time <= today_end)\
            .group_by(Message.user_id, Message.user_name)\
            .order_by(desc('message_count'))\
            .first()
        if not result:
            return "今天还没有人发言。"
        user_name, user_id, message_count = result
        return f"今日话题王: {user_name}，共发送了 {message_count} 条消息。"
    except Exception as e:
        logger.error(f"查询今日最多发言用户时出错: {str(e)}")
        return f"查询失败: {str(e)}"
    finally:
        close_db_session(db)

@register_tool(name="send_message", description="给指定用户发送消息 {user:用户名称 content:消息内容}")
def send_message(user: str='', content: str='', user_id: str = None) -> str:
    """给指定用户发送私信"""
    lark_client = LarkClient(get_auth())
    if user_id is not None:
        userId = user_id
    else:
        SearchResponsePacket, userAndGroupIds = lark_client.search_some(user)
        if not userAndGroupIds:
            return f"未找到用户 '{user}'。"
        user_or_group_id = userAndGroupIds[0]
        if user_or_group_id['type'] == 'user':
            logger.info(f'搜索到用户: {user}')
            userId = user_or_group_id['id']
        else:
            logger.info('搜索到群组')
            chatId = user_or_group_id['id']
            group_name = lark_client.get_group_name(chatId)
            logger.info(f'群组名称: {group_name}')
            return f"'{user}' 是一个群组，不是用户，无法发送私信。"
    PutChatResponsePacket, chatId = lark_client.create_chat(userId)
    found_user_name = lark_client.get_other_user_all_name(userId, chatId)
    logger.info(f'用户名称: {found_user_name}')
    _ = lark_client.send_msg(content, chatId)
    return f"成功向 {user} 发送了私信: '{content}'"

if __name__ == "__main__":
    mcp.run(transport="stdio")
