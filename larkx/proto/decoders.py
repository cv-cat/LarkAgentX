import gzip
import json
import zlib

from protobuf_to_dict import protobuf_to_dict
from . import proto_pb2 as P
MSG_TYPE_NAMES = {
    0: 'UNKNOWN', 2: 'POST', 3: 'FILE', 4: 'TEXT', 5: 'IMAGE', 6: 'SYSTEM',
    7: 'AUDIO', 8: 'EMAIL', 9: 'SHARE_GROUP_CHAT', 10: 'STICKER',
    11: 'MERGE_FORWARD', 12: 'CALENDAR', 13: 'CLOUD_FILE', 14: 'CARD',
    15: 'MEDIA', 16: 'SHARE_CALENDAR_EVENT', 17: 'HONGBAO',
    18: 'GENERAL_CALENDAR', 19: 'VIDEO_CHAT', 20: 'LOCATION',
    22: 'COMMERCIALIZED_HONGBAO', 23: 'SHARE_USER_CARD', 24: 'TODO', 25: 'FOLDER',
}
CHAT_TYPE_NAMES = {0: 'UNKNOWN', 1: 'P2P', 2: 'GROUP', 3: 'TOPIC_GROUP'}
# Chat.ChatMode 的 THREAD / THREAD_V2;新建的话题群是 GROUP + 这两种模式,旧版话题群才是 TOPIC_GROUP
THREAD_CHAT_MODES = (2, 3)


def enum_to_int(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        names = P.entities.Message.Type.keys()
        if value in names:
            return P.entities.Message.Type.Value(value)
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def is_thread_chat(chat_info: dict) -> bool:
    """话题群里每条根消息自成一个话题。chat_info 为 chats.PullChatsByIdsRequest 返回的单个会话。"""
    return enum_to_int(chat_info.get('chatMode', 0)) in THREAD_CHAT_MODES or enum_to_int(chat_info.get('type', 0)) == 3


def is_self_chat(chat_info: dict) -> bool:
    """和自己的会话: 私聊类型且成员只有一个人。proto 里没有专门的标记字段。"""
    if enum_to_int(chat_info.get('type', 0)) != 1:
        return False
    return chat_info.get('userCount') == 1 or chat_info.get('memberCount') == 1


def resolve_scope(msg_id: str, msg_type: int, chat_type: int, root_id: str, thread_id: str, thread_chat: bool=False) -> tuple:
    """返回 (scope, anchor):anchor 是回复时的 --root,也是 agent 的会话边界。"""
    if chat_type == 1:
        return ('chat', '')
    if root_id and root_id != '0':
        return ('topic', thread_id or root_id)
    # 话题群的根消息本身就开启一个话题(建群等系统提示除外);普通群每条消息也带 threadId=自身 id,不能据此判断
    if (thread_chat or chat_type == 3) and msg_type != 6:
        return ('topic', msg_id or '')
    return ('chat', '')


def _lark_all():
    from . import gateway
    return gateway._lark_all()


def extract_rich_text(rich_text_dict):
    """把 richText 元素树展开成纯文本摘要。

    富文本有两种布局: 老的扁平式(叶子直接挂在 elementIds 下)和树形(DOCS(22) 下挂段落 P、列表 UL/OL/LI、
    引用、代码块等块级元素,文字在叶子里),都按 childIds 递归。块级元素之间补换行,列表项补「- 」或「n. 」,
    代码块取代码内容,链接取地址(自定义文字的链接写成「文字(地址)」)。解码失败的元素用占位符。
    """
    TAG_PLACEHOLDERS = {2: '[图片]', 10: '[表情]', 18: '[视频]', 22: '[文档]'}
    TEXT_TAGS = (1, 7, 8, 9, 17, 23, 24, 25, 44, 45, 46)
    BLOCK_TAGS = (3, 26, 27, 28, 29, 31, 37, 23, 24, 25, 44, 45, 46)
    AT, LINK, OL, LI, CODE, CODE_V2, PARA = 5, 6, 27, 28, 31, 37, 3
    text = ''
    try:
        E = _lark_all().entities.RichTextElement
        dictionary = rich_text_dict['elements']['dictionary']

        def leaf(tag, prop):
            nonlocal text
            if not prop:
                return
            try:
                if tag in TEXT_TAGS or tag == PARA:
                    text += P.TextProperty.FromString(prop).content
                elif tag == AT:
                    text += P.AtProperty.FromString(prop).content or '[@]'
                elif tag == LINK:
                    # 现在的链接属性是 AnchorProperty;老消息是 LinkProperty(url)。只有自定义文字的链接才输出文字
                    ap = E.AnchorProperty.FromString(prop)
                    href = ap.href or E.LinkProperty.FromString(prop).url
                    if href and (ap.isCustom or ap.scene) and ap.content and ap.content != href:
                        text += f'{ap.content}({href})'
                    else:
                        text += href
                elif tag == CODE:
                    text += E.CodeBlockProperty.FromString(prop).content
                elif tag == CODE_V2:
                    for line in E.CodeBlockV2Property.FromString(prop).contents:
                        text += ''.join(c.content for c in line.contents) + '\n'
                else:
                    text += TAG_PLACEHOLDERS.get(tag, '')
            except Exception:
                text += TAG_PLACEHOLDERS.get(tag, '')

        seen = set()

        def walk(key, ordered=False, index=0):
            nonlocal text
            if key in seen or not isinstance(dictionary.get(key), dict):
                return
            seen.add(key)
            v = dictionary[key]
            tag = enum_to_int(v.get('tag', 1))
            children = v.get('childIds') or []
            if tag == LI:
                text += f'{index + 1}. ' if ordered else '- '
            if children:
                if tag in BLOCK_TAGS and tag != LI and text and not text.endswith('\n'):
                    text += '\n'
                for i, child in enumerate(children):
                    walk(child, ordered=(tag == OL), index=i)
                if tag in BLOCK_TAGS and not text.endswith('\n'):
                    text += '\n'
            else:
                leaf(tag, v.get('property'))
                if tag == PARA and not text.endswith('\n'):
                    text += '\n'

        roots = [k for k in rich_text_dict.get('elementIds') or [] if k in dictionary]
        # 扁平布局或没挂到树上的元素:按 id 顺序补在后面
        listed = set(roots)
        roots += [k for k in sorted(dictionary, key=lambda x: int(x) if str(x).isdigit() else 0) if k not in listed]
        for root in roots:
            walk(root)
    except Exception:
        pass
    return text.strip()


def decode_message_content(message_type, content_bytes):
    try:
        if message_type == 4:
            tc = P.TextContent()
            tc.ParseFromString(content_bytes)
            d = protobuf_to_dict(tc)
            text = extract_rich_text(d.get('richText', {})) or d.get('text', '')
            return (text, d)
        if message_type == 2:
            pc = P.PostContent()
            pc.ParseFromString(content_bytes)
            d = protobuf_to_dict(pc)
            title = d.get('title', '')
            text = extract_rich_text(d.get('richText', {})) or d.get('text', '')
            return (f'[富文本] {title}\n{text}'.strip(), d)
        if message_type == 5:
            ic = P.ImageContent()
            ic.ParseFromString(content_bytes)
            d = protobuf_to_dict(ic)
            v2 = d.get('imageV2') or {}
            if v2:
                key = v2.get('imageKey', '')
                width = height = '?'
                for variant in v2.get('variants', []):
                    if variant.get('type') == 1:
                        size = variant.get('size') or {}
                        width, height = (size.get('width', '?'), size.get('height', '?'))
                        break
                has_crypto = 'crypto' in v2
                return (f"[图片] imageKey={key} ({width}x{height}){(' 已加密' if has_crypto else '')}", d)
            img = (d.get('image') or {}).get('origin') or {}
            key = img.get('key') or (d.get('image') or {}).get('key') or (d.get('image') or {}).get('imageKey', '')
            return (f"[图片] imageKey={key} ({img.get('width', '?')}x{img.get('height', '?')})", d)
        if message_type == 3:
            fc = P.FileContent()
            fc.ParseFromString(content_bytes)
            d = protobuf_to_dict(fc)
            return (f"[文件] {d.get('name', '')} ({d.get('mime', '')}, {d.get('size', 0)}字节, key={d.get('key', '')})", d)
        if message_type == 15:
            mc = P.MediaContent()
            mc.ParseFromString(content_bytes)
            d = protobuf_to_dict(mc)
            return (f"[视频] {d.get('name', '')} (时长{d.get('duration', 0) / 1000:.1f}s, {d.get('size', 0)}字节, key={d.get('key', '')})", d)
        if message_type == 7:
            ac = P.AudioContent()
            ac.ParseFromString(content_bytes)
            d = protobuf_to_dict(ac)
            return (f"[语音] 时长{d.get('duration', 0) / 1000:.1f}s, key={d.get('key', '')}", d)
        if message_type == 10:
            sc = P.StickerContent()
            sc.ParseFromString(content_bytes)
            d = protobuf_to_dict(sc)
            return (f"[表情包] stickerId={d.get('stickerId', '')} key={d.get('key', '')}", d)
        if message_type == 14:
            cc = P.CardContent()
            cc.ParseFromString(content_bytes)
            d = protobuf_to_dict(cc)
            header = d.get('cardHeader') or {}
            title = header.get('title') or header.get('mainTitle') or ''
            json_card = d.get('jsonCard', '')
            parts = ['[卡片]']
            if title:
                parts.append(title)
            if d.get('cardDesc'):
                parts.append(f"({d['cardDesc']})")
            if json_card:
                parts.append(json_card[:2000])
            elif d.get('openCardContent'):
                parts.append(f"<openCardContent {len(d['openCardContent'])}字节>")
            return (' '.join(parts), d)
        if message_type == 11:
            mfc = P.MergeForwardContent()
            mfc.ParseFromString(content_bytes)
            d = protobuf_to_dict(mfc)
            msgs = d.get('messages', [])
            name = d.get('groupChatName') or f"{d.get('p2pCreatorName', '')}与{d.get('p2pPartnerName', '')}的会话"
            lines = [f'[合并转发] {name} 共{len(msgs)}条:']
            for m in msgs[:20]:
                sub_type = enum_to_int(m.get('type', 0))
                sub_summary, _ = decode_message_content(sub_type, m.get('content', b''))
                lines.append(f"  {m.get('fromId', '')}: {sub_summary}")
            return ('\n'.join(lines), d)
        if message_type == 20:
            lc = P.LocationContent()
            lc.ParseFromString(content_bytes)
            d = protobuf_to_dict(lc)
            desc = d.get('locationDescription') or {}
            return (f"[位置] {desc.get('name', '')} {desc.get('description', '')} ({d.get('latitude', '')},{d.get('longitude', '')})", d)
        if message_type == 6:
            sc = P.SystemContent()
            sc.ParseFromString(content_bytes)
            d = protobuf_to_dict(sc)
            texts = []
            for cv in (d.get('sysContentValues') or {}).values():
                for item in (cv or {}).get('items', []):
                    if item.get('text'):
                        texts.append(item['text'])
            return (f"[系统消息] type={d.get('typeNum') or d.get('type', '')} {' '.join(texts)}", d)
        if message_type == 23:
            sc = P.ShareUserCardContent()
            sc.ParseFromString(content_bytes)
            d = protobuf_to_dict(sc)
            return (f"[名片] {d.get('name', '')} (userId={d.get('userId', '')})", d)
        if message_type == 9:
            sc = P.ShareGroupChatContent()
            sc.ParseFromString(content_bytes)
            d = protobuf_to_dict(sc)
            chat = d.get('chat') or {}
            chat_name = chat.get('name', '')
            chat_id = d.get('chatId') or chat.get('id', '')
            return (f'[群分享] {chat_name} (chatId={chat_id})', d)
        if message_type == 16:
            sc = P.ShareCalendarEventContent()
            sc.ParseFromString(content_bytes)
            d = protobuf_to_dict(sc)
            return (f"[分享日程] 参与人数={d.get('attendeesCount', '?')}", d)
        if message_type == 17:
            hc = P.HongbaoContent()
            hc.ParseFromString(content_bytes)
            d = protobuf_to_dict(hc)
            return (f"[红包] {d.get('subject', '')}", d)
        if message_type == 12:
            cc = P.CalendarContent()
            cc.ParseFromString(content_bytes)
            d = protobuf_to_dict(cc)
            return (f"[日历] {d.get('calendar', '')}", d)
        if message_type == 19:
            vc = P.VideoChatContent()
            vc.ParseFromString(content_bytes)
            d = protobuf_to_dict(vc)
            topic = (d.get('meetingCard') or {}).get('topic', '')
            return (f'[视频会议] {topic}', d)
        if message_type == 8:
            ec = P.EmailContent()
            ec.ParseFromString(content_bytes)
            d = protobuf_to_dict(ec)
            return (f"[邮件] {d.get('title', '')} {d.get('text', '')}", d)
    except Exception as e:
        return (f'[{MSG_TYPE_NAMES.get(message_type, message_type)}消息解析失败: {e}]', None)
    return (f'[{MSG_TYPE_NAMES.get(message_type, message_type)}类型消息]', None)


def frame_payload(frame) -> bytes:
    """WS 帧里 Packet 的字节。连接时声明了 accept_encoding=gzip,服务端可以把推送压缩后再发,要先解压,
    否则解不出 Packet,整条推送会被当成坏帧丢掉。"""
    encoding = (frame.payloadEncoding or '').lower()
    if encoding == 'gzip' or (not encoding and frame.payload[:2] == b'\x1f\x8b'):
        return gzip.decompress(frame.payload)
    if encoding in ('deflate', 'zlib'):
        return zlib.decompress(frame.payload)
    if encoding and encoding not in ('identity', 'pb'):
        raise ValueError(f'不认识的 payloadEncoding: {encoding}')
    return frame.payload


def parse_ws_frame(raw: bytes):
    """返回 (frame, packet) 两个 dict。payloadEncoding=json 的帧不是 Packet,packet 是 {'json': 内容},不带 sid 和 cmd。"""
    frame = P.Frame()
    frame.ParseFromString(raw)
    frame_d = protobuf_to_dict(frame)
    if (frame.payloadEncoding or '').lower() == 'json':
        return (frame_d, {'json': json.loads(frame.payload)})
    packet = P.Packet()
    packet.ParseFromString(frame_payload(frame))
    packet_d = protobuf_to_dict(packet)
    return (frame_d, packet_d)


def push_sids(raw: bytes) -> list:
    """PUSH_SID(cmd 6000)帧:服务端只推来 sid,完整的推送包要按 sid 再拉。返回要拉的 sid:包自己的 sid,
    加上合并在一起推来的 compactedSids(proto_pb2.Packet 没有这个字段,按 improto.Packet 解)。"""
    frame = P.Frame()
    frame.ParseFromString(raw)
    packet = _lark_all().improto.Packet.FromString(frame_payload(frame))
    return list(dict.fromkeys(s for s in (packet.sid, *map(str, packet.compactedSids)) if s))


def decode_push_messages(raw: bytes):
    _, packet = parse_ws_frame(raw)
    return push_messages(packet.get('payload') or b'')


def push_messages(payload: bytes):
    """新消息推送(PushMessagesRequest)里的消息。"""
    if not payload:
        return []
    pmr_d = protobuf_to_dict(P.PushMessagesRequest.FromString(payload))
    at_me_map = pmr_d.get('messagesAtMe') or {}
    return [message_dict(v, at_me=bool(at_me_map.get(v.get('id')) or at_me_map.get(k)))
            for k, v in (pmr_d.get('messages') or {}).items()]


def message_dict(v: dict, at_me: bool = False, thread_chat: bool = False, chat_id: str = '') -> dict:
    """消息实体(entities.Message 解成的 dict)转成入库、判断触发用的消息。推送、补拉、拉历史都用这一个。"""
    message_type = enum_to_int(v.get('type', 0))
    chat_type = enum_to_int(v.get('chatType', 0))
    summary, data = decode_message_content(message_type, v.get('content', b''))
    root_id = v.get('rootId') or ''
    scope, anchor = resolve_scope(v.get('id'), message_type, chat_type, root_id, v.get('threadId') or '', thread_chat)
    return {'msg_id': v.get('id'), 'msg_type': message_type, 'msg_type_name': MSG_TYPE_NAMES.get(message_type, str(message_type)),
            'from_id': v.get('fromId'), 'chat_id': v.get('chatId') or v.get('channelId') or str(chat_id), 'chat_type': chat_type,
            'chat_type_name': CHAT_TYPE_NAMES.get(chat_type, str(chat_type)), 'scope': scope, 'anchor': anchor, 'at_me': at_me,
            'root_id': root_id, 'parent_id': v.get('parentId') or '', 'cid': v.get('cid') or '', 'position': v.get('position'),
            'create_time': v.get('createTime'), 'content': summary, 'content_data': data}


def batch_copy_messages(payload: bytes) -> tuple:
    """逐条转发的推送(messages.PushBatchCopyMessages, cmd 134):返回 (这批消息的 id, 推送里直接带着的消息)。
    推送里只有 messageIds、会话卡片和最后一条消息 lastMessage,别的要按 id 再拉。"""
    p = _lark_all().messages.PushBatchCopyMessages.FromString(payload)
    ids = list(dict.fromkeys(str(i) for i in p.messageIds if i))
    last = p.lastMessage if p.HasField('lastMessage') and p.lastMessage.id else None
    if last is None or (ids and last.id not in ids):
        return ids, []
    return ids or [last.id], [message_dict(protobuf_to_dict(last))]
