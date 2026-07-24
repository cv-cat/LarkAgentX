# -*- coding: utf-8 -*-
import os
import sys
import random
import datetime
from loguru import logger
from sqlalchemy import func, desc
from mcp.server.fastmcp import FastMCP
from typing_extensions import Annotated

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.core.llm_service import LLMService
from app.db.session import get_db_session, close_db_session
from app.db.models import Message
from app.api.auth import get_auth
from app.api.lark_client import LarkClient

mcp = FastMCP("LARK_MCP_SERVER")
registered_tools = []
llm_service = LLMService()


def register_tool(name: str, description: str):
    def decorator(func):
        mcp.tool(name=name, description=description)(func)
        registered_tools.append((name, description))
        return func
    return decorator

@register_tool(name="list_tools", description="List all available tools and their descriptions")
def list_tools() -> str:
    result = "🛠️ 当前可用功能列表：\n"
    for name, desc in registered_tools:
        result += f"- `{name}`：{desc}\n"
    return result

@register_tool(name="get_weather", description="获取城市天气")
def get_weather(
    city: Annotated[str, "城市名称"] = "北京"
):
    """
    获取城市天气
    :param city: 城市名称
    :return: 城市天气
    """
    from extension.weather_api.api import get_city_weather
    return get_city_weather(city)

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

    _ = lark_client.send_msg(content, chatId)
    return f"成功向 {user} 发送了私信: '{content}'"

@register_tool(name="download_image", description="下载并解密飞书图片消息 {image_id:图片ID key_hex:解密密钥(hex) iv_hex:解密IV(hex)}")
def download_image(image_id: str, key_hex: str, iv_hex: str) -> str:
    """下载并解密飞书加密图片"""
    try:
        from app.api.image_decrypt import download_and_decrypt_image
        lark_client = LarkClient(get_auth())
        cookie_str = "; ".join(f"{k}={v}" for k, v in lark_client.auth.cookie.items())
        result = download_and_decrypt_image(
            image_id=image_id,
            key_hex=key_hex,
            iv_hex=iv_hex,
            cookie=cookie_str,
        )
        if result.get('cached'):
            return f"图片已缓存: {result['path']} ({result['mime_type']}, {result['size']} bytes)"
        return f"图片已下载: {result['path']} ({result['mime_type']}, {result['size']} bytes, SHA256: {result['sha256'][:16]}...)"
    except Exception as e:
        return f"图片下载失败: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport="stdio")