import mimetypes
import os
import re
import zlib
from pathlib import Path

import requests
from loguru import logger
from .auth import LarkAuth
from .config import load_config
from .region import get_region


def message_resource_url(msg_id: str, key: str, chat_id: str, host: str=None) -> str:
    """host 为所属区域的文件主机(LarkAuth.region.file_host),不传时取 LARKX_REGION。"""
    host = host or get_region(load_config()['region']).file_host
    return f'{host}/download/messages/{msg_id}/keys/{key}?chat_id={chat_id}'


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
    url = message_resource_url(msg['msg_id'], key, msg['chat_id'], host=auth.region.file_host)
    logger.info(f'下载资源: {url}')
    return download(auth, url, out_path)


# ---- 上传(发图片、文件前先上传拿到 key) ----
# 接口在文件主机上,带登录 cookie,请求和响应是 lark.pan 里的 protobuf:
#   图片: POST /api/image,表单字段 image,响应的 key 是图片 key
#   文件: /upload/create 拿到 uploadId(就是文件 key) -> 逐块 /upload/part -> /upload/complete
UPLOAD_PART_SIZE = 4 * 1024 * 1024
MAX_UPLOAD = 100 * 1024 * 1024
_KEY = re.compile(r'[\w\-.]{1,200}')


class UploadError(Exception):
    pass


def _pan():
    from .proto.gateway import _lark_all
    return _lark_all().pan


def _post(auth: LarkAuth, path: str, what: str, content_type: str = '', **kwargs) -> bytes:
    headers = {'origin': auth.region.web_origin, 'referer': auth.region.web_origin + '/',
               'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'}
    if content_type:
        headers['content-type'] = content_type
    try:
        r = requests.post(auth.region.file_host + path, cookies=auth.cookies, headers=headers, timeout=120, **kwargs)
    except requests.RequestException as e:
        raise UploadError(f'{what}失败: {e}') from e
    if r.status_code != 200:
        raise UploadError(f'{what}失败: HTTP {r.status_code}')
    return r.content


def upload_image(auth: LarkAuth, path: str) -> str:
    """上传一张图片,返回图片 key。"""
    data = Path(path).read_bytes()
    if len(data) > MAX_UPLOAD:
        raise UploadError('图片太大')
    mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    resp = _pan().PutFileResponse.FromString(_post(auth, '/api/image', '上传图片', files={'image': (Path(path).name, data, mime)}))
    if not _KEY.fullmatch(resp.key or ''):
        raise UploadError('上传图片失败: 响应里没有图片 key')
    return resp.key


def upload_file(auth: LarkAuth, path: str) -> dict:
    """分块上传一个文件,返回 {'key', 'name', 'size', 'mime'}。"""
    p = Path(path)
    size = p.stat().st_size
    if size <= 0:
        raise UploadError('不能上传空文件')
    if size > MAX_UPLOAD:
        raise UploadError('文件太大(上限 100MB)')
    name, mime = p.name, mimetypes.guess_type(path)[0] or ''
    pan = _pan()
    created = pan.CreateFileUploadResponse.FromString(_post(
        auth, '/upload/create', '创建上传', 'application/x-protobuf',
        data=pan.CreateFileUploadRequest(fileType=1, fileName=name, fileSize=size).SerializeToString()))
    upload_id = created.uploadId
    if not _KEY.fullmatch(upload_id or ''):
        raise UploadError('创建上传失败: 响应里没有 uploadId')
    complete = pan.CompleteFileUploadRequest(uploadId=upload_id, fileType=1, fileName=name, mime=mime)
    with p.open('rb') as f:
        part_id = 0
        while True:
            chunk = f.read(UPLOAD_PART_SIZE)
            if not chunk:
                break
            part_id += 1
            part = pan.UploadFilePartResponse.FromString(_post(
                auth, '/upload/part', f'上传第 {part_id} 块', 'application/octet-stream',
                params={'upload_id': upload_id, 'part_id': part_id}, data=chunk))
            crc = zlib.crc32(chunk)
            if part.partId != part_id or part.crc32 != crc:
                raise UploadError(f'上传第 {part_id} 块失败: 校验和不一致')
            complete.partToCrc32[part_id] = crc
    result = pan.CompleteFileUploadResponse.FromString(_post(
        auth, '/upload/complete', '完成上传', 'application/x-protobuf', data=complete.SerializeToString()))
    if result.code != 0:
        raise UploadError(f'完成上传失败: code={result.code}')
    return {'key': upload_id, 'name': name, 'size': size, 'mime': mime}
