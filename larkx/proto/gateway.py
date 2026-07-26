import json
from pathlib import Path
from google.protobuf import json_format
from protobuf_to_dict import protobuf_to_dict
from . import proto_pb2 as P
_CMD_MAP = None
_LARK_ALL = None


def _cmd_map():
    global _CMD_MAP
    if _CMD_MAP is None:
        _CMD_MAP = json.loads((Path(__file__).parent / 'cmd_map.json').read_text(encoding='utf-8'))
    return _CMD_MAP


def _lark_all():
    global _LARK_ALL
    if _LARK_ALL is None:
        from . import lark_all_pb2
        _LARK_ALL = lark_all_pb2
    return _LARK_ALL


def resolve_type(type_name: str):
    L = _lark_all()
    parts = type_name.split('.')
    obj = L
    for p in parts:
        obj = getattr(obj, p, None)
        if obj is None:
            raise ValueError(f'未知类型: {type_name}')
    return obj


def resolve_cmd(type_or_cmd):
    if isinstance(type_or_cmd, int) or (isinstance(type_or_cmd, str) and type_or_cmd.isdigit()):
        cmd = int(type_or_cmd)
        resp_cls = None
        for r in _cmd_map()['by_cmd'].get(str(cmd), []):
            if r.get('resp'):
                try:
                    resp_cls = resolve_type(r['resp'])
                    break
                except ValueError:
                    continue
        return (cmd, None, resp_cls)
    entry = _cmd_map()['by_req'].get(type_or_cmd)
    if not entry:
        raise ValueError(f'cmd 映射里没有 {type_or_cmd}(查 docs/cmd_table.md 确认名字)')
    req_cls = resolve_type(type_or_cmd) if not entry.get('push') else None
    resp_cls = resolve_type(entry['resp']) if entry.get('resp') else None
    return (entry['cmd'], req_cls, resp_cls)


def build_packet(cmd: int, request_id: str, req_msg=None, req_bytes: bytes=None) -> P.Packet:
    pkt = P.Packet()
    pkt.payloadType = 1
    pkt.cmd = cmd
    pkt.cid = request_id
    if req_msg is not None:
        pkt.payload = req_msg.SerializeToString()
    elif req_bytes is not None:
        pkt.payload = req_bytes
    return pkt


def request_from_dict(req_cls, data: dict):
    msg = req_cls()
    if data:
        json_format.ParseDict(data, msg, ignore_unknown_fields=True)
    return msg


def response_to_dict(resp_cls, payload: bytes):
    msg = resp_cls()
    msg.ParseFromString(payload)
    return protobuf_to_dict(msg)
