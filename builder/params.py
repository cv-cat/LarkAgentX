import re
import time
import requests
from builder.header import HeaderBuilder
from app.utils.lark_utils import generate_access_key, generate_request_id


class Params:
    def __init__(self):
        self.params = {}

    def add_param_by_dict(self, params):
        self.params.update(params)

    def add_param(self, key, value):
        self.params[key] = value

    def get(self):
        return self.params


class ParamsBuilder:
    base_url = 'https://open-dev.feishu.cn/messenger/'
    get_ticket_url = "https://login.feishu.cn/suite/passport/frontier_ticket/"

    @staticmethod
    def build_receive_msg_param(auth):
        params = Params()
        headers = HeaderBuilder.build_common_header().get()

        cookies = auth.cookie
        deviceid = cookies.get('passport_web_did')
        res = requests.get(ParamsBuilder.base_url, cookies=cookies, headers=headers)
        res_text = res.text
        appKey = re.findall(r'appKey: "(.*?)"', res_text)[0]
        mystr = f'2{appKey}{deviceid}f8a69f1719916z'
        access_key = generate_access_key(mystr)
        request_id = generate_request_id()
        params.add_param("local_device_id", deviceid)

        response = requests.get(ParamsBuilder.get_ticket_url, headers=headers, cookies=cookies, params=params.get())
        res_json = response.json()
        ticket = res_json.get('ticket')

        params = Params()
        params.add_param_by_dict({
            "access_key": access_key,
            "aid": "1",
            "ticket": ticket,
            "device_id": deviceid,
            "fpid": "2",
            "accept_encoding": "gzip",
            "request_id": request_id
        })
        return params

    @staticmethod
    def build_get_user_info_param():
        params = Params()
        params.add_param_by_dict({
            "app_id": "12",
            "_t": str(int(time.time() * 1000))
        })
        return params

    @staticmethod
    def build_get_csrf_token_param():
        params = Params()
        params.add_param_by_dict({
            "_t": str(int(time.time() * 1000))
        })
        return params

    @classmethod
    def build_get_other_user_info_param(cls, user_id):
        pass
