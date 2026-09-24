"""
mindgalaxy.auth
================

Username + 4-digit passkey accounts for the hosted, multi-user site.

A 4-digit passkey has only 10,000 possible values, so the protection comes
from refusing to let anyone guess quickly, not from the passkey itself:

* each account locks for 15 minutes after 5 wrong passkeys in a row;
* each IP address may make at most 30 failed logins an hour, across all
  accounts (so someone can't try one passkey against many usernames);
* each IP address may create at most 5 accounts a day.

Passkeys are stored as salted PBKDF2-SHA256 hashes, never in plain text.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from typing import Optional

from .storage import Storage

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,24}$")
PIN_RE = re.compile(r"^\d{4}$")

MAX_ATTEMPTS = 5
LOCK_FOR = _dt.timedelta(minutes=15)
IP_FAILURES_PER_HOUR = 30
SIGNUPS_PER_IP_PER_DAY = 5
_ITERATIONS = 200_000


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def validate(username: str, pin: str) -> None:
    if not USERNAME_RE.match(username):
        raise AuthError("Username must be 3–24 characters: letters, numbers or underscores.")
    if not PIN_RE.match(pin or ""):
        raise AuthError("Passkey must be exactly 4 digits.")


def hash_pin(pin: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${digest.hex()}"


def check_pin(pin: str, stored: str) -> bool:
    try:
        _algo, iterations, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# A throwaway hash so unknown usernames take as long to reject as wrong
# passkeys, and response timing doesn't reveal which usernames exist.
_DUMMY_HASH = hash_pin("0000")


@dataclass
class User:
    id: int
    username: str


def _now() -> _dt.datetime:
    return _dt.datetime.utcnow()


def signup(store: Storage, username: str, pin: str, ip: str) -> User:
    username = normalize_username(username)
    validate(username, pin)
    if store.count_events("signup", ip, _now() - _dt.timedelta(days=1)) >= SIGNUPS_PER_IP_PER_DAY:
        raise AuthError("Too many new accounts from this network today. Try again tomorrow.", 429)
    if store.get_user(username):
        raise AuthError("That username is taken. Pick another, or sign in if it's yours.", 409)
    user_id = store.create_user(username, hash_pin(pin))
    store.log_event("signup", ip)
    return User(user_id, username)


def login(store: Storage, username: str, pin: str, ip: str) -> User:
    username = normalize_username(username)
    if store.count_events("login_fail", ip, _now() - _dt.timedelta(hours=1)) >= IP_FAILURES_PER_HOUR:
        raise AuthError("Too many failed sign-ins from this network. Try again in an hour.", 429)
    wrong = AuthError("Wrong username or passkey.", 401)
    user = store.get_user(username) if USERNAME_RE.match(username) else None
    if user is None:
        check_pin(pin or "", _DUMMY_HASH)
        store.log_event("login_fail", ip)
        raise wrong
    if user["locked_until"] and user["locked_until"] > _now():
        minutes = max(1, int((user["locked_until"] - _now()).total_seconds() // 60) + 1)
        raise AuthError(f"This account is locked after too many wrong passkeys. Try again in {minutes} min.", 423)
    if not PIN_RE.match(pin or "") or not check_pin(pin, user["pin_hash"]):
        store.log_event("login_fail", ip)
        if store.record_login_failure(user["id"], MAX_ATTEMPTS, LOCK_FOR):
            raise AuthError("Too many wrong passkeys. This account is locked for 15 minutes.", 423)
        raise wrong
    store.reset_login_failures(user["id"])
    return User(user["id"], user["username"])
