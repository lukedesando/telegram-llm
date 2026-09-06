import importlib.util
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"


def _load_preflight_module():
    path = DEPLOY / "preflight.py"
    spec = importlib.util.spec_from_file_location("telegram_llm_deploy_preflight", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DeploymentContractTests(unittest.TestCase):
    def test_shell_scripts_parse(self):
        for name in ("install_pi.sh", "rollback_pi.sh", "qualify_pi.sh"):
            subprocess.run(["bash", "-n", str(DEPLOY / name)], check=True)

    def test_systemd_unit_is_single_worker_loopback_and_hardened(self):
        unit = (DEPLOY / "systemd" / "telegram-llm.service").read_text(encoding="utf-8")
        self.assertIn("User=luke", unit)
        self.assertIn("Group=luke", unit)
        self.assertIn("EnvironmentFile=/etc/telegram-llm/telegram-llm.env", unit)
        self.assertIn("EnvironmentFile=/etc/telegram-llm/revision.env", unit)
        self.assertIn("StateDirectory=telegram-llm", unit)
        self.assertIn("StateDirectoryMode=0700", unit)
        self.assertIn("ExecStartPre=", unit)
        self.assertIn("--host 127.0.0.1 --port 8787 --workers 1", unit)
        self.assertNotIn("0.0.0.0", unit)
        self.assertNotIn("--port 8765", unit)
        self.assertNotIn("--port 8766", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("ProtectHome=true", unit)
        self.assertIn("ProtectSystem=full", unit)

    def test_prepare_only_cannot_switch_active_release(self):
        source = (DEPLOY / "install_pi.sh").read_text(encoding="utf-8")
        prepare_exit = source.index('if [[ "$MODE" == "prepare" ]]')
        current_switch = source.index('NEXT_LINK="$APP_ROOT/.current-')
        unit_install = source.index('install -m 0644 "$RELEASE_DIR/deploy/systemd/telegram-llm.service" "$UNIT_DEST"')
        self.assertLess(prepare_exit, current_switch)
        self.assertLess(prepare_exit, unit_install)
        self.assertIn('[[ "$BRANCH" == "main" ]]', source)
        self.assertIn('git status --porcelain --untracked-files=normal', source)
        self.assertIn('git archive "$EXPECTED_SHA"', source)
        self.assertIn('VERIFY_UNIT="$(mktemp /run/telegram-llm-verify.', source)
        self.assertIn('s#/opt/telegram-llm/current#$RELEASE_DIR#g', source)
        self.assertIn('systemd-analyze verify "$VERIFY_UNIT"', source)

    def test_activation_requires_secret_file_metadata_and_exact_health(self):
        source = (DEPLOY / "install_pi.sh").read_text(encoding="utf-8")
        self.assertIn('root:$SERVICE_GROUP:640', source)
        self.assertIn('TCP port $PORT is already in use before activation', source)
        self.assertIn('value.get("revision") != expected', source)
        self.assertIn('value.get("storage") != "ok"', source)
        self.assertIn('systemd-analyze verify "$UNIT_DEST"', source)
        self.assertNotIn("set -x", source)

    def test_activation_failure_restores_preexisting_or_first_install_state(self):
        source = (DEPLOY / "install_pi.sh").read_text(encoding="utf-8")
        capture_pos = source.index('PREVIOUS_CURRENT_TARGET=""')
        trap_pos = source.index('trap activation_exit EXIT')
        switch_pos = source.index('NEXT_LINK="$APP_ROOT/.current-')
        self.assertLess(capture_pos, trap_pos)
        self.assertLess(trap_pos, switch_pos)
        self.assertIn('PREVIOUS_ENABLED=false', source)
        self.assertIn('PREVIOUS_ACTIVE=false', source)
        self.assertIn('trap cleanup_backups EXIT', source)
        self.assertIn('restore_previous_activation()', source)
        self.assertIn('if [[ -n "$PREVIOUS_CURRENT_TARGET" ]]', source)
        self.assertIn('rm -f -- "$CURRENT_LINK"', source)
        self.assertIn('cp -p -- "$PREVIOUS_REVISION_BACKUP" "$REVISION_ENV"', source)
        self.assertIn('rm -f -- "$REVISION_ENV"', source)
        self.assertIn('cp -p -- "$PREVIOUS_UNIT_BACKUP" "$UNIT_DEST"', source)
        self.assertIn('rm -f -- "$UNIT_DEST"', source)
        self.assertIn('cmp -s "$PREVIOUS_REVISION_BACKUP" "$REVISION_ENV"', source)
        self.assertIn('cmp -s "$PREVIOUS_UNIT_BACKUP" "$UNIT_DEST"', source)
        self.assertIn('systemctl is-enabled --quiet "$SERVICE"', source)
        self.assertIn('systemctl is-active --quiet "$SERVICE"', source)
        self.assertIn('systemctl start "$SERVICE"', source)
        self.assertIn('systemctl stop "$SERVICE"', source)
        self.assertIn('health_json="$(curl --fail', source)
        self.assertIn('ACTIVATION_ROLLBACK=COMPLETE', source)
        self.assertIn('ACTIVATION_ROLLBACK=FAILED', source)
        self.assertIn('TRANSACTION_ACTIVE=false', source)

    def test_rollback_can_recover_when_current_path_is_broken(self):
        source = (DEPLOY / "rollback_pi.sh").read_text(encoding="utf-8")
        self.assertIn('TARGET_RELEASE="$APP_ROOT/releases/$TARGET_SHA"', source)
        self.assertIn('.source-revision', source)
        verify_pos = source.index('systemd-analyze verify "$VERIFY_UNIT"')
        switch_pos = source.index('NEXT_LINK="$APP_ROOT/.rollback-')
        self.assertLess(verify_pos, switch_pos)
        self.assertIn('s#/opt/telegram-llm/current#$TARGET_RELEASE#g', source)
        self.assertIn('value.get("revision") != expected', source)

    def test_local_qualification_checks_exact_runtime_identity(self):
        source = (DEPLOY / "qualify_pi.sh").read_text(encoding="utf-8")
        self.assertIn('[[ "$(hostname)" == "pi-guy" ]]', source)
        self.assertIn('systemctl is-enabled --quiet "$SERVICE"', source)
        self.assertIn('systemctl is-active --quiet "$SERVICE"', source)
        self.assertIn('127.0.0.1:$PORT', source)
        self.assertIn('LOCAL_PI_QUALIFICATION=PASS', source)
        self.assertIn('root:luke:640', source)
        self.assertIn('luke:luke:700', source)

    def test_openai_sdk_is_pinned(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("openai==3.8.0", requirements)
        self.assertNotIn("openai", requirements)

    def test_preflight_accepts_valid_environment_without_secret_values_in_errors(self):
        preflight = _load_preflight_module()
        with tempfile.TemporaryDirectory() as tmp:
            database_path = str(pathlib.Path(tmp) / "telegram-llm.sqlite3")
            env = {
                "TELEGRAM_TOKEN": "telegram-secret-value",
                "TELEGRAM_ALLOWED_USER_ID": "123456789",
                "WEBHOOK_BASE_URL": "https://relay.example.com",
                "WEBHOOK_SECRET_TOKEN": "webhook-secret-value",
                "OPENAI_API_KEY": "openai-secret-value",
                "APP_REVISION": "a" * 40,
                "DATABASE_PATH": database_path,
            }
            errors = preflight.validate_environment(
                env,
                expected_database_path=database_path,
            )
        self.assertEqual(errors, [])
        joined = " ".join(errors)
        self.assertNotIn("telegram-secret-value", joined)
        self.assertNotIn("webhook-secret-value", joined)
        self.assertNotIn("openai-secret-value", joined)

    def test_preflight_rejects_insecure_or_ambiguous_runtime_identity(self):
        preflight = _load_preflight_module()
        env = {
            "TELEGRAM_TOKEN": "",
            "TELEGRAM_ALLOWED_USER_ID": "0",
            "WEBHOOK_BASE_URL": "http://relay.example.com/",
            "WEBHOOK_SECRET_TOKEN": "",
            "OPENAI_API_KEY": "",
            "APP_REVISION": "unknown",
            "DATABASE_PATH": "relative.sqlite3",
        }
        errors = preflight.validate_environment(env)
        joined = " | ".join(errors)
        self.assertIn("TELEGRAM_TOKEN is required", joined)
        self.assertIn("TELEGRAM_ALLOWED_USER_ID must be a positive integer", joined)
        self.assertIn("WEBHOOK_BASE_URL must be an absolute HTTPS URL", joined)
        self.assertIn("WEBHOOK_BASE_URL must be an origin only, without a path", joined)
        self.assertIn("WEBHOOK_BASE_URL must not end with a slash", joined)
        self.assertIn("APP_REVISION must be a full 40-character lowercase Git SHA", joined)
        self.assertIn("DATABASE_PATH must be exactly /var/lib/telegram-llm/telegram-llm.sqlite3", joined)

    def test_preflight_rejects_secret_file_database_override_and_bad_url_components(self):
        preflight = _load_preflight_module()
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "TELEGRAM_TOKEN": "token",
                "TELEGRAM_ALLOWED_USER_ID": "123",
                "WEBHOOK_BASE_URL": "https://user:pass@relay.example.com/base?x=1#fragment",
                "WEBHOOK_SECRET_TOKEN": "secret",
                "OPENAI_API_KEY": "key",
                "APP_REVISION": "A" * 40,
                "DATABASE_PATH": str(pathlib.Path(tmp) / "override.sqlite3"),
            }
            errors = preflight.validate_environment(env)
        joined = " | ".join(errors)
        self.assertIn("WEBHOOK_BASE_URL must not embed credentials", joined)
        self.assertIn("WEBHOOK_BASE_URL must be an origin only, without a path", joined)
        self.assertIn("WEBHOOK_BASE_URL must not contain a query or fragment", joined)
        self.assertIn("APP_REVISION must be a full 40-character lowercase Git SHA", joined)
        self.assertIn("DATABASE_PATH must be exactly /var/lib/telegram-llm/telegram-llm.sqlite3", joined)


if __name__ == "__main__":
    unittest.main()
