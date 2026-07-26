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


def extract_rich_text(rich_text_dict):
    TAG_PLACEHOLDERS = {2: '[图片]', 5: '[@]', 10: '[表情]', 18: '[视频]', 22: '[文档]'}
    text = ''
    try:
        dictionary = rich_text_dict['elements']['dictionary']
        element_ids = rich_text_dict.get('elementIds') or []
        if element_ids:
            ordered = [(k, dictionary[k]) for k in element_ids if k in dictionary]
            ordered += [(k, v) for k, v in dictionary.items() if k not in set(element_ids)]
        else:
            try:
                ordered = sorted(dictionary.items(), key=lambda item: int(item[0]))
            except Exception:
                ordered = list(dictionary.items())
        for k, v in ordered:
            tag = v.get('tag', 1)
            prop = v.get('property')
            if not prop:
                continue
            if tag in (1, 3, 7, 8, 9, 17):
                tp = P.TextProperty()
                try:
                    tp.ParseFromString(prop)
                    text += tp.content
                    if tag == 3:
                        text += '\n'
                    continue
                except Exception:
                    pass
            text += TAG_PLACEHOLDERS.get(tag, '')
    except Exception:
        pass
    return text


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
            return (f"[视频] {d.get('name', '')} (时长{d.get('duration', 0)}s, {d.get('size', 0)}字节, key={d.get('key', '')})", d)
        if message_type == 7:
            ac = P.AudioContent()
            ac.ParseFromString(content_bytes)
            d = protobuf_to_dict(ac)
            return (f"[语音] 时长{d.get('duration', 0)}s, key={d.get('key', '')}", d)
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


def parse_ws_frame(raw: bytes):
    frame = P.Frame()
    frame.ParseFromString(raw)
    frame_d = protobuf_to_dict(frame)
    packet = P.Packet()
    packet.ParseFromString(frame.payload)
    packet_d = protobuf_to_dict(packet)
    return (frame_d, packet_d)


def decode_push_messages(raw: bytes):
    _, packet = parse_ws_frame(raw)
    out = []
    if 'payload' not in packet:
        return out
    pmr = P.PushMessagesRequest()
    pmr.ParseFromString(packet['payload'])
    pmr_d = protobuf_to_dict(pmr)
    at_me_map = pmr_d.get('messagesAtMe') or {}
    for k, v in (pmr_d.get('messages') or {}).items():
        message_type = enum_to_int(v.get('type', 0))
        chat_type = enum_to_int(v.get('chatType', 0))
        summary, data = decode_message_content(message_type, v.get('content', b''))
        thread_id = v.get('threadId') or ''
        root_id = v.get('rootId') or ''
        if chat_type == 1:
            scope, anchor = ('chat', '')
        elif root_id and root_id != '0':
            scope, anchor = ('topic', thread_id or root_id)
        elif chat_type == 3:
            scope, anchor = ('chat', v.get('id') or '')
        else:
            scope, anchor = ('chat', '')
        out.append({'msg_id': v.get('id'), 'msg_type': message_type, 'msg_type_name': MSG_TYPE_NAMES.get(message_type, str(message_type)), 'from_id': v.get('fromId'), 'chat_id': v.get('chatId') or v.get('channelId'), 'chat_type': chat_type, 'chat_type_name': CHAT_TYPE_NAMES.get(chat_type, str(chat_type)), 'scope': scope, 'anchor': anchor, 'at_me': bool(at_me_map.get(v.get('id')) or at_me_map.get(k)), 'root_id': root_id, 'parent_id': v.get('parentId') or '', 'cid': v.get('cid') or '', 'position': v.get('position'), 'create_time': v.get('createTime'), 'content': summary, 'content_data': data})
    return out
