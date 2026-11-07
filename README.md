<a href="https://larkagentx.cvcat.site">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="static/resource/hero-zh-dark.webp">
    <img src="static/resource/hero-zh-light.webp" alt="LarkAgentX：你的飞书账号，直连本地 Coding Agent。启动：lark web" width="100%">
  </picture>
</a>

<div align="center">

[![Python](https://img.shields.io/badge/python-3.9%2B-232838?style=flat-square&logo=python&logoColor=white)](pyproject.toml)
[![GitHub stars](https://img.shields.io/github/stars/cv-cat/LarkAgentX?style=flat-square&logo=github&color=232838)](https://github.com/cv-cat/LarkAgentX/stargazers)
[![Feishu | Lark](https://img.shields.io/badge/Feishu%20%7C%20Lark-232838?style=flat-square)](#快速上手)
[![Claude Code | Codex](https://img.shields.io/badge/Claude%20Code%20%7C%20Codex-232838?style=flat-square)](#为什么用-larkagentx)

[主页](https://larkagentx.cvcat.site) · **简体中文** · [English](README_EN.md)

</div>

LarkAgentX 让你的飞书账号直连本地的 coding agent。扫码登录后，收到的消息交给本机的 Claude Code 或 Codex 处理，回复以你的账号发出。无需配置飞书机器人，飞书和 Lark 都支持。

<div align="center">

<a href="https://api.openai-next.com">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="static/resource/sponsors/vectrust-dark.png">
    <img src="static/resource/sponsors/vectrust.png" alt="Vectrust" height="56">
  </picture>
</a>

<sub>赞助：[Vectrust](https://api.openai-next.com) @ OpenDev Org & NextRouter Alliance · [想出现在这里？](mailto:992822653@qq.com)</sub>

</div>

## 快速上手

```bash
git clone https://github.com/cv-cat/LarkAgentX.git && cd LarkAgentX
pip install -e .
lark web            # 打开 http://127.0.0.1:8765 ，扫码添加账号
```

本机需要装好 Claude Code 或 Codex。扫码用飞书 App 里的「扫一扫」。

## 控制台

<p>
  <img src="static/resource/webui-overview.png" width="49%" alt="账号概览">
  <img src="static/resource/webui-chats.png" width="49%" alt="聊天记录">
</p>

账号、聊天记录、回复方式、agent 和触发规则都在这里管理，保存后立即生效。[在线体验](https://larkagentx.cvcat.site/console)

## 为什么用 LarkAgentX

<img src="static/resource/mascot/laptop.webp" alt="吉祥物盘腿坐着敲电脑" width="150" align="right">

- **不用建机器人。** 直接用你自己的飞书账号收发消息。
- **接本地的 agent。** Claude Code 或 Codex 都行，每个会话有自己的上下文。
- **多账号。** 飞书和 Lark 账号可以同时在线，同一个账号只会运行一处。
- **数据在本地。** 登录凭证和消息都存在 `~/.larkx/`。

<br clear="right">

## 命令行

```bash
lark auth qr                      # 扫码登录，Lark 账号加 --region lark
lark listen --agent               # 收消息并交给 agent
lark send <chat_id> <text>        # 发消息
lark history <chat_id> --save     # 拉历史消息
lark api <type> '<json>'          # 调任意网关接口
```

配置写在 `.env`，见 [`.env.example`](.env.example)。agent 以免确认模式运行，可以执行任意命令，只对信任的会话开启。

## 参与贡献

<img src="static/resource/mascot/bubble.webp" alt="吉祥物坐在聊天气泡上挥手" width="130" align="right">

欢迎提交 Issue 和 Pull Request。前端在 `webui/`，`npm run build` 输出到 `larkx/web/static/`。

<br clear="right">

## Star 趋势

<a href="https://cvcat.site/star-history/svg?repos=cv-cat/LarkAgentX&type=Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://cvcat.site/star-history/svg?repos=cv-cat/LarkAgentX&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://cvcat.site/star-history/svg?repos=cv-cat/LarkAgentX&type=Date" />
    <img alt="Star History Chart" src="https://cvcat.site/star-history/svg?repos=cv-cat/LarkAgentX&type=Date" />
  </picture>
</a>

## 🍔 交流群

如果你对爬虫和 AI Agent 感兴趣，可以加入群聊一起讨论~

ps: 请加群，人满或者过期 issue | wx 提醒 | qq提醒

| group-1 | group-2 | group-3 | group-4 (2000人qq群) |
|:--:|:--:|:--:|:--:|
| <img width="280" alt="group1" src="https://cvcat.site/assets/group1.jpg" /> | <img width="280" alt="group2" src="https://cvcat.site/assets/group2.jpg" /> | <img width="280" alt="group3" src="https://cvcat.site/assets/group3.jpg" /> | <img width="280" alt="group3" src="https://cvcat.site/assets/group4.jpg" /> |

<details>
<summary>免责声明</summary>

<br>

- 仅供学习和研究使用，不得用于商业或违法用途。
- 通过飞书网页版的内部协议工作，不是官方接口。请遵守飞书 / Lark 的服务条款和当地法律。
- 自动收发消息可能触发风控，导致账号受限或被封，后果自负。
- 与飞书、Lark 及其运营方无关，名称和商标归各自所有者。

</details>
