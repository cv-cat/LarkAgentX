# 吉祥物

LarkAgentX 的吉祥物是一位戴耳麦的 Q 版「消息小助理」，肩上停着一只蓝绿色的小云雀（Lark 就是云雀）。原创角色，图由图像模型生成（OpenAI `gpt-image-2.6`，透明底）。
要出新的姿势或贴纸时，沿用下面的角色描述，只换「姿势」一句，保证每张图里是同一个人。

| 文件 | 用途 | 姿势 |
| --- | --- | --- |
| `static/resource/mascot/hero.png` | README 标题图（`render_hero.py` 的素材） | 单脚跳着挥手，另一只手举着印有 `>_` 的聊天气泡 |
| `static/resource/mascot/laptop.webp` | README「工作方式」 | 盘腿坐着敲笔记本电脑，小云雀从屏幕后探出头 |
| `static/resource/mascot/bubble.webp` | README「参与贡献」 | 坐在一朵聊天气泡上晃腿挥手，小云雀叼着信封飞在旁边 |

## 角色描述

```text
an original cute girl mascot who is a young digital messenger assistant: short fluffy black bob with a small blue hair clip
shaped like a four-point sparkle, big bright blue eyes, a happy open-mouth smile, a compact white headset with a tiny microphone,
a white hoodie with a soft blue (#3370FF) hood lining and a teal (#00D6B9) zipper pull, a navy pleated skirt, white socks and
blue sneakers; a tiny round blue-and-teal skylark bird with a little white sparkle on its chest perches on her shoulder
```

## 画风

```text
Chibi anime die-cut sticker of <角色描述>, <姿势>. Thick clean white sticker border, soft cel shading, crisp line art, small golden sparkles.
Centered on a transparent background, nothing else in the frame. No text other than >_ , no watermark.
```

请求参数：`model: gpt-image-2.6`、`size: 1024x1024`、`quality: high`、`background: transparent`。提示词用英文。

## 处理

- 切掉四周的透明边，标题图素材缩到 900px 高、保留 PNG 原图；README 里直接显示的贴纸缩到 400px，存成带透明通道的 WebP（quality 90）。
- 不要转成 256 色调色板：脸颊会出色块，贴纸白边外会多一圈灰边。
- 改了吉祥物或标题文案后，运行 `python dev/readme_assets/render_hero.py` 重新生成四张标题图。
