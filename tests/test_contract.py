import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_main_keeps_health_and_webhook_routes(self):
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        routes = set()
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                    if decorator.args and isinstance(decorator.args[0], ast.Constant):
                        routes.add((decorator.func.attr, decorator.args[0].value))
        self.assertIn(("post", "/webhook"), routes)
        self.assertIn(("get", "/health"), routes)

    def test_webhook_secret_header_remains_checked_constant_time(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("x_telegram_bot_api_secret_token", source)
        self.assertIn("webhook_secret_token", source)
        self.assertIn("secrets.compare_digest", source)
        self.assertIn("status_code=403", source)

    def test_public_host_is_guarded_before_routes(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn('@app.middleware("http")', source)
        self.assertIn("public_surface_allows", source)
        self.assertIn("request.headers.get(\"host\", \"\")", source)
        self.assertIn("status_code=404", source)

    def test_health_checks_storage_and_can_fail_degraded(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("conversation_store.ping()", source)
        self.assertIn("status_code=200 if storage_ok else 503", source)
        self.assertIn("settings.app_revision", source)

    def test_operator_commands_are_registered(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn('CommandHandler("new", handle_new)', source)
        self.assertIn('CommandHandler("status", handle_status)', source)
        self.assertIn("UpdateDeduplicator", source)


if __name__ == "__main__":
    unittest.main()
