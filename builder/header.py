from app.utils.lark_utils import generate_request_id, generate_long_request_id

class Header:
    def __init__(self):
        self.headers = {}

    def set_header(self, key, value):
        self.headers[key] = value

    def set_header_from_dict(self, kv):
        for k, v in kv.items():
            self.set_header(k, v)

    def remove_header(self, key):
        if key in self.headers:
            del self.headers[key]

    def get(self):
        return self.headers

class HeaderBuilder:
    @staticmethod
    def build_common_header():
        common_header = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "cache-control": "max-age=0",
            "priority": "u=0, i",
            "sec-ch-ua": "\"Microsoft Edge\";v=\"125\", \"Chromium\";v=\"125\", \"Not.A/Brand\";v=\"24\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
        }
        header = Header()
        header.set_header_from_dict(common_header)
        return header

    @staticmethod
    def build_get_csrf_token_header():
        get_csrf_token_header = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "cache-control": "no-cache",
            "origin": "https://open-dev.feishu.cn",
            "priority": "u=1, i",
            "referer": "https://open-dev.feishu.cn/",
            "sec-ch-ua": "\"Microsoft Edge\";v=\"125\", \"Chromium\";v=\"125\", \"Not.A/Brand\";v=\"24\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
            "x-api-version": "1.0.8",
            "x-app-id": "12",
            "x-device-info": "platform=websdk",
            "x-lgw-os-type": "1",
            "x-lgw-terminal-type": "2",
            "x-request-id": generate_request_id(),
            "x-terminal-type": "2"
        }
        header = Header()
        header.set_header_from_dict(get_csrf_token_header)
        return header

    @staticmethod
    def build_get_user_info_header(x_csrf_token):
        get_user_info_header = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "cache-control": "no-cache",
            "origin": "https://open-dev.feishu.cn",
            "priority": "u=1, i",
            "referer": "https://open-dev.feishu.cn/",
            "sec-ch-ua": "\"Microsoft Edge\";v=\"125\", \"Chromium\";v=\"125\", \"Not.A/Brand\";v=\"24\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
            "x-api-version": "1.0.8",
            "x-app-id": "12",
            "x-csrf-token": x_csrf_token,
            "x-device-info": "platform=websdk",
            "x-lgw-os-type": "1",
            "x-lgw-terminal-type": "2",
            "x-locale": "zh-CN",
            "x-request-id": generate_long_request_id(),
            "x-terminal-type": "2"
        }
        header = Header()
        header.set_header_from_dict(get_user_info_header)
        return header

    @staticmethod
    def build_send_msg_header():
        send_msg_header = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "content-type": "application/x-protobuf",
            "locale": "zh_CN",
            "origin": "https://open-dev.feishu.cn",
            "priority": "u=1, i",
            "referer": "https://open-dev.feishu.cn/",
            "sec-ch-ua": "\"Microsoft Edge\";v=\"125\", \"Chromium\";v=\"125\", \"Not.A/Brand\";v=\"24\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
            "x-appid": "161471",
            "x-command": "5",
            "x-command-version": "5.7.0",
            "x-lgw-os-type": "1",
            "x-lgw-terminal-type": "2",
            "x-request-id": generate_request_id(),
            "x-source": "web",
            "x-web-version": "3.9.32"
        }
        header = Header()
        header.set_header_from_dict(send_msg_header)
        return header

    @staticmethod
    def build_create_chat_header():
        create_chat_header = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "content-type": "application/x-protobuf",
            "locale": "zh_CN",
            "origin": "https://open-dev.feishu.cn",
            "priority": "u=1, i",
            "referer": "https://open-dev.feishu.cn/",
            "sec-ch-ua": "\"Microsoft Edge\";v=\"125\", \"Chromium\";v=\"125\", \"Not.A/Brand\";v=\"24\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
            "x-appid": "161471",
            "x-command": "13",
            "x-command-version": "2.7.0",
            "x-lgw-os-type": "1",
            "x-lgw-terminal-type": "2",
            "x-request-id": generate_request_id(),
            "x-source": "web",
            "x-web-version": "3.9.32"
        }
        header = Header()
        header.set_header_from_dict(create_chat_header)
        return header


    @staticmethod
    def build_search_header():
        search_header = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "content-type": "application/x-protobuf",
            "locale": "zh_CN",
            "origin": "https://open-dev.feishu.cn",
            "priority": "u=1, i",
            "referer": "https://open-dev.feishu.cn/",
            "sec-ch-ua": "\"Microsoft Edge\";v=\"125\", \"Chromium\";v=\"125\", \"Not.A/Brand\";v=\"24\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
            "x-appid": "161471",
            "x-command": "11021",
            "x-command-version": "2.7.0",
            "x-lgw-os-type": "1",
            "x-lgw-terminal-type": "2",
            "x-request-id": generate_request_id(),
            "x-source": "web",
            "x-web-version": "3.9.32"
        }
        header = Header()
        header.set_header_from_dict(search_header)
        return header

    @staticmethod
    def build_get_user_all_name_header():
        search_header = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "content-type": "application/x-protobuf",
            "locale": "zh_CN",
            "origin": "https://open-dev.feishu.cn",
            "priority": "u=1, i",
            "referer": "https://open-dev.feishu.cn/",
            "sec-ch-ua": "\"Microsoft Edge\";v=\"125\", \"Chromium\";v=\"125\", \"Not.A/Brand\";v=\"24\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
            "x-appid": "161471",
            "x-command": "5023",
            "x-command-version": "2.7.0",
            "x-lgw-os-type": "1",
            "x-lgw-terminal-type": "2",
            "x-request-id": generate_request_id(),
            "x-source": "web",
            "x-web-version": "3.9.32"
        }
        header = Header()
        header.set_header_from_dict(search_header)
        return header

    @staticmethod
    def build_get_group_name_header():
        search_header = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "content-type": "application/x-protobuf",
            "locale": "zh_CN",
            "origin": "https://open-dev.feishu.cn",
            "priority": "u=1, i",
            "referer": "https://open-dev.feishu.cn/",
            "sec-ch-ua": "\"Microsoft Edge\";v=\"125\", \"Chromium\";v=\"125\", \"Not.A/Brand\";v=\"24\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
            "x-appid": "161471",
            "x-command": "64",
            "x-command-version": "2.7.0",
            "x-lgw-os-type": "1",
            "x-lgw-terminal-type": "2",
            "x-request-id": generate_request_id(),
            "x-source": "web",
            "x-web-version": "3.9.32"
        }
        header = Header()
        header.set_header_from_dict(search_header)
        return header