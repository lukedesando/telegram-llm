from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

REQUIRED_SECRET_NAMES = (
    "TELEGRAM_TOKEN",
    "WEBHOOK_SECRET_TOKEN",
    "OPENAI_API_KEY",
)
PI_DATABASE_PATH = "/var/lib/telegram-llm/telegram-llm.sqlite3"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def validate_environment(
    env: dict[str, str],
    *,
    expected_database_path: str = PI_DATABASE_PATH,
) -> list[str]:
    errors: list[str] = []

    for name in REQUIRED_SECRET_NAMES:
        if not env.get(name, "").strip():
            errors.append(f"{name} is required")

    user_id = env.get("TELEGRAM_ALLOWED_USER_ID", "").strip()
    try:
        if int(user_id) <= 0:
            raise ValueError
    except ValueError:
        errors.append("TELEGRAM_ALLOWED_USER_ID must be a positive integer")

    base_url = env.get("WEBHOOK_BASE_URL", "").strip()
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        errors.append("WEBHOOK_BASE_URL must be an absolute HTTPS URL")
    if parsed.username or parsed.password:
        errors.append("WEBHOOK_BASE_URL must not embed credentials")
    if parsed.path:
        errors.append("WEBHOOK_BASE_URL must be an origin only, without a path")
    if parsed.query or parsed.fragment:
        errors.append("WEBHOOK_BASE_URL must not contain a query or fragment")
    if base_url.endswith("/"):
        errors.append("WEBHOOK_BASE_URL must not end with a slash")

    revision = env.get("APP_REVISION", "").strip()
    if not _SHA_RE.fullmatch(revision):
        errors.append("APP_REVISION must be a full 40-character lowercase Git SHA")

    database_path = env.get("DATABASE_PATH", "").strip()
    if database_path != expected_database_path:
        errors.append(f"DATABASE_PATH must be exactly {expected_database_path}")
    else:
        parent = Path(database_path).parent
        if not parent.is_dir():
            errors.append("DATABASE_PATH parent directory does not exist")
        elif not os.access(parent, os.W_OK | os.X_OK):
            errors.append("DATABASE_PATH parent directory is not writable")

    return errors


def main() -> int:
    errors = validate_environment(dict(os.environ))
    if errors:
        for error in errors:
            print(f"PREFLIGHT_ERROR={error}")
        return 2

    print(
        "PREFLIGHT=PASS "
        f"revision={os.environ['APP_REVISION']} "
        f"database_path={os.environ['DATABASE_PATH']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
