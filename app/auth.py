"""Вход по продуктовому коду, хранение хешей, антибрут по IP."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv()

CODES_FILE = Path(os.getenv("PRODUCT_CODES_FILE", str(ROOT / "data" / "product_codes.txt")))
SECRET = os.getenv("SECRET_KEY", "dev-change-me")
CODE_RE = re.compile(r"^[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}$")
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_FAILS = int(os.getenv("LOGIN_MAX_FAILS", "8"))
WINDOW_MIN = int(os.getenv("LOGIN_WINDOW_MIN", "15"))
LOCK_MIN = int(os.getenv("LOGIN_LOCK_MIN", "20"))
SESSION_COOKIE = "tf_session"


def normalize_code(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", (raw or "").upper())
    if len(cleaned) != 16:
        return ""
    return "-".join(cleaned[i : i + 4] for i in range(0, 16, 4))


def generate_code() -> str:
    chars = [secrets.choice(ALPHABET) for _ in range(16)]
    return "-".join("".join(chars[i : i + 4]) for i in range(0, 16, 4))


def hash_code(code: str) -> str:
    norm = normalize_code(code)
    return hmac.new(SECRET.encode(), norm.encode(), hashlib.sha256).hexdigest()


def load_hashes() -> set[str]:
    if not CODES_FILE.exists():
        return set()
    hashes: set[str] = set()
    for line in CODES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        hashes.add(line.split()[0].lower())
    return hashes


def append_hash(code: str) -> str:
    CODES_FILE.parent.mkdir(parents=True, exist_ok=True)
    digest = hash_code(code)
    existing = load_hashes()
    if digest not in existing:
        with CODES_FILE.open("a", encoding="utf-8") as f:
            f.write(digest + "\n")
    return digest


def code_is_valid(code: str) -> bool:
    return valid_code_hash(code) is not None


def valid_code_hash(code: str) -> str | None:
    """HMAC кода, если он есть в списке выданных; иначе None."""
    norm = normalize_code(code)
    if not norm or not CODE_RE.match(norm):
        return None
    digest = hash_code(norm)
    if digest in load_hashes():
        return digest
    return None


def client_ip(request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def check_lock(db: Session, ip: str):
    from app.models import LoginAttempt

    row = db.get(LoginAttempt, ip)
    if row is None:
        return None
    if row.locked_until and row.locked_until > datetime.utcnow():
        return row.locked_until
    return None


def register_fail(db: Session, ip: str) -> datetime | None:
    from app.models import LoginAttempt

    now = datetime.utcnow()
    row = db.get(LoginAttempt, ip)
    if row is None:
        row = LoginAttempt(ip=ip, fails=0, window_start=now)
        db.add(row)
    if row.window_start is None or now - row.window_start > timedelta(minutes=WINDOW_MIN):
        row.fails = 0
        row.window_start = now
        row.locked_until = None
    row.fails += 1
    row.last_fail = now
    locked = None
    if row.fails >= MAX_FAILS:
        locked = now + timedelta(minutes=LOCK_MIN)
        row.locked_until = locked
    db.commit()
    return locked


def register_ok(db: Session, ip: str) -> None:
    from app.models import LoginAttempt

    row = db.get(LoginAttempt, ip)
    if row:
        db.delete(row)
        db.commit()
