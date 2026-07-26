import hashlib
import random
import string
import uuid
_ALPHABET = string.digits + string.ascii_letters


def generate_access_key(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


def generate_request_id() -> str:
    return ''.join((random.choice(string.ascii_lowercase + string.digits) for _ in range(10)))


def generate_long_request_id() -> str:
    return str(uuid.uuid4())


def generate_request_cid() -> str:
    return ''.join((random.choice(_ALPHABET) for _ in range(10)))
