import json
import os
import re

DIR = os.environ.get('LARK_WORK_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work'))
OUT = os.environ.get('LARK_PROTO_OUT', os.path.dirname(os.path.abspath(__file__)) + '/out') + '/cmd_table.md'

cmd_map = json.load(open(os.path.join(DIR, 'cmd_map.json'), encoding='utf-8'))

rows = []
VALID = re.compile(r'^-?\d+(\|[A-Za-z0-9_.]*)+$')
for raw in cmd_map:
    if not VALID.match(raw):
        continue
    if not re.search(r'\|[A-Za-z_.]*[A-Za-z]', raw):  # must contain a proto-ish identifier
        continue
    parts = raw.split('|')
    try:
        cmd = int(parts[0])
    except ValueError:
        continue
    req = resp = name = ''
    rest = parts[1:]
    if len(rest) == 2:
        req, resp = rest
    elif len(rest) == 4:
        req, resp, _, name = rest
    elif len(rest) == 3:
        req, resp, name = rest
    else:
        resp = '|'.join(rest)
    rows.append((cmd, req, resp, name, raw))

rows.sort(key=lambda r: r[0])

lines = [
    '# 飞书网页客户端接口 (cmd) 映射表',
    '',
    '> 来源：web-client-next worklet bundles (2026-07-25, sdk 7.72.8)。',
    '> 格式 A: `cmd|请求proto|响应proto`；格式 B: `cmd||推送proto||推送名`；格式 C: `cmd|请求|响应|1|名称`。',
    '> 同名 cmd 在不同业务命名空间可能复用（推送类 cmd 与请求类 cmd 不冲突）。',
    '',
    '| cmd | 请求 | 响应/推送 | 名称 |',
    '|----:|------|-----------|------|',
]
for cmd, req, resp, name, raw in rows:
    lines.append('| %d | %s | %s | %s |' % (cmd, req, resp, name))

open(OUT, 'w', encoding='utf-8').write('\n'.join(lines))
print('written %s, %d rows' % (OUT, len(rows)))

# a few stats
push = [r for r in rows if 'Push' in r[2] or 'PUSH' in r[3]]
print('push-type cmds:', len(push))
