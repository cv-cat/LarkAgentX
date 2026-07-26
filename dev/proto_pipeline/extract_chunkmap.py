import re, json, os

DIR = os.environ.get('LARK_WORK_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work'))

chunk_map = {}
for fn in ['1242.60b3a8cd.js', '1181.aa6c8a55.js', '9174.30e252dd.js', '9373.e0426f59.js']:
    src = open(os.path.join(DIR, fn), encoding='utf-8', errors='replace').read()
    for m in re.finditer(r'\.u=\w+=>"static/js/"\+\w+\+"\."\+\{([^{}]+)\}\[\w+\]\+"\.js"', src):
        body = m.group(1)
        for kv in re.finditer(r'(\d+):"([0-9a-f]+)"', body):
            chunk_map[int(kv.group(1))] = kv.group(2)

print('chunks found:', len(chunk_map))
out = dict(sorted(chunk_map.items()))
json.dump(out, open(os.path.join(DIR, 'chunk_map.json'), 'w'), indent=0)
print(json.dumps(out))
