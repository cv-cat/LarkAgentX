# -*- coding: utf-8 -*-
import os
import sys
import random
import datetime

import requests
from loguru import logger
from sqlalchemy import func, desc
from mcp.server.fastmcp import FastMCP



BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from app.config.settings import Settings
from app.db.session import get_db_session, close_db_session
from app.db.models import Message
from app.api.auth import get_auth
from app.api.lark_client import LarkClient

mcp = FastMCP("LARK_MCP_SERVER")
registered_tools = []

def register_tool(name: str, description: str):
    def decorator(func):
        mcp.tool(name=name, description=description)(func)
        registered_tools.append((name, description))
        return func
    return decorator

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


@register_tool(name="roll_dice", description="Roll a dice with a given number of sides")
def roll_dice(sides: int = 6) -> str:
    result = random.randint(1, sides)
    return f"🎲 你掷出了：{result}"


@register_tool(name="make_todo_list", description="Create a simple todo list from comma-separated tasks")
def make_todo_list(tasks: str) -> str:
    task_list = [task.strip() for task in tasks.split(',')]
    return "\n".join(f"- [ ] {task}" for task in task_list)

@register_tool(name="translate_to_chinese", description="Translate an English word to Chinese")
def translate_to_chinese(word: str) -> str:
    dictionary = {
        "apple": "苹果",
        "banana": "香蕉",
        "computer": "电脑",
        "sun": "太阳",
        "moon": "月亮"
    }
    return dictionary.get(word.lower(), "这个词我还没学会呢~")


@register_tool(name="countdown", description="Create a countdown from a given number")
def countdown(start: int) -> str:
    if start < 1:
        return "请输入大于 0 的数字"
    return " → ".join(str(i) for i in range(start, 0, -1)) + " → 🚀"


@register_tool(name="random_color", description="Generate a random hex color")
def random_color() -> str:
    return "#{:06x}".format(random.randint(0, 0xFFFFFF))


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

@register_tool(name="list_tools", description="List all available tools and their descriptions")
def list_tools() -> str:
    result = "🛠️ 当前可用功能列表：\n"
    for name, desc in registered_tools:
        result += f"- `{name}`：{desc}\n"
    return result

# @register_tool(name="get_weather", description="获得指定地区的天气预报 {city:城市名称}")
# def get_weather(city: str) -> str:
#     """获取指定城市的天气预报"""
#     try:
#         wea_api_key = Settings.get("WEATHER_API_KEY", None)
#         if wea_api_key is None:
#             return "天气 API 密钥未设置，请联系管理员。"
#         geo_url = 'https://restapi.amap.com/v3/geocode/geo'
#         geo_params = {
#             'key': wea_api_key,
#             'address': city,
#         }
#         adcode = 0
#         geo_res = requests.get(geo_url, params=geo_params).json()
#         if geo_res['status'] == '1':
#             adcode = geo_res['geocodes'][0]['adcode']
#         url = 'https://restapi.amap.com/v3/weather/weatherInfo'
#         params = {
#             'key': wea_api_key,
#             'city': adcode,
#             'extensions': 'all'
#         }
#         res = requests.get(url, params=params).json()
#         if res['status'] == '1':
#             return res
#         else:
#             return f"获取天气信息失败: {res['info']}"
#     except Exception as e:
#         logger.error(f"获取天气信息失败: {str(e)}")
#         return f"获取天气信息失败: {str(e)}"

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
def send_message(user: str, content: str) -> str:
    """给指定用户发送私信"""
    lark_client = LarkClient(get_auth())
    SearchResponsePacket, userAndGroupIds = lark_client.search_some(user)
    if not userAndGroupIds:
        return f"未找到用户 '{user}'。"
    user_or_group_id = userAndGroupIds[0]
    if user_or_group_id['type'] == 'user':
        logger.info(f'搜索到用户: {user}')
        userId = user_or_group_id['id']
        PutChatResponsePacket, chatId = lark_client.create_chat(userId)
        found_user_name = lark_client.get_other_user_all_name(userId, chatId)
        logger.info(f'用户名称: {found_user_name}')
    else:
        logger.info('搜索到群组')
        chatId = user_or_group_id['id']
        group_name = lark_client.get_group_name(chatId)
        logger.info(f'群组名称: {group_name}')
        return f"'{user}' 是一个群组，不是用户，无法发送私信。"

    res = lark_client.send_msg(content, chatId)
    return f"成功向 {user} 发送了私信: '{content}'"

if __name__ == "__main__":
    mcp.run(transport="stdio")