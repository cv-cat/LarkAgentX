import json

import static.proto_pb2 as FLY_BOOK_PROTO
from protobuf_to_dict import protobuf_to_dict
from app.utils.lark_utils import generate_request_cid

class ProtoBuilder:
    @staticmethod
    def build_send_message_request_proto(sends_text, request_id, chatId):
        cid_1 = generate_request_cid()
        cid_2 = generate_request_cid()

        Packet = FLY_BOOK_PROTO.Packet()
        Packet.payloadType = 1
        Packet.cmd = 5
        Packet.cid = request_id

        PutMessageRequest = FLY_BOOK_PROTO.PutMessageRequest()
        PutMessageRequest.type = 4
        PutMessageRequest.chatId = chatId
        PutMessageRequest.cid = cid_1
        PutMessageRequest.isNotified = 1
        PutMessageRequest.version = 1

        PutMessageRequest.content.richText.elementIds.append(cid_2)
        PutMessageRequest.content.richText.innerText = sends_text
        PutMessageRequest.content.richText.elements.dictionary[cid_2].tag = 1

        TextProperty = FLY_BOOK_PROTO.TextProperty()
        TextProperty.content = str(sends_text)
        PutMessageRequest.content.richText.elements.dictionary[cid_2].property = TextProperty.SerializeToString()

        Packet.payload = PutMessageRequest.SerializeToString()
        return Packet

    @staticmethod
    def build_search_request_proto(request_id, query):
        request_cid = generate_request_cid()
        Packet = FLY_BOOK_PROTO.Packet()
        Packet.payloadType = 1
        Packet.cmd = 11021
        Packet.cid = request_id

        UniversalSearchRequest = FLY_BOOK_PROTO.UniversalSearchRequest()
        UniversalSearchRequest.header.searchSession = request_cid
        UniversalSearchRequest.header.sessionSeqId = 1
        UniversalSearchRequest.header.query = query
        UniversalSearchRequest.header.searchContext.tagName = 'SMART_SEARCH'

        EntityItem_1 = FLY_BOOK_PROTO.EntityItem()
        EntityItem_1.type = 1
        # EntityItem_1.filter.userFilter.isResigned = 1
        # EntityItem_1.filter.userFilter.haveChatter = 0
        # EntityItem_1.filter.userFilter.exclude = 1

        EntityItem_2 = FLY_BOOK_PROTO.EntityItem()
        EntityItem_2.type = 2
        EntityFilter = FLY_BOOK_PROTO.EntityItem.EntityFilter()
        EntityItem_2.filter.CopyFrom(EntityFilter)

        EntityItem_3 = FLY_BOOK_PROTO.EntityItem()
        GroupChatFilter = FLY_BOOK_PROTO.GroupChatFilter()
        EntityItem_3.type = 3
        EntityItem_3.filter.groupChatFilter.CopyFrom(GroupChatFilter)

        EntityItem_4 = FLY_BOOK_PROTO.EntityItem()
        EntityItem_4.type = 10
        EntityFilter = FLY_BOOK_PROTO.EntityItem.EntityFilter()
        EntityItem_4.filter.CopyFrom(EntityFilter)

        UniversalSearchRequest.header.searchContext.entityItems.append(EntityItem_1)
        UniversalSearchRequest.header.searchContext.entityItems.append(EntityItem_2)
        UniversalSearchRequest.header.searchContext.entityItems.append(EntityItem_3)
        UniversalSearchRequest.header.searchContext.entityItems.append(EntityItem_4)
        UniversalSearchRequest.header.searchContext.commonFilter.includeOuterTenant = 1
        UniversalSearchRequest.header.searchContext.sourceKey = 'messenger'
        UniversalSearchRequest.header.locale = 'zh_CN'
        SearchExtraParam = FLY_BOOK_PROTO.SearchExtraParam()
        UniversalSearchRequest.header.extraParam.CopyFrom(SearchExtraParam)
        Packet.payload = UniversalSearchRequest.SerializeToString()
        return Packet

    @staticmethod
    def decode_search_response_proto(message):
        userAndGroupIds = []
        Packet = FLY_BOOK_PROTO.Packet()
        Packet.ParseFromString(message)
        Packet = protobuf_to_dict(Packet)
        if 'payload' in Packet:
            payload = Packet['payload']
            UniversalSearchResponse = FLY_BOOK_PROTO.UniversalSearchResponse()
            UniversalSearchResponse.ParseFromString(payload)
            UniversalSearchResponse = protobuf_to_dict(UniversalSearchResponse)
            Packet['payload'] = UniversalSearchResponse

            for result in UniversalSearchResponse['results']:
                if result['type'] == 1:
                    userAndGroupIds.append({
                        'type': 'user',
                        'id': result['id']
                    })
                elif result['type'] == 3:
                    userAndGroupIds.append({
                        'type': 'group',
                        'id': result['id']
                    })

        return Packet, userAndGroupIds


    @staticmethod
    def build_create_chat_request_proto(request_id, chatId):
        Packet = FLY_BOOK_PROTO.Packet()
        Packet.payloadType = 1
        Packet.cmd = 13
        Packet.cid = request_id

        PutChatRequest = FLY_BOOK_PROTO.PutChatRequest()
        PutChatRequest.type = 1
        PutChatRequest.chatterIds.append(chatId)
        Packet.payload = PutChatRequest.SerializeToString()
        return Packet

    @staticmethod
    def decode_create_chat_response_proto(message):
        chatId = None
        Packet = FLY_BOOK_PROTO.Packet()
        Packet.ParseFromString(message)
        Packet = protobuf_to_dict(Packet)
        if 'payload' in Packet:
            payload = Packet['payload']
            PutChatResponse = FLY_BOOK_PROTO.PutChatResponse()
            PutChatResponse.ParseFromString(payload)
            PutChatResponse = protobuf_to_dict(PutChatResponse)
            Packet['payload'] = PutChatResponse
            chatId = PutChatResponse['chat']['id']
        return Packet, chatId

    @staticmethod
    def extra_packet_id(message):
        Frame = FLY_BOOK_PROTO.Frame()
        Frame.ParseFromString(message)
        Frame = protobuf_to_dict(Frame)
        payload = Frame['payload']
        Packet = FLY_BOOK_PROTO.Packet()
        Packet.ParseFromString(payload)
        Packet = protobuf_to_dict(Packet)
        Frame['payload'] = Packet
        packet_id = Packet['sid']
        return packet_id

    @staticmethod
    def decode_receive_msg_proto(message):
        ReceiveTextContent = {
            'fromId': None,
            'chatId': None,
            'chatType': None,
            'content': None,
            'messageId': None
        }
        Frame = FLY_BOOK_PROTO.Frame()
        Frame.ParseFromString(message)
        Frame = protobuf_to_dict(Frame)
        payload = Frame['payload']
        Packet = FLY_BOOK_PROTO.Packet()
        Packet.ParseFromString(payload)
        Packet = protobuf_to_dict(Packet)
        Frame['payload'] = Packet
        Packet_sid = Packet['sid']
        if 'payload' in Packet:
            payload = Packet['payload']
            PushMessagesRequest = FLY_BOOK_PROTO.PushMessagesRequest()
            PushMessagesRequest.ParseFromString(payload)
            PushMessagesRequest = protobuf_to_dict(PushMessagesRequest)
            Packet['payload'] = PushMessagesRequest
            if 'messages' in PushMessagesRequest:
                messages = PushMessagesRequest['messages']
                for k, v in messages.items():
                    message_type = v['type']
                    fromId = v['fromId']
                    content = v['content']
                    chatId = v['chatId']
                    chatType = v['chatType']
                    messageId = v.get('id', None)
                    ReceiveTextContent['fromId'] = fromId
                    ReceiveTextContent['chatId'] = chatId
                    ReceiveTextContent['chatType'] = chatType
                    ReceiveTextContent['messageId'] = messageId
                    if message_type == 4:
                        receive_content = ''
                        TextContent = FLY_BOOK_PROTO.TextContent()
                        TextContent.ParseFromString(content)
                        TextContent = protobuf_to_dict(TextContent)
                        v['content'] = TextContent
                        dictionary = TextContent['richText']['elements']['dictionary']
                        try:
                            dictionary = dict(sorted(dictionary.items(), key=lambda item: int(item[0])))
                        except:
                            pass
                        for k, v in dictionary.items():
                            property = v['property']
                            TextProperty = FLY_BOOK_PROTO.TextProperty()
                            TextProperty.ParseFromString(property)
                            TextProperty = protobuf_to_dict(TextProperty)
                            v['property'] = TextProperty
                            receive_content += TextProperty['content']
                        ReceiveTextContent['content'] = receive_content
        return ReceiveTextContent

    @staticmethod
    def build_get_user_all_name_request_proto(request_id, user_id, chatId):
        Packet = FLY_BOOK_PROTO.Packet()
        Packet.payloadType = 1
        Packet.cmd = 5023
        Packet.cid = request_id

        GetUserInfoRequest = FLY_BOOK_PROTO.GetUserInfoRequest()
        GetUserInfoRequest.userId = int(user_id)
        GetUserInfoRequest.chatId = int(chatId)
        GetUserInfoRequest.userType = 1

        Packet.payload = GetUserInfoRequest.SerializeToString()
        return Packet

    @staticmethod
    def decode_info_response_proto(message):
        translation = None
        Packet = FLY_BOOK_PROTO.Packet()

        Packet.ParseFromString(message)
        Packet = protobuf_to_dict(Packet)
        if 'payload' in Packet:
            payload = Packet['payload']
            UserInfo = FLY_BOOK_PROTO.UserInfo()
            UserInfo.ParseFromString(payload)
            UserInfo = protobuf_to_dict(UserInfo)
            Packet['payload'] = UserInfo
            detail = UserInfo['userInfoDetail']['detail']
            translation = detail['nickname'] if 'nickname' in detail else None
            locales = detail['locales']
            for locale in locales:
                if locale['key_string'] == 'zh_cn':
                    translation = locale['translation']
                    break
        return translation

    @staticmethod
    def decode_group_info_response_proto(message):
        nickname = None
        Packet = FLY_BOOK_PROTO.Packet()

        Packet.ParseFromString(message)
        Packet = protobuf_to_dict(Packet)
        if 'payload' in Packet:
            payload = Packet['payload']
            UserInfo = FLY_BOOK_PROTO.UserInfo()
            UserInfo.ParseFromString(payload)
            UserInfo = protobuf_to_dict(UserInfo)
            Packet['payload'] = UserInfo
            detail = UserInfo['userInfoDetail']['detail']
            nickname = detail['nickname1'] if 'nickname1' in detail else None
            if not nickname:
                nickname = detail['nickname4'] if 'nickname4' in detail else None
        if nickname:
            nickname = nickname.decode('utf-8')
        return nickname

    @staticmethod
    def build_get_group_name_request_proto(request_id, chatId):
        Packet = FLY_BOOK_PROTO.Packet()
        Packet.payloadType = 1
        Packet.cmd = 64
        Packet.cid = request_id

        GetGroupInfoRequest = FLY_BOOK_PROTO.GetGroupInfoRequest()
        GetGroupInfoRequest.chatId = str(chatId)

        Packet.payload = GetGroupInfoRequest.SerializeToString()
        return Packet

    @staticmethod
    def build_delete_message_request_proto(request_id, message_id, chat_id):
        """Build recall/delete message request (cmd=9)"""
        Packet = FLY_BOOK_PROTO.Packet()
        Packet.payloadType = 1
        Packet.cmd = 9
        Packet.cid = request_id

        req = FLY_BOOK_PROTO.DeleteMessagesRequest()
        req.messageIds.append(str(message_id))
        req.chatId = str(chat_id)

        Packet.payload = req.SerializeToString()
        return Packet

    @staticmethod
    def build_edit_message_request_proto(request_id, message_id, new_text):
        """Build edit message request (cmd=900010)"""
        cid = generate_request_cid()

        Packet = FLY_BOOK_PROTO.Packet()
        Packet.payloadType = 1
        Packet.cmd = 900010
        Packet.cid = request_id

        # Build the rich text content for edit
        root_id = "2"
        text_id = "3"

        TextProperty = FLY_BOOK_PROTO.TextProperty()
        TextProperty.content = str(new_text)
        text_property_bytes = TextProperty.SerializeToString()

        richText = FLY_BOOK_PROTO.RichText()
        richText.elementIds.append(root_id)
        richText.innerText = new_text
        richText.elements.dictionary[root_id].tag = FLY_BOOK_PROTO.RichTextElement.P
        richText.elements.dictionary[root_id].property = b''
        richText.elements.dictionary[root_id].childIds.append(text_id)
        richText.elements.dictionary[text_id].tag = FLY_BOOK_PROTO.RichTextElement.TEXT
        richText.elements.dictionary[text_id].property = text_property_bytes

        rich_text_bytes = richText.SerializeToString()

        # Build content wrapper: field 1 = richText bytes
        content_bytes = ProtoBuilder._encode_bytes_field(1, rich_text_bytes)

        # Build edit payload manually:
        # field 1 (varint) = message_id
        # field 2 (string) = cid
        # field 3 (varint) = type (4 = TEXT)
        # field 4 (bytes) = content
        payload = b''
        payload += ProtoBuilder._encode_varint_field(1, int(message_id))
        payload += ProtoBuilder._encode_string_field(2, cid)
        payload += ProtoBuilder._encode_varint_field(3, 4)  # TEXT type
        payload += ProtoBuilder._encode_bytes_field(4, content_bytes)

        Packet.payload = payload
        return Packet

    @staticmethod
    def build_reaction_request_proto(request_id, cmd, message_id, reaction_type):
        """Build add/remove reaction request (cmd=25 add, cmd=26 remove)"""
        Packet = FLY_BOOK_PROTO.Packet()
        Packet.payloadType = 1
        Packet.cmd = cmd
        Packet.cid = request_id

        # Reaction payload: field1=messageId, field2=reactionType, field3=source(1)
        payload = b''
        payload += ProtoBuilder._encode_string_field(1, str(message_id))
        payload += ProtoBuilder._encode_string_field(2, str(reaction_type))
        payload += ProtoBuilder._encode_varint_field(3, 1)

        Packet.payload = payload
        return Packet

    @staticmethod
    def build_pin_request_proto(request_id, chat_id, message_id):
        """Build pin message request (cmd=5100)"""
        Packet = FLY_BOOK_PROTO.Packet()
        Packet.payloadType = 1
        Packet.cmd = 5100
        Packet.cid = request_id

        # Pin payload: field1=chatId(varint), field2=messageId(varint)
        payload = b''
        payload += ProtoBuilder._encode_varint_field(1, int(chat_id))
        payload += ProtoBuilder._encode_varint_field(2, int(message_id))

        Packet.payload = payload
        return Packet

    @staticmethod
    def build_unpin_request_proto(request_id, chat_id, pin_id):
        """Build unpin message request (cmd=5103)"""
        Packet = FLY_BOOK_PROTO.Packet()
        Packet.payloadType = 1
        Packet.cmd = 5103
        Packet.cid = request_id

        # Unpin payload: field1=pinId(varint), field2=chatId(varint)
        payload = b''
        payload += ProtoBuilder._encode_varint_field(1, int(pin_id))
        payload += ProtoBuilder._encode_varint_field(2, int(chat_id))

        Packet.payload = payload
        return Packet

    @staticmethod
    def decode_pin_response_proto(message):
        """Decode pin response to extract pin ID"""
        Packet = FLY_BOOK_PROTO.Packet()
        Packet.ParseFromString(message)
        payload = Packet.payload
        if payload:
            # Parse CreatePinResponse: field 1 = PinEntity (bytes)
            # PinEntity: field 1 = id (varint)
            pin_entity, _ = ProtoBuilder._decode_bytes_field(payload, 1)
            if pin_entity:
                pin_id, _ = ProtoBuilder._decode_varint_field(pin_entity, 1)
                return pin_id
        return None

    @staticmethod
    def build_mark_read_request_proto(request_id, chat_id, message_id):
        """Build mark-read request (cmd=40)"""
        Packet = FLY_BOOK_PROTO.Packet()
        Packet.payloadType = 1
        Packet.cmd = 40
        Packet.cid = request_id

        # MarkRead payload: field1=chatId, field2=messageId, field3=maxUint64, field6=requestId
        payload = b''
        payload += ProtoBuilder._encode_string_field(1, str(chat_id))
        payload += ProtoBuilder._encode_string_field(2, str(message_id))
        payload += ProtoBuilder._encode_varint_field(3, 0xFFFFFFFFFFFFFFFF)
        payload += ProtoBuilder._encode_string_field(6, request_id)

        Packet.payload = payload
        return Packet

    @staticmethod
    def build_send_message_in_thread_request_proto(sends_text, request_id, chatId, rootId):
        """Build send message in thread request (cmd=5 with rootId)"""
        cid_1 = generate_request_cid()
        cid_2 = generate_request_cid()

        Packet = FLY_BOOK_PROTO.Packet()
        Packet.payloadType = 1
        Packet.cmd = 5
        Packet.cid = request_id

        PutMessageRequest = FLY_BOOK_PROTO.PutMessageRequest()
        PutMessageRequest.type = 4
        PutMessageRequest.chatId = chatId
        PutMessageRequest.cid = cid_1
        PutMessageRequest.isNotified = 1
        PutMessageRequest.version = 1
        PutMessageRequest.rootId = rootId
        PutMessageRequest.parentId = rootId

        PutMessageRequest.content.richText.elementIds.append(cid_2)
        PutMessageRequest.content.richText.innerText = sends_text
        PutMessageRequest.content.richText.elements.dictionary[cid_2].tag = 1

        TextProperty = FLY_BOOK_PROTO.TextProperty()
        TextProperty.content = str(sends_text)
        PutMessageRequest.content.richText.elements.dictionary[cid_2].property = TextProperty.SerializeToString()

        Packet.payload = PutMessageRequest.SerializeToString()
        return Packet

    # Raw protobuf encoding helpers
    @staticmethod
    def _encode_varint(value):
        """Encode a value as a protobuf varint"""
        result = b''
        value = value & 0xFFFFFFFFFFFFFFFF  # ensure unsigned 64-bit
        while value >= 0x80:
            result += bytes([value & 0x7F | 0x80])
            value >>= 7
        result += bytes([value & 0x7F])
        return result

    @staticmethod
    def _encode_varint_field(field_number, value):
        """Encode a varint field (wire type 0)"""
        tag = ProtoBuilder._encode_varint(field_number << 3)
        return tag + ProtoBuilder._encode_varint(value)

    @staticmethod
    def _encode_string_field(field_number, value):
        """Encode a string field (wire type 2)"""
        return ProtoBuilder._encode_bytes_field(field_number, value.encode('utf-8'))

    @staticmethod
    def _encode_bytes_field(field_number, value):
        """Encode a bytes field (wire type 2)"""
        tag = ProtoBuilder._encode_varint((field_number << 3) | 2)
        length = ProtoBuilder._encode_varint(len(value))
        return tag + length + value

    @staticmethod
    def _decode_varint(data, offset=0):
        """Decode a varint from data at offset, return (value, new_offset)"""
        value = 0
        shift = 0
        while offset < len(data):
            b = data[offset]
            value |= (b & 0x7F) << shift
            offset += 1
            if (b & 0x80) == 0:
                return value, offset
            shift += 7
        return value, offset

    @staticmethod
    def _decode_varint_field(data, target_field):
        """Find and decode first varint field with given field number"""
        offset = 0
        while offset < len(data):
            tag, offset = ProtoBuilder._decode_varint(data, offset)
            field_num = tag >> 3
            wire_type = tag & 7
            if wire_type == 0:
                value, offset = ProtoBuilder._decode_varint(data, offset)
                if field_num == target_field:
                    return value, True
            elif wire_type == 2:
                length, offset = ProtoBuilder._decode_varint(data, offset)
                offset += length
            else:
                break
        return None, False

    @staticmethod
    def _decode_bytes_field(data, target_field):
        """Find and decode first bytes field with given field number"""
        offset = 0
        while offset < len(data):
            tag, offset = ProtoBuilder._decode_varint(data, offset)
            field_num = tag >> 3
            wire_type = tag & 7
            if wire_type == 0:
                _, offset = ProtoBuilder._decode_varint(data, offset)
            elif wire_type == 2:
                length, offset = ProtoBuilder._decode_varint(data, offset)
                value = data[offset:offset + length]
                offset += length
                if field_num == target_field:
                    return value, True
            else:
                break
        return None, False