#!/usr/bin/env bash
set -euo pipefail

SERVICE="telegram-llm.service"
APP_ROOT="/opt/telegram-llm"
CURRENT_LINK="$APP_ROOT/current"
CONFIG_DIR="/etc/telegram-llm"
SECRET_ENV="$CONFIG_DIR/telegram-llm.env"
REVISION_ENV="$CONFIG_DIR/revision.env"
UNIT_DEST="/etc/systemd/system/$SERVICE"
STATE_DIR="/var/lib/telegram-llm"
PORT="8787"
HEALTH_URL="http://127.0.0.1:$PORT/health"

fail() {
    printf 'QUALIFICATION=FAIL reason=%s\n' "$*" >&2
    exit 2
}

[[ $# -eq 1 ]] || fail "usage: $0 <expected-40-char-sha>"
EXPECTED_SHA="$1"
[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "expected revision must be a full lowercase Git SHA"
[[ "$(hostname)" == "pi-guy" ]] || fail "unexpected host"

for command in systemctl systemd-analyze curl python3 readlink stat cmp ss; do
    command -v "$command" >/dev/null 2>&1 || fail "required command missing: $command"
done

TARGET_RELEASE="$APP_ROOT/releases/$EXPECTED_SHA"
[[ -d "$TARGET_RELEASE" ]] || fail "expected release is absent"
[[ -f "$TARGET_RELEASE/.source-revision" ]] || fail "release revision marker is absent"
[[ "$(cat "$TARGET_RELEASE/.source-revision")" == "$EXPECTED_SHA" ]] || fail "release marker mismatches"
[[ "$(readlink -f "$CURRENT_LINK")" == "$TARGET_RELEASE" ]] || fail "current symlink does not select expected release"
[[ -f "$REVISION_ENV" ]] || fail "revision environment file is absent"
[[ "$(cat "$REVISION_ENV")" == "APP_REVISION=$EXPECTED_SHA" ]] || fail "revision environment does not match expected release"
[[ -f "$SECRET_ENV" && ! -L "$SECRET_ENV" ]] || fail "secret environment file is absent or is a symlink"
[[ "$(stat -c '%U:%G:%a' "$SECRET_ENV")" == "root:luke:640" ]] || fail "secret environment metadata is not root:luke:0640"

cmp -s "$TARGET_RELEASE/deploy/systemd/telegram-llm.service" "$UNIT_DEST" || fail "installed systemd unit differs from release unit"
systemd-analyze verify "$UNIT_DEST"
systemctl is-enabled --quiet "$SERVICE" || fail "service is not enabled"
systemctl is-active --quiet "$SERVICE" || fail "service is not active"
[[ "$(systemctl show "$SERVICE" -p User --value)" == "luke" ]] || fail "service user is not luke"
[[ "$(systemctl show "$SERVICE" -p MainPID --value)" != "0" ]] || fail "service has no main PID"

mapfile -t LISTENERS < <(ss -H -ltn | awk -v port=":$PORT" '$4 ~ port "$" {print $4}')
[[ ${#LISTENERS[@]} -eq 1 ]] || fail "expected exactly one TCP listener on port $PORT"
[[ "${LISTENERS[0]}" == "127.0.0.1:$PORT" ]] || fail "service is not bound exclusively to IPv4 loopback"

[[ -d "$STATE_DIR" ]] || fail "state directory is absent"
[[ "$(stat -c '%U:%G:%a' "$STATE_DIR")" == "luke:luke:700" ]] || fail "state directory metadata is not luke:luke:0700"
[[ -f "$STATE_DIR/telegram-llm.sqlite3" ]] || fail "SQLite database is absent"

HEALTH_JSON="$(curl --fail --silent --show-error --max-time 5 "$HEALTH_URL")" || fail "local health endpoint is unavailable"
python3 - "$EXPECTED_SHA" "$HEALTH_JSON" <<'PY' || fail "health payload does not match expected revision/storage state"
import json
import sys
expected, raw = sys.argv[1], sys.argv[2]
value = json.loads(raw)
if value.get("status") != "ok":
    raise SystemExit(1)
if value.get("storage") != "ok":
    raise SystemExit(1)
if value.get("revision") != expected:
    raise SystemExit(1)
PY

printf 'LOCAL_PI_QUALIFICATION=PASS\n'
printf 'HOST=pi-guy\n'
printf 'REVISION=%s\n' "$EXPECTED_SHA"
printf 'SERVICE_ACTIVE=true\n'
printf 'SERVICE_ENABLED=true\n'
printf 'LISTENER=127.0.0.1:%s\n' "$PORT"
printf 'STORAGE=ok\n'
