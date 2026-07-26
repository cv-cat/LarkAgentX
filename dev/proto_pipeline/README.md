# Proto 再生成管线(维护者用)

飞书更新协议后，按以下流程重新提取全量 proto schema 和接口映射。

## 前提

先拿到 4 个基础 worklet bundle（版本会更新，文件名带 hash，需从页面 SharedWorker 创建记录里取最新 URL):

```
1242.*.js  (js runtime service)
1181.*.js  (shared worklet,长连接)
9174.*.js  (messenger worklet)
9373.*.js  (feed worklet)
```

来源：`https://sf1-scmcdn-cn.feishucdn.com/obj/feishu-static/ee/web-client-next/p/static/js/<文件名>`，
下载后放入 `work/`（或设 `LARK_WORK_DIR` 指向存放目录）。

抓取最新文件名的方法：chrome-devtools 打开 `open-dev.feishu.cn/next/messenger`,
initScript Hook `SharedWorker` 构造器，记录传入的 blob loader 里的 `importScripts` URL。

## 执行

```bash
cd dev/proto_pipeline
python extract_chunkmap.py    # 从基础 bundle 解 webpack chunk 映射 → work/chunk_map.json
python download_chunks.py     # 并发下载全部懒加载 chunk(300+ 个)→ work/chunks/
python extract_all.py         # 提取 schema 注册表 + cmd 映射 → work/schemas_all.json, work/cmd_map.json
python gen_protos.py          # 生成 proto 文件(默认输出到 out/proto,含合并版 lark_all.proto)
python gen_cmd_table.py       # 生成接口映射表(默认 out/cmd_table.md)
```

输出目录可用环境变量覆盖：`LARK_WORK_DIR`(输入/中间产物）、`LARK_PROTO_OUT`(proto/表输出）。

## 产物用途

- `out/proto/lark_all.proto` → 用 grpcio-tools 1.71.x 编译为 `larkx/proto/lark_all_pb2.py`
- `work/cmd_map.json` → 按 `lark api` 的格式整理为 `larkx/proto/cmd_map.json`
- `out/cmd_table.md` → 接口速查表（参考）
