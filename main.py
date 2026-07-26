"""LarkAgentX — 飞书数字人。

直接运行: 连接飞书 WS 收消息,入库并接入本地 coding agent 自动回复。
等价于 `lark listen --agent`,额外参数原样透传。
首次使用先 `lark auth qr` 扫码登录。
"""
import sys

from larkx.cli import main as cli_main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "listen", "--agent", *sys.argv[1:]]
    sys.exit(cli_main())
