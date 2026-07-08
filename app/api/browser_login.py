"""
Browser-based login for Feishu/Lark.
Opens a browser window for the user to login and captures the session cookie.
"""
import os
import json
import asyncio
from loguru import logger

# Cookie storage path
COOKIE_FILE = os.path.expanduser("~/.lark/msg/cookie.json")
LOGIN_URL = "https://www.feishu.cn/messenger/"
# Required cookie that indicates successful login
AUTH_COOKIE_NAME = "session"


def ensure_cookie_dir():
    """Ensure the cookie storage directory exists"""
    os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)


def save_cookie_to_file(cookie_str: str):
    """Save cookie string to local file"""
    ensure_cookie_dir()
    with open(COOKIE_FILE, 'w') as f:
        json.dump({"cookie": cookie_str}, f)
    logger.info(f"Cookie saved to {COOKIE_FILE}")


def load_cookie_from_file() -> str:
    """Load cookie string from local file"""
    if not os.path.exists(COOKIE_FILE):
        return ""
    try:
        with open(COOKIE_FILE, 'r') as f:
            data = json.load(f)
            return data.get("cookie", "")
    except Exception as e:
        logger.warning(f"Failed to load cookie from file: {e}")
        return ""


def clear_saved_cookie():
    """Remove saved cookie file"""
    if os.path.exists(COOKIE_FILE):
        os.remove(COOKIE_FILE)
        logger.info("Saved cookie cleared")


async def browser_login(timeout: int = 180) -> str:
    """
    Open a browser for Feishu login and capture cookies.

    Args:
        timeout: Maximum wait time in seconds (default: 3 minutes)

    Returns:
        Cookie string for API authentication

    Raises:
        TimeoutError: If login is not completed within timeout
        ImportError: If playwright is not installed
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise ImportError(
            "playwright is required for browser login. "
            "Install with: pip install playwright && playwright install chromium"
        )

    logger.info("Starting browser login...")
    logger.info(f"Opening {LOGIN_URL}")
    logger.info(f"Please login within {timeout} seconds...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(LOGIN_URL)

        # Poll for login completion by checking cookies
        import time
        start_time = time.time()
        cookie_str = ""

        while time.time() - start_time < timeout:
            cookies = await context.cookies()

            # Check for session cookie that indicates successful login
            has_session = any(
                c['name'] in ('session', 'session_list', 'passport_web_did')
                for c in cookies
            )

            # Also check if we've navigated to messenger (login complete)
            current_url = page.url
            if has_session and ('messenger' in current_url or 'suite' in current_url):
                # Build cookie string
                cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
                logger.info("Login successful! Cookie captured.")
                break

            await asyncio.sleep(1)

        await browser.close()

    if not cookie_str:
        raise TimeoutError(f"Login not completed within {timeout} seconds")

    # Save cookie to file
    save_cookie_to_file(cookie_str)

    return cookie_str


def login_interactive(timeout: int = 180) -> str:
    """
    Synchronous wrapper for browser login.

    Returns:
        Cookie string for API authentication
    """
    return asyncio.run(browser_login(timeout))
