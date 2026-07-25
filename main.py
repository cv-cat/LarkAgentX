"""
Lark Message Recorder - Main Entry Point
Records all received Lark messages to a MySQL database.
"""
import argparse
import multiprocessing
import sys
import asyncio
from loguru import logger


def start_mcp_server():
    """Start the MCP server in a separate process"""
    logger.info("Starting MCP server...")
    from app.core.mcp_server import mcp
    mcp.run(transport="stdio")


async def do_login(timeout=180):
    """Perform browser-based login"""
    from app.api.browser_login import browser_login
    try:
        cookie = await browser_login(timeout)
        logger.info("Login successful! You can now run the agent.")
        return cookie
    except ImportError as e:
        logger.error(str(e))
        sys.exit(1)
    except TimeoutError as e:
        logger.error(str(e))
        sys.exit(1)


async def main():
    """Main function to run the Lark message recorder"""
    parser = argparse.ArgumentParser(description="LarkAgentX - Feishu/Lark AI Agent")
    parser.add_argument("--login", action="store_true", help="Login via browser and save cookie")
    parser.add_argument("--logout", action="store_true", help="Clear saved cookie")
    parser.add_argument("--login-timeout", type=int, default=180, help="Browser login timeout in seconds")
    args = parser.parse_args()

    if args.logout:
        from app.api.browser_login import clear_saved_cookie
        clear_saved_cookie()
        logger.info("Logged out successfully")
        return

    if args.login:
        await do_login(args.login_timeout)
        return

    from app.db.session import init_db
    from app.api.auth import get_auth
    from app.api.lark_client import LarkClient
    from app.core.message_service import MessageService
    mcp_process = multiprocessing.Process(target=start_mcp_server)
    mcp_process.daemon = True
    mcp_process.start()

    logger.info("初始化数据库...")
    try:
        init_db()
        logger.info("数据库初始化成功.")
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}")
        sys.exit(1)

    logger.info("初始化认证...")
    try:
        auth = get_auth()
        if not auth.is_authenticated():
            logger.warning("未找到认证信息，请先运行: python main.py --login")
            logger.info("或设置环境变量 LARK_COOKIE")
            sys.exit(1)
        logger.info("认证初始化成功.")
    except Exception as e:
        logger.error(f"认证初始化失败: {str(e)}")
        sys.exit(1)

    logger.info("创建 Lark 客户端...")
    try:
        lark_client = LarkClient(auth)
        logger.info("Lark 客户端创建成功.")
    except Exception as e:
        logger.error(f"Lark 客户端创建失败: {str(e)}")
        sys.exit(1)

    logger.info("创建消息服务...")
    message_service = MessageService(lark_client)

    try:
        logger.info("连接到 Lark WebSocket...")
        logger.info("开始接收消息...")
        logger.info('================================================================')
        await lark_client.connect_websocket(message_service.process_message)
    except KeyboardInterrupt:
        logger.info("程序被用户中断.")
    except Exception as e:
        logger.error(f"Error: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
