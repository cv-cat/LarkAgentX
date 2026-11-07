"""生成 README 顶部的标题图: static/resource/hero-{zh,en}-{light,dark}.webp。

文字用控制台主页同一套字体(Geist / 衬线标题子集),吉祥物是 static/resource/mascot/hero.png
(来源见同目录 mascot.md)。用本机的 Chrome 或 Edge 无头模式把 HTML 截成透明底的图,所以图里的字在任何系统上看起来都一样。

    python dev/readme_assets/render_hero.py            # 自动找 Chrome / Edge
    BROWSER=/path/to/chrome python dev/readme_assets/render_hero.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'static' / 'resource'
FONTS = ROOT / 'webui' / 'node_modules' / '@fontsource-variable'
SERIF = ROOT / 'webui' / 'src' / 'assets' / 'NotoSerifSC-subset.woff2'
MASCOT = OUT / 'mascot' / 'hero.png'
W, H, SCALE = 1280, 560, 2

TEXT = {
    'zh': {'title': '你的飞书账号，', 'title2': '直连本地 Coding Agent。',
           'sub': '无需配置飞书机器人，消息交给本机的 Claude Code 或 Codex 处理。', 'cmd': 'lark web'},
    'en': {'title': 'Your Feishu account,', 'title2': 'wired to your local coding agent.',
           'sub': 'No bot to set up. Claude Code or Codex handles your messages.', 'cmd': 'lark web'},
}
THEMES = {
    'light': {'ink': '#1F2329', 'serif': '#8F959E', 'sub': '#646A73'},
    'dark': {'ink': '#F1F3F9', 'serif': '#9AA3B5', 'sub': '#9AA3B5'},
}
PILL = {'bg': '#1B2033', 'line': '#30384F', 'text': '#F2F4FA', 'dim': '#7D859C'}


def html(lang: str, theme: str) -> str:
    t, c = TEXT[lang], THEMES[theme]
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Geist; src: url("{(FONTS / 'geist/files/geist-latin-wght-normal.woff2').as_uri()}"); font-weight: 100 900; }}
@font-face {{ font-family: GeistMono; src: url("{(FONTS / 'geist-mono/files/geist-mono-latin-wght-normal.woff2').as_uri()}"); font-weight: 100 900; }}
@font-face {{ font-family: LarkXSerif; src: url("{SERIF.as_uri()}"); font-weight: 600; }}
html, body {{ margin: 0; width: {W}px; height: {H}px; background: transparent; overflow: hidden; }}
body {{ font-family: Geist, "PingFang SC", "Microsoft YaHei", sans-serif; color: {c['ink']}; -webkit-font-smoothing: antialiased; }}
.text {{ position: absolute; left: 40px; top: 50%; transform: translateY(-50%); width: 760px; }}
.name {{ font-size: 92px; font-weight: 800; letter-spacing: -0.04em; line-height: 1; }}
.title {{ margin-top: 26px; font-size: 38px; font-weight: 700; line-height: 1.3; letter-spacing: -0.01em; }}
.title2 {{ font-family: LarkXSerif, Georgia, serif; font-weight: 600; color: {c['serif']}; }}
.sub {{ margin-top: 16px; font-size: 21px; color: {c['sub']}; }}
.pill {{ margin-top: 34px; display: inline-flex; align-items: center; height: 60px; padding: 0 32px; border-radius: 999px;
        background: {PILL['bg']}; border: 1px solid {PILL['line']}; color: {PILL['text']}; font: 500 25px GeistMono, monospace; }}
.pill b {{ color: {PILL['dim']}; font-weight: 500; margin-right: 16px; }}
.mascot {{ position: absolute; right: 70px; top: 50%; transform: translateY(-50%); height: 520px; }}
</style></head><body>
<div class="text">
  <div class="name">LarkAgentX</div>
  <div class="title">{t['title']}<br><span class="title2">{t['title2']}</span></div>
  <div class="sub">{t['sub']}</div>
  <div class="pill"><b>$</b>{t['cmd']}</div>
</div>
<img class="mascot" src="{MASCOT.as_uri()}">
</body></html>'''


def find_browser() -> str:
    if os.environ.get('BROWSER'):
        return os.environ['BROWSER']
    candidates = [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    ]
    for name in ('google-chrome', 'chromium', 'chromium-browser', 'msedge'):
        found = shutil.which(name)
        if found:
            candidates.insert(0, found)
    for path in candidates:
        if os.path.exists(path):
            return path
    sys.exit('没找到 Chrome / Edge,用 BROWSER=<浏览器路径> 指定')


def main():
    browser = find_browser()
    with tempfile.TemporaryDirectory() as tmp:
        for lang in TEXT:
            for theme in THEMES:
                page = Path(tmp) / f'{lang}-{theme}.html'
                page.write_text(html(lang, theme), encoding='utf-8')
                shot = Path(tmp) / f'{lang}-{theme}.png'
                subprocess.run([browser, '--headless=new', '--disable-gpu', '--hide-scrollbars', f'--user-data-dir={Path(tmp) / "profile"}',
                                '--default-background-color=00000000', f'--force-device-scale-factor={SCALE}', f'--window-size={W},{H}',
                                '--virtual-time-budget=3000', f'--screenshot={shot}', page.as_uri()],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                out = OUT / f'hero-{lang}-{theme}.webp'
                Image.open(shot).convert('RGBA').save(out, 'WEBP', quality=90, method=6)
                print(out.relative_to(ROOT), f'{out.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
