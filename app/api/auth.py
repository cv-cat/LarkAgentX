from http.cookies import SimpleCookie

from app.config.settings import settings

class LarkAuth:
    """Authentication for Lark API"""
    
    def __init__(self, cookie_str=None):
        """Initialize LarkAuth with optional cookie string"""
        self.cookie = {}
        if cookie_str:
            self.prepare_auth(cookie_str)
        elif settings.LARK_COOKIE:
            self.prepare_auth(settings.LARK_COOKIE)
    
    def prepare_auth(self, cookie_str):
        """Process cookie string to dict format"""
        cookie = SimpleCookie()
        cookie.load(cookie_str)
        self.cookie = {k: v.value for k, v in cookie.items()}
        return self.cookie

def get_auth():
    """Get LarkAuth instance with cookie from config"""
    return LarkAuth() 