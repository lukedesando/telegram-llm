#!/usr/bin/env bash
set -euo pipefail

SERVICE="telegram-llm.service"
SERVICE_USER="luke"
SERVICE_GROUP="luke"
PORT="8787"
APP_ROOT="/opt/telegram-llm"
RELEASE_ROOT="$APP_ROOT/releases"
CURRENT_LINK="$APP_ROOT/current"
CONFIG_DIR="/etc/telegram-llm"
SECRET_ENV="$CONFIG_DIR/telegram-llm.env"
REVISION_ENV="$CONFIG_DIR/revision.env"
UNIT_DEST="/etc/systemd/system/$SERVICE"
HEALTH_URL="http://127.0.0.1:$PORT/health"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 2
}

usage() {
    printf 'Usage: sudo %s <40-char-main-sha> [--prepare-only]\n' "$0" >&2
    exit 2
}

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail "must run as root"
[[ $# -ge 1 && $# -le 2 ]] || usage
EXPECTED_SHA="$1"
MODE="activate"
if [[ $# -eq 2 ]]; then
    [[ "$2" == "--prepare-only" ]] || usage
    MODE="prepare"
fi
[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "expected revision must be a full lowercase Git SHA"

for command in git python3 tar install systemctl systemd-analyze curl stat getent sed; do
    command -v "$command" >/dev/null 2>&1 || fail "required command missing: $command"
done

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$SOURCE_DIR"
[[ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" == "true" ]] || fail "source is not a Git checkout"
ACTUAL_SHA="$(git rev-parse HEAD)"
[[ "$ACTUAL_SHA" == "$EXPECTED_SHA" ]] || fail "checkout revision does not match expected revision"
BRANCH="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
[[ "$BRANCH" == "main" ]] || fail "deployment source must be the main branch"
[[ -z "$(git status --porcelain --untracked-files=normal)" ]] || fail "deployment source must be clean"

getent passwd "$SERVICE_USER" >/dev/null || fail "service user does not exist: $SERVICE_USER"
getent group "$SERVICE_GROUP" >/dev/null || fail "service group does not exist: $SERVICE_GROUP"

install -d -m 0755 "$APP_ROOT" "$RELEASE_ROOT"

RELEASE_DIR="$RELEASE_ROOT/$EXPECTED_SHA"
if [[ -e "$RELEASE_DIR" ]]; then
    [[ -d "$RELEASE_DIR" ]] || fail "release path exists but is not a directory"
    [[ -f "$RELEASE_DIR/.source-revision" ]] || fail "existing release lacks revision marker"
    [[ "$(cat "$RELEASE_DIR/.source-revision")" == "$EXPECTED_SHA" ]] || fail "existing release revision marker mismatches"
    [[ -x "$RELEASE_DIR/.venv/bin/python" ]] || fail "existing release lacks virtual environment"
else
    STAGING_DIR="$(mktemp -d "$RELEASE_ROOT/.staging-$EXPECTED_SHA.XXXXXX")"
    cleanup() {
        rm -rf -- "$STAGING_DIR"
    }
    trap cleanup EXIT

    git archive "$EXPECTED_SHA" | tar -x -C "$STAGING_DIR"
    printf '%s\n' "$EXPECTED_SHA" > "$STAGING_DIR/.source-revision"
    python3 -m venv "$STAGING_DIR/.venv"
    "$STAGING_DIR/.venv/bin/python" -m pip install \
        --disable-pip-version-check \
        --no-input \
        --requirement "$STAGING_DIR/requirements.txt"
    "$STAGING_DIR/.venv/bin/python" -m compileall -q "$STAGING_DIR"

    mv -- "$STAGING_DIR" "$RELEASE_DIR"
    trap - EXIT
fi

VERIFY_UNIT="$(mktemp /run/telegram-llm-verify.XXXXXX.service)"
cleanup_verify() {
    rm -f -- "$VERIFY_UNIT"
}
trap cleanup_verify EXIT
sed "s#/opt/telegram-llm/current#$RELEASE_DIR#g" \
    "$RELEASE_DIR/deploy/systemd/telegram-llm.service" > "$VERIFY_UNIT"
systemd-analyze verify "$VERIFY_UNIT"
rm -f -- "$VERIFY_UNIT"
trap - EXIT

printf 'PREPARED_REVISION=%s\n' "$EXPECTED_SHA"
printf 'PREPARED_RELEASE=%s\n' "$RELEASE_DIR"

if [[ "$MODE" == "prepare" ]]; then
    printf 'DEPLOYMENT_STATE=PREPARED_INACTIVE\n'
    exit 0
fi

install -d -m 0750 -o root -g "$SERVICE_GROUP" "$CONFIG_DIR"
[[ -f "$SECRET_ENV" && ! -L "$SECRET_ENV" ]] || fail "secret environment file must exist as a regular file: $SECRET_ENV"
SECRET_META="$(stat -c '%U:%G:%a' "$SECRET_ENV")"
[[ "$SECRET_META" == "root:$SERVICE_GROUP:640" ]] || fail "secret environment file must be owned root:$SERVICE_GROUP with mode 0640"

if ! systemctl is-active --quiet "$SERVICE"; then
    command -v ss >/dev/null 2>&1 || fail "required command missing for first activation: ss"
    if ss -H -ltn | awk '{print $4}' | grep -Eq ":${PORT}$"; then
        fail "TCP port $PORT is already in use before first activation"
    fi
fi

[[ ! -e "$CURRENT_LINK" || -L "$CURRENT_LINK" ]] || fail "current path exists and is not a symlink"
NEXT_LINK="$APP_ROOT/.current-$EXPECTED_SHA-$$"
ln -s -- "$RELEASE_DIR" "$NEXT_LINK"
mv -Tf -- "$NEXT_LINK" "$CURRENT_LINK"

printf 'APP_REVISION=%s\n' "$EXPECTED_SHA" > "$REVISION_ENV"
chown root:root "$REVISION_ENV"
chmod 0644 "$REVISION_ENV"

install -m 0644 "$RELEASE_DIR/deploy/systemd/telegram-llm.service" "$UNIT_DEST"
systemd-analyze verify "$UNIT_DEST"
systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"

attempt=1
while (( attempt <= 30 )); do
    HEALTH_JSON="$(curl --fail --silent --show-error --max-time 3 "$HEALTH_URL" 2>/dev/null || true)"
    if [[ -n "$HEALTH_JSON" ]] && python3 - "$EXPECTED_SHA" "$HEALTH_JSON" <<'PY'
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
        printf 'DEPLOYMENT_STATE=ACTIVE\n'
        printf 'HEALTH=PASS\n'
        printf 'REVISION=%s\n' "$EXPECTED_SHA"
        printf 'CURRENT_RELEASE=%s\n' "$(readlink -f "$CURRENT_LINK")"
        exit 0
    fi
    sleep 1
    ((attempt += 1))
done

systemctl status "$SERVICE" --no-pager >&2 || true
journalctl -u "$SERVICE" -n 80 --no-pager >&2 || true
fail "service did not become healthy at expected revision"
