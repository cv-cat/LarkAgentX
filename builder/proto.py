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
            'content': None
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
                    ReceiveTextContent['fromId'] = fromId
                    ReceiveTextContent['chatId'] = chatId
                    ReceiveTextContent['chatType'] = chatType
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