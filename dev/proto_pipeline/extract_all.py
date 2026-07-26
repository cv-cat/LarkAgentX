import re, os, json, glob

DIR = os.environ.get('LARK_WORK_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work'))
CHUNKS = os.path.join(DIR, 'chunks')

reg_pat = re.compile(r'register\("([a-zA-Z0-9_.]+)","([a-zA-Z0-9_.]+)",\{')
cmd_pat = re.compile(r'"(-?\d+(?:\|[A-Za-z0-9_.]*)+)"')

def extract_regs(src):
    out = []
    for m in reg_pat.finditer(src):
        ns, name = m.group(1), m.group(2)
        i = m.end() - 1
        depth = 0
        start = i
        in_str = False
        str_ch = ''
        esc = False
        while i < len(src):
            c = src[i]
            if in_str:
                if esc:
                    esc = False
                elif c == '\\':
                    esc = True
                elif c == str_ch:
                    in_str = False
            else:
                if c in '"\'':
                    in_str = True
                    str_ch = c
                elif c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        break
            i += 1
        out.append((ns, name, src[start:i+1]))
    return out

all_regs = {}
cmd_map = {}
files = sorted(glob.glob(os.path.join(CHUNKS, '*.js')))
for fp in files:
    src = open(fp, encoding='utf-8', errors='replace').read()
    for ns, name, body in extract_regs(src):
        all_regs.setdefault((ns, name), body)
    for m in cmd_pat.finditer(src):
        cmd_map.setdefault(m.group(1), os.path.basename(fp))

print('files:', len(files))
print('schemas:', len(all_regs))
print('cmd mappings:', len(cmd_map))

json.dump({'%s.%s' % k: v for k, v in sorted(all_regs.items())},
          open(os.path.join(DIR, 'schemas_all.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
json.dump(cmd_map, open(os.path.join(DIR, 'cmd_map.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)

# namespace stats
from collections import Counter
ns_count = Counter(k[0] for k in all_regs)
print('namespaces:', dict(ns_count.most_common(40)))
