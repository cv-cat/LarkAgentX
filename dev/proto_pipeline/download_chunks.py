import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor

DIR = os.environ.get('LARK_WORK_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work'))
OUT = os.path.join(DIR, 'chunks')
os.makedirs(OUT, exist_ok=True)

BASE = 'https://sf1-scmcdn-cn.feishucdn.com/obj/feishu-static/ee/web-client-next/p/static/js'
chunk_map = json.load(open(os.path.join(DIR, 'chunk_map.json')))

# also keep the 4 base bundles under their chunk ids
BASE_BUNDLES = {
    '1242': '60b3a8cd', '1181': 'aa6c8a55', '9174': '30e252dd', '9373': 'e0426f59', '8929': '4a638fa1',
}
for cid, h in BASE_BUNDLES.items():
    chunk_map.setdefault(cid, h)

def fetch(item):
    cid, h = item
    name = '%s.%s.js' % (cid, h)
    path = os.path.join(OUT, name)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return name, 'skip', os.path.getsize(path)
    try:
        req = urllib.request.Request(BASE + '/' + name, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        open(path, 'wb').write(data)
        return name, 'ok', len(data)
    except Exception as e:
        return name, 'FAIL: %s' % e, 0

results = []
with ThreadPoolExecutor(max_workers=12) as ex:
    for res in ex.map(fetch, sorted(chunk_map.items(), key=lambda x: int(x[0]))):
        results.append(res)

fails = [r for r in results if r[1].startswith('FAIL')]
total = sum(r[2] for r in results)
print('done: %d files, %d failures, total %.1f MB' % (len(results), len(fails), total / 1e6))
for f in fails:
    print(' ', f[0], f[1])
