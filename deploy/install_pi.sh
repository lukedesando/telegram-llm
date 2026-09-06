#!/usr/bin/env bash
set -Eeuo pipefail

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

for command in git python3 tar install systemctl systemd-analyze curl stat getent sed cp rm mv ln readlink mktemp awk grep ss journalctl sleep; do
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
    cleanup_staging() {
        rm -rf -- "$STAGING_DIR"
    }
    trap cleanup_staging EXIT

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

PREVIOUS_CURRENT_TARGET=""
PREVIOUS_SHA=""
if [[ -L "$CURRENT_LINK" ]]; then
    PREVIOUS_CURRENT_TARGET="$(readlink -f "$CURRENT_LINK" 2>/dev/null || true)"
    [[ -n "$PREVIOUS_CURRENT_TARGET" ]] || fail "existing current symlink is broken; repair or use rollback before activation"
    [[ "$PREVIOUS_CURRENT_TARGET" == "$RELEASE_ROOT/"* ]] || fail "existing current symlink points outside the managed release root"
    [[ -f "$PREVIOUS_CURRENT_TARGET/.source-revision" ]] || fail "existing selected release lacks revision marker"
    PREVIOUS_SHA="$(cat "$PREVIOUS_CURRENT_TARGET/.source-revision")"
    [[ "$PREVIOUS_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "existing selected release has invalid revision marker"
    [[ "$PREVIOUS_CURRENT_TARGET" == "$RELEASE_ROOT/$PREVIOUS_SHA" ]] || fail "existing selected release path and revision marker disagree"
elif [[ -e "$CURRENT_LINK" ]]; then
    fail "current path exists and is not a symlink"
fi

PREVIOUS_UNIT_BACKUP=""
if [[ -e "$UNIT_DEST" ]]; then
    [[ -f "$UNIT_DEST" && ! -L "$UNIT_DEST" ]] || fail "installed unit path is not a regular file"
    PREVIOUS_UNIT_BACKUP="$(mktemp /run/telegram-llm-unit-before.XXXXXX)"
    cp -p -- "$UNIT_DEST" "$PREVIOUS_UNIT_BACKUP"
fi

PREVIOUS_REVISION_BACKUP=""
if [[ -e "$REVISION_ENV" ]]; then
    [[ -f "$REVISION_ENV" && ! -L "$REVISION_ENV" ]] || fail "revision environment path is not a regular file"
    PREVIOUS_REVISION_BACKUP="$(mktemp /run/telegram-llm-revision-before.XXXXXX)"
    cp -p -- "$REVISION_ENV" "$PREVIOUS_REVISION_BACKUP"
fi

PREVIOUS_ENABLED=false
if systemctl is-enabled --quiet "$SERVICE" 2>/dev/null; then
    PREVIOUS_ENABLED=true
fi
PREVIOUS_ACTIVE=false
if systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
    PREVIOUS_ACTIVE=true
fi
if [[ "$PREVIOUS_ACTIVE" == true && -z "$PREVIOUS_CURRENT_TARGET" ]]; then
    fail "active service has no restorable managed current release"
fi

if [[ "$PREVIOUS_ACTIVE" != true ]]; then
    if ss -H -ltn | awk '{print $4}' | grep -Eq ":${PORT}$"; then
        fail "TCP port $PORT is already in use before activation"
    fi
fi

TRANSACTION_ACTIVE=false
cleanup_backups() {
    [[ -z "$PREVIOUS_UNIT_BACKUP" ]] || rm -f -- "$PREVIOUS_UNIT_BACKUP"
    [[ -z "$PREVIOUS_REVISION_BACKUP" ]] || rm -f -- "$PREVIOUS_REVISION_BACKUP"
}
restore_previous_activation() {
    local original_status="$1"
    trap - EXIT
    set +e
    printf 'ACTIVATION_ROLLBACK=START\n' >&2

    systemctl stop "$SERVICE" >/dev/null 2>&1 || true
    if [[ "$PREVIOUS_ENABLED" == true ]]; then
        systemctl enable "$SERVICE" >/dev/null 2>&1 || true
    else
        systemctl disable "$SERVICE" >/dev/null 2>&1 || true
    fi

    if [[ -n "$PREVIOUS_CURRENT_TARGET" ]]; then
        local restore_link="$APP_ROOT/.restore-$PREVIOUS_SHA-$$"
        ln -s -- "$PREVIOUS_CURRENT_TARGET" "$restore_link"
        mv -Tf -- "$restore_link" "$CURRENT_LINK"
    else
        rm -f -- "$CURRENT_LINK"
    fi

    if [[ -n "$PREVIOUS_REVISION_BACKUP" ]]; then
        cp -p -- "$PREVIOUS_REVISION_BACKUP" "$REVISION_ENV"
    else
        rm -f -- "$REVISION_ENV"
    fi

    if [[ -n "$PREVIOUS_UNIT_BACKUP" ]]; then
        cp -p -- "$PREVIOUS_UNIT_BACKUP" "$UNIT_DEST"
    else
        rm -f -- "$UNIT_DEST"
    fi

    systemctl daemon-reload >/dev/null 2>&1 || true
    if [[ "$PREVIOUS_ACTIVE" == true ]]; then
        systemctl start "$SERVICE" >/dev/null 2>&1 || true
    else
        systemctl stop "$SERVICE" >/dev/null 2>&1 || true
    fi

    cleanup_backups
    printf 'ACTIVATION_ROLLBACK=COMPLETE previous_revision=%s previous_active=%s previous_enabled=%s\n' \
        "${PREVIOUS_SHA:-none}" "$PREVIOUS_ACTIVE" "$PREVIOUS_ENABLED" >&2
    exit "$original_status"
}
activation_exit() {
    local status="$?"
    if [[ "$TRANSACTION_ACTIVE" == true && "$status" -ne 0 ]]; then
        restore_previous_activation "$status"
    fi
    cleanup_backups
}
trap activation_exit EXIT
TRANSACTION_ACTIVE=true

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
        TRANSACTION_ACTIVE=false
        cleanup_backups
        trap - EXIT
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
