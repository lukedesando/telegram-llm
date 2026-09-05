import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FlightScopeTests(unittest.TestCase):
    def test_command_surface_is_bounded(self):
        tree = ast.parse((ROOT / "agent.py").read_text(encoding="utf-8"))
        command_keys = None
        for node in tree.body:
            if isinstance(node, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == "COMMANDS" for t in node.targets):
                    command_keys = {
                        key.value
                        for key in node.value.keys
                        if isinstance(key, ast.Constant) and isinstance(key.value, str)
                    }
                    break
        self.assertEqual(command_keys, {"weather", "flight", "news", "search", "pdf"})

    def test_grok_and_deferred_tools_are_not_in_agent(self):
        source = (ROOT / "agent.py").read_text(encoding="utf-8").lower()
        for forbidden in (
            "grok",
            "xai",
            "cmd_stocks",
            "cmd_image",
            "cmd_sports",
            "cmd_tr",
            "cmd_retrieve",
        ):
            self.assertNotIn(forbidden, source)

    def test_config_does_not_require_removed_provider_keys(self):
        source = (ROOT / "config.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("xai_api_key", source)
        self.assertNotIn("google_cse", source)


if __name__ == "__main__":
    unittest.main()
