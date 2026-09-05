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

    def test_webhook_secret_header_remains_checked(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("x_telegram_bot_api_secret_token", source)
        self.assertIn("webhook_secret_token", source)
        self.assertIn("status_code=403", source)


if __name__ == "__main__":
    unittest.main()
