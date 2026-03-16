"""
Feishu image message decryption and download.

Feishu encrypts image payloads with AES-256-GCM. The WebSocket push message
contains the image_id (CDN path) and encryption key/IV embedded in a nested
protobuf structure. This module handles:
  1. Extracting image_id, decrypt key, and IV from the raw image message content
  2. Downloading the encrypted payload from Feishu CDN
  3. Decrypting with AES-256-GCM
  4. Detecting file type and saving to disk
"""
import os
import hashlib
import binascii
import glob
import requests
from loguru import logger
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

IMAGE_CDN_BASE_URL = "https://s1-imfile.feishucdn.com"
IMAGE_MAX_BYTES = 64 * 1024 * 1024  # 64MB
IMAGE_SAVE_DIR = os.path.expanduser("~/.lark/msg/images")


def decrypt_image_payload(encrypted: bytes, key_hex: str, iv_hex: str) -> bytes:
    """
    Decrypt a Feishu image payload using AES-256-GCM.

    Args:
        encrypted: Raw encrypted bytes from CDN
        key_hex: 32-byte AES key as hex string (64 hex chars)
        iv_hex: 12-byte GCM nonce as hex string (24 hex chars)

    Returns:
        Decrypted image bytes

    Raises:
        ValueError: If key/IV format is invalid
        Exception: If decryption fails
    """
    key = binascii.unhexlify(key_hex.strip())
    iv = binascii.unhexlify(iv_hex.strip())

    if len(key) != 32:
        raise ValueError(f"Unexpected image key length: {len(key)}, expected 32")
    if len(iv) != 12:
        raise ValueError(f"Unexpected image IV length: {len(iv)}, expected 12")
    if len(encrypted) < 16:
        raise ValueError(f"Image payload too small: {len(encrypted)}")

    aesgcm = AESGCM(key)
    # AES-GCM: last 16 bytes are the authentication tag
    # The nonce is the IV
    plaintext = aesgcm.decrypt(iv, encrypted, None)
    return plaintext


def detect_image_type(data: bytes) -> tuple:
    """
    Detect image file type from magic bytes.

    Returns:
        (extension, mime_type) tuple
    """
    if len(data) >= 3 and data[:3] == b'\xff\xd8\xff':
        return "jpg", "image/jpeg"
    if len(data) >= 8 and data[:8] == b'\x89PNG\r\n\x1a\n':
        return "png", "image/png"
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "webp", "image/webp"
    if len(data) >= 6 and (data[:6] == b'GIF87a' or data[:6] == b'GIF89a'):
        return "gif", "image/gif"
    if len(data) >= 2 and data[:2] == b'BM':
        return "bmp", "image/bmp"
    if len(data) >= 4 and (data[:4] == b'\x49\x49\x2a\x00' or data[:4] == b'\x4d\x4d\x00\x2a'):
        return "tiff", "image/tiff"
    return "bin", "application/octet-stream"


def image_download_url(image_id: str) -> str:
    """Build the CDN download URL for an image."""
    base = IMAGE_CDN_BASE_URL.rstrip("/")
    return f"{base}/static-resource/v1/{image_id}~?image_size=&cut_type=&quality=&format=&sticker_format=.webp"


def fetch_image_payload(image_id: str, cookie: str) -> bytes:
    """
    Download encrypted image payload from Feishu CDN.

    Args:
        image_id: Image identifier (e.g., img_v3_xxxx)
        cookie: Authentication cookie string

    Returns:
        Encrypted image bytes
    """
    url = image_download_url(image_id)
    headers = {
        "Cookie": cookie,
        "Referer": "https://xtool.feishu.cn/next/messenger/",
        "User-Agent": "Mozilla/5.0",
    }

    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code < 200 or resp.status_code >= 300:
        raise Exception(f"Download image failed: status={resp.status_code}")

    if len(resp.content) > IMAGE_MAX_BYTES:
        raise Exception(f"Image payload exceeds {IMAGE_MAX_BYTES} bytes")

    return resp.content


def save_image(plaintext: bytes, image_id: str, message_id: str = None, save_dir: str = None) -> dict:
    """
    Save decrypted image to disk.

    Args:
        plaintext: Decrypted image bytes
        image_id: Image identifier
        message_id: Optional message ID for filename
        save_dir: Optional override for save directory

    Returns:
        Dict with path, mime_type, sha256, size info
    """
    save_dir = save_dir or IMAGE_SAVE_DIR
    os.makedirs(save_dir, exist_ok=True)

    ext, mime_type = detect_image_type(plaintext)

    base_name = f"{message_id}_{image_id}" if message_id else image_id
    # Sanitize filename
    base_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in base_name)

    file_path = os.path.join(save_dir, f"{base_name}.{ext}")

    with open(file_path, 'wb') as f:
        f.write(plaintext)

    sha256_hash = hashlib.sha256(plaintext).hexdigest()

    return {
        "path": file_path,
        "mime_type": mime_type,
        "sha256": sha256_hash,
        "size": len(plaintext),
        "extension": ext,
    }


def find_cached_image(image_id: str, message_id: str = None, save_dir: str = None) -> dict:
    """
    Check if image is already downloaded and cached.

    Returns:
        Dict with image info if cached, None otherwise
    """
    save_dir = save_dir or IMAGE_SAVE_DIR
    base_name = f"{message_id}_{image_id}" if message_id else image_id
    base_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in base_name)

    matches = glob.glob(os.path.join(save_dir, f"{base_name}.*"))
    for match in matches:
        if os.path.isfile(match) and os.path.getsize(match) > 0:
            with open(match, 'rb') as f:
                data = f.read()
            ext, mime_type = detect_image_type(data)
            sha256_hash = hashlib.sha256(data).hexdigest()
            return {
                "path": match,
                "mime_type": mime_type,
                "sha256": sha256_hash,
                "size": len(data),
                "extension": ext,
                "cached": True,
            }
    return None


def download_and_decrypt_image(image_id: str, key_hex: str, iv_hex: str,
                                cookie: str, message_id: str = None,
                                save_dir: str = None) -> dict:
    """
    Full pipeline: check cache -> download -> decrypt -> save.

    Args:
        image_id: Image identifier
        key_hex: Decryption key as hex string
        iv_hex: Decryption IV as hex string
        cookie: Auth cookie string
        message_id: Optional message ID
        save_dir: Optional save directory override

    Returns:
        Dict with image info including path, mime_type, sha256, size
    """
    # Check cache first
    cached = find_cached_image(image_id, message_id, save_dir)
    if cached:
        logger.debug(f"Image {image_id} found in cache")
        return cached

    # Download
    logger.info(f"Downloading image {image_id}...")
    encrypted = fetch_image_payload(image_id, cookie)

    # Decrypt
    logger.info(f"Decrypting image {image_id} ({len(encrypted)} bytes)...")
    plaintext = decrypt_image_payload(encrypted, key_hex, iv_hex)

    # Save
    result = save_image(plaintext, image_id, message_id, save_dir)
    result["cached"] = False
    logger.info(f"Image saved: {result['path']} ({result['mime_type']}, {result['size']} bytes)")

    return result


def parse_image_decrypt_info(raw_content: bytes) -> dict:
    """
    Extract image_id, decrypt key, and IV from raw image message content bytes.
    Uses raw protobuf parsing (no generated code needed).

    The image content has this nested structure:
    - field 2 (bytes): image payload
      - field 1 (bytes): image_id string
      - field 2 (bytes): CDN info string
      - field 3 (bytes): crypto info
        - field 2 (bytes): inner crypto
          - field 1 (bytes): AES key (32 bytes)
          - field 2 (bytes): GCM IV (12 bytes)
        OR directly:
          - field 1 (bytes): AES key
          - field 2 (bytes): GCM IV

    Also tries Content.imageKey (field 2 of Content message) as fallback.

    Returns:
        Dict with image_id, key_hex, iv_hex (may be empty strings if not found)
    """
    result = {
        "image_id": "",
        "key_hex": "",
        "iv_hex": "",
        "cdn": "",
    }

    if not raw_content:
        return result

    # Try Content.imageKey first (field 2 as string)
    try:
        import static.proto_pb2 as FLY_BOOK_PROTO
        content = FLY_BOOK_PROTO.Content()
        content.ParseFromString(raw_content)
        image_key = content.imageKey
        if image_key and image_key.strip():
            result["image_id"] = image_key.strip()
            return result
    except Exception:
        pass

    # Parse nested protobuf manually
    # field 2 = image payload
    image_payload = _proto_get_bytes_field(raw_content, 2)
    if not image_payload:
        return result

    # field 1 of image_payload = image_id
    image_id_bytes = _proto_get_bytes_field(image_payload, 1)
    if image_id_bytes:
        result["image_id"] = image_id_bytes.decode('utf-8', errors='ignore').strip()

    # field 2 of image_payload = CDN info
    cdn_bytes = _proto_get_bytes_field(image_payload, 2)
    if cdn_bytes:
        result["cdn"] = cdn_bytes.decode('utf-8', errors='ignore').strip()

    # field 3 of image_payload = crypto info
    crypto_info = _proto_get_bytes_field(image_payload, 3)
    if crypto_info:
        key, iv = _extract_key_iv(crypto_info)
        if key:
            result["key_hex"] = binascii.hexlify(key).decode()
        if iv:
            result["iv_hex"] = binascii.hexlify(iv).decode()

    return result


def _extract_key_iv(crypto_raw: bytes) -> tuple:
    """
    Extract AES key and GCM IV from crypto info protobuf.
    Tries inner field 2 first (nested wrapper), then direct fields.
    """
    key = None
    iv = None

    # Try nested: field 2 -> then field 1 (key) and field 2 (iv)
    candidates = [crypto_raw]
    inner = _proto_get_bytes_field(crypto_raw, 2)
    if inner:
        candidates.insert(0, inner)

    for candidate in candidates:
        if key is None:
            val = _proto_get_bytes_field(candidate, 1)
            if val and _looks_binary_secret(val):
                key = val
        if iv is None:
            val = _proto_get_bytes_field(candidate, 2)
            if val and _looks_binary_secret(val):
                iv = val

    return key, iv


def _looks_binary_secret(data: bytes) -> bool:
    """Check if bytes look like a cryptographic key/IV (not printable text)."""
    if len(data) not in (12, 16, 24, 32, 48):
        return False
    try:
        text = data.decode('utf-8')
        if all(0x20 <= ord(c) <= 0x7e for c in text):
            return False  # All printable ASCII, probably not a key
    except UnicodeDecodeError:
        pass
    return True


def _proto_decode_varint(data: bytes, offset: int = 0) -> tuple:
    """Decode a protobuf varint. Returns (value, new_offset)."""
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


def _proto_get_bytes_field(data: bytes, target_field: int) -> bytes:
    """Find and return the first length-delimited field with given number."""
    offset = 0
    while offset < len(data):
        try:
            tag, offset = _proto_decode_varint(data, offset)
        except Exception:
            break
        field_num = tag >> 3
        wire_type = tag & 7

        if wire_type == 0:  # varint
            _, offset = _proto_decode_varint(data, offset)
        elif wire_type == 2:  # length-delimited
            length, offset = _proto_decode_varint(data, offset)
            if offset + length > len(data):
                break
            value = data[offset:offset + length]
            offset += length
            if field_num == target_field:
                return value
        elif wire_type == 5:  # 32-bit
            offset += 4
        elif wire_type == 1:  # 64-bit
            offset += 8
        else:
            break
    return None
