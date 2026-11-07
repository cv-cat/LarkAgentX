"""把标题用到的字从 Noto Serif SC(OFL)里抠出来,合成一个很小的 woff2。

首页的衬线标题是唯一需要它的地方,整包字体几十 MB,不值得进 Python 包。
改了标题文字就重跑,缺字时浏览器会退回系统衬线,不会出错:

    mkdir tmp && cd tmp && npm pack @fontsource-variable/noto-serif-sc && tar xf *.tgz
    python -m venv venv && venv/Scripts/pip install fonttools brotli
    venv/Scripts/python ../scripts/subset_serif.py package ../src/assets/NotoSerifSC-subset.woff2
"""
import glob
import os
import re
import sys

from fontTools.merge import Merger
from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

# 所有用衬线的文字。保持和页面一致。
TEXT = (
    '直连本地 Coding Agent'
    '一个控制台 管理所有账号'
    '从收到消息 到发出回复'
    '本地运行 三行命令启动'
    '扫码登录 开始使用'
    '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz .,:;!?-'
    '，。：；！？、'      # 中文标点
)


def ranges(css_path):
    """fontsource 的 css 里 unicode-range -> woff2 文件名。"""
    css = open(css_path, encoding='utf-8').read()
    out = []
    for block in re.findall(r'@font-face\s*{(.*?)}', css, flags=re.S):
        m = re.search(r'unicode-range:\s*([^;]+);', block)
        f = re.search(r'files/([^)\'"]+\.woff2)', block)
        if not m or not f:
            continue
        spans = []
        for part in m.group(1).split(','):
            part = part.strip().replace('U+', '')
            lo, _, hi = part.partition('-')
            spans.append((int(lo, 16), int(hi or lo, 16)))
        out.append((f.group(1), spans))
    return out


def main(pkg, out_path):
    table = ranges(os.path.join(pkg, 'index.css'))
    chars = sorted(set(TEXT))
    per_file = {}
    for ch in chars:
        cp = ord(ch)
        for name, spans in table:
            if any(lo <= cp <= hi for lo, hi in spans):
                per_file.setdefault(name, []).append(ch)
                break
        else:
            print('未找到', repr(ch))
    print('涉及切片', len(per_file))
    tmp = []
    for i, (name, cs) in enumerate(per_file.items()):
        font = TTFont(os.path.join(pkg, 'files', name))
        font = instancer.instantiateVariableFont(font, {'wght': 600}, inplace=False) if 'fvar' in font else font
        opt = Options()
        opt.layout_features = []
        opt.name_IDs = ['*']
        opt.notdef_outline = True
        opt.hinting = False
        sub = Subsetter(opt)
        sub.populate(text=''.join(cs))
        sub.subset(font)
        for t in ('GSUB', 'GPOS', 'GDEF', 'STAT', 'avar', 'HVAR', 'MVAR'):
            if t in font:
                del font[t]
        p = f'_slice_{i}.ttf'
        font.flavor = None
        font.save(p)
        tmp.append(p)
    merged = Merger().merge(tmp)
    merged.flavor = 'woff2'
    merged.save(out_path)
    for p in tmp:
        os.remove(p)
    print('输出', out_path, os.path.getsize(out_path), '字节,', len(chars), '个字符')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
