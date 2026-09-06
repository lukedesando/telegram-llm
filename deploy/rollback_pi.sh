#!/usr/bin/env bash
set -euo pipefail

SERVICE="telegram-llm.service"
APP_ROOT="/opt/telegram-llm"
CURRENT_LINK="$APP_ROOT/current"
CONFIG_DIR="/etc/telegram-llm"
REVISION_ENV="$CONFIG_DIR/revision.env"
UNIT_DEST="/etc/systemd/system/$SERVICE"
HEALTH_URL="http://127.0.0.1:8787/health"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 2
}

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail "must run as root"
[[ $# -eq 1 ]] || fail "usage: sudo $0 <previous-40-char-sha>"
TARGET_SHA="$1"
[[ "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "target revision must be a full lowercase Git SHA"

for command in systemctl systemd-analyze curl python3 install; do
    command -v "$command" >/dev/null 2>&1 || fail "required command missing: $command"
done

TARGET_RELEASE="$APP_ROOT/releases/$TARGET_SHA"
[[ -d "$TARGET_RELEASE" ]] || fail "target release is not installed: $TARGET_RELEASE"
[[ -f "$TARGET_RELEASE/.source-revision" ]] || fail "target release lacks revision marker"
[[ "$(cat "$TARGET_RELEASE/.source-revision")" == "$TARGET_SHA" ]] || fail "target release revision marker mismatches"
[[ -x "$TARGET_RELEASE/.venv/bin/python" ]] || fail "target release lacks virtual environment"
[[ ! -e "$CURRENT_LINK" || -L "$CURRENT_LINK" ]] || fail "current path exists and is not a symlink"

systemd-analyze verify "$TARGET_RELEASE/deploy/systemd/telegram-llm.service"
NEXT_LINK="$APP_ROOT/.rollback-$TARGET_SHA-$$"
ln -s -- "$TARGET_RELEASE" "$NEXT_LINK"
mv -Tf -- "$NEXT_LINK" "$CURRENT_LINK"

printf 'APP_REVISION=%s\n' "$TARGET_SHA" > "$REVISION_ENV"
chown root:root "$REVISION_ENV"
chmod 0644 "$REVISION_ENV"
install -m 0644 "$TARGET_RELEASE/deploy/systemd/telegram-llm.service" "$UNIT_DEST"
systemd-analyze verify "$UNIT_DEST"
systemctl daemon-reload
systemctl restart "$SERVICE"

attempt=1
while (( attempt <= 30 )); do
    HEALTH_JSON="$(curl --fail --silent --show-error --max-time 3 "$HEALTH_URL" 2>/dev/null || true)"
    if [[ -n "$HEALTH_JSON" ]] && python3 - "$TARGET_SHA" "$HEALTH_JSON" <<'PY'
import json
import sys
expected, raw = sys.argv[1], sys.argv[2]
try:
    value = json.loads(raw)
except json.JSONDecodeError:
    raise SystemExit(1)
if value.get("status") != "ok" or value.get("storage") != "ok":
    raise SystemExit(1)
if value.get("revision") != expected:
    raise SystemExit(1)
PY
    then
        printf 'ROLLBACK=PASS\n'
        printf 'REVISION=%s\n' "$TARGET_SHA"
        exit 0
    fi
    sleep 1
    ((attempt += 1))
done

systemctl status "$SERVICE" --no-pager >&2 || true
journalctl -u "$SERVICE" -n 80 --no-pager >&2 || true
fail "rollback target did not become healthy"
