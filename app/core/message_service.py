"""
Service for processing and storing Lark messages
"""
import json
import os

from loguru import logger
from datetime import datetime
from app.db.models import Message
from app.db.session import get_db_session, close_db_session
from app.config.settings import settings
from app.core.llm_service import LLMService
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

class MessageService:
    """Service for processing and storing messages"""
    
    def __init__(self, lark_client):
        self.lark_client = lark_client
        self.db = get_db_session()
        self.llm_service = LLMService()
        self.mcp_transport = PythonStdioTransport("app/core/mcp_server.py", env={"PATHEXT": os.environ.get("PATHEXT", "")})
        self.system_message = {"role": "system", "content": "你是一个很有帮助的助手。当用户提问需要调用工具时，请使用 tools 中定义的函数。"}
    
    async def process_message(self, user_name, user_id, content, is_group_chat, group_name, chat_id):
        """Process and store a message in the database"""
        try:
            message_source = f"群聊 {group_name}" if is_group_chat else "私聊"
            logger.info(f"收到{message_source}消息 - 用户: {user_name}, 内容: {content}")
            if not content or not content.strip():
                logger.warning("收到非纯文本消息，跳过存储")
                return
            message = Message(
                user_name=user_name,
                user_id=user_id,
                content=content,
                is_group_chat=is_group_chat,
                group_name=group_name,
                chat_id=chat_id,
                message_time=datetime.now()
            )
            self.db.add(message)
            self.db.commit()
            if content.strip().startswith(settings.FUNCTION_TRIGGER_FLAG):
                await self._handle_function_call(user_name, content, chat_id, is_group_chat)
        except Exception as e:
            self.db.rollback()
            logger.error(f"存储消息时出错: {str(e)}")

    
    async def _handle_function_call(self, user_name, content, chat_id, is_group_chat):
        """处理flag触发的函数调用请求并发送响应"""
        try:
            logger.info(f"触发flag函数调用 - 用户: {user_name}, 内容: {content}")
            query = content.strip()[len(settings.FUNCTION_TRIGGER_FLAG):].strip()
            if not self.llm_service.is_available():
                error_msg = settings.AI_BOT_PREFIX + " 未在配置中设置 OPENAI_API_KEY"
                logger.error(error_msg)
                self.lark_client.send_msg(error_msg, chat_id)
                return
            
            async with Client(self.mcp_transport) as mcp_client:
                tools = []
                for tool in await mcp_client.list_tools():
                    tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description":  tool.description,
                            "parameters": tool.inputSchema,
                        }
                    })
                messages = [
                    self.system_message,
                    {"role": "user", "content": query}
                ]
                resp = self.llm_service.chat_completion(messages, tools)
                msg = resp.choices[0].message
                if msg.tool_calls:
                    call = msg.tool_calls[0]
                    fn_name = call.function.name
                    args = json.loads(call.function.arguments)
                    output = await mcp_client.call_tool(fn_name, args)
                    logger.info(f"调用函数 {fn_name} -> {output}")
                    messages.append(msg)
                    messages.append({
                        "role": "tool",
                        "content": output,
                        "tool_call_id": call.id
                    })
                    summary = self.llm_service.chat_completion(messages)
                    response = summary.choices[0].message.content
                else:
                    response = msg.content
                response = f'{settings.AI_BOT_PREFIX} {response}'
                self.lark_client.send_msg(response, chat_id)
        except Exception as e:
            logger.error(f"处理flag函数调用时出错: {str(e)}")
            error_msg = f"{settings.AI_BOT_PREFIX} 处理请求时出错: {str(e)}"
            try:
                self.lark_client.send_msg(error_msg, chat_id)
            except Exception as send_err:
                logger.error(f"发送错误消息失败: {str(send_err)}")
    
    def close(self):
        """Close database session"""
        close_db_session(self.db) 