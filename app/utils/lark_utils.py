"""
Lark API utility functions
"""
import os
import execjs
import subprocess
from loguru import logger
from functools import partial

subprocess.Popen = partial(subprocess.Popen, encoding="utf-8")

def init_js():
    """
    Initialize JavaScript environment for Lark decryption
    """
    try:
        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        js_path = os.path.join(script_dir, 'static', 'lark_decrypt.js')
        pathext = os.environ.get("PATHEXT", "")
        if '.EXE' not in pathext:
            pathext += '.EXE;'
            os.environ['PATHEXT'] = pathext
        lark_decrypt_js = execjs.compile(open(js_path, 'r', encoding='utf-8').read())
        return lark_decrypt_js
    except Exception as e:
        try:
            script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            js_path = os.path.join(script_dir, 'static', 'lark_decrypt.js')
            lark_decrypt_js = execjs.compile(open(js_path, 'r', encoding='utf-8').read())
            return lark_decrypt_js
        except Exception as e:
            logger.error(f"Error: Could not load JavaScript file: {e}")
            return None


def trans_cookies(cookies_str):
    """
    Transform cookie string to dictionary
    
    Args:
        cookies_str (str): Cookie string
        
    Returns:
        dict: Cookie dictionary
    """
    cookies = dict()
    for i in cookies_str.split("; "):
        try:
            cookies[i.split('=')[0]] = '='.join(i.split('=')[1:])
        except:
            continue
    return cookies

def generate_access_key(mystr):
    """Generate access key using JavaScript function"""
    lark_decrypt_js = init_js()
    if lark_decrypt_js:
        access_key = lark_decrypt_js.call('generate_access_key', mystr)
        return access_key
    return None

def generate_request_id():
    """Generate request ID using JavaScript function"""
    lark_decrypt_js = init_js()
    if lark_decrypt_js:
        request_id = lark_decrypt_js.call('generate_request_id')
        return request_id
    return None

def generate_long_request_id():
    """Generate long request ID using JavaScript function"""
    lark_decrypt_js = init_js()

    if lark_decrypt_js:
        request_id = lark_decrypt_js.call('generate_long_request_id')
        return request_id
    return None

def generate_request_cid():
    """Generate request CID using JavaScript function"""
    lark_decrypt_js = init_js()
    if lark_decrypt_js:
        request_cid = lark_decrypt_js.call('generate_request_cid')
        return request_cid
    return None
