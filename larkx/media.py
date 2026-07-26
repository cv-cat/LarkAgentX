import os
import requests
from loguru import logger
from .auth import LarkAuth
FILE_HOST = 'https://internal-api-lark-file.feishu.cn'
CDN_HOST = 'https://s1-imfile.feishucdn.com'


def message_resource_url(msg_id: str, key: str, chat_id: str, host: str=FILE_HOST) -> str:
    return f'{host}/download/messages/{msg_id}/keys/{key}?chat_id={chat_id}'


def static_resource_url(key: str, host: str=FILE_HOST) -> str:
    return f'{host}/static-resource/v1/{key}~'


def extract_resource_key(msg_type: int, content_data: dict) -> str:
    if not content_data:
        return ''
    if msg_type == 5:
        v2 = content_data.get('imageV2') or {}
        if v2.get('imageKey'):
            return v2['imageKey']
        img = (content_data.get('image') or {}).get('origin') or {}
        return img.get('key') or (content_data.get('image') or {}).get('imageKey', '')
    if msg_type in (3, 15, 7, 10):
        return content_data.get('key', '')
    return ''


def download(auth: LarkAuth, url: str, out_path: str=None, max_bytes: int=200 * 1024 * 1024):
    with requests.get(url, cookies=auth.cookies, timeout=60, stream=True) as r:
        r.raise_for_status()
        content_type = r.headers.get('content-type', '')
        if not out_path:
            buf = b''
            for chunk in r.iter_content(1 << 16):
                buf += chunk
                if len(buf) > max_bytes:
                    raise ValueError('文件过大')
            return (buf, content_type)
        n = 0
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, 'wb') as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                n += len(chunk)
                if n > max_bytes:
                    raise ValueError('文件过大')
        return (out_path, content_type, n)


def download_message_resource(auth: LarkAuth, msg: dict, out_path: str=None):
    key = extract_resource_key(msg.get('msg_type', 0), msg.get('content_data') or {})
    if not key:
        raise ValueError('该消息没有可下载的资源')
    url = message_resource_url(msg['msg_id'], key, msg['chat_id'])
    logger.info(f'下载资源: {url}')
    return download(auth, url, out_path)
