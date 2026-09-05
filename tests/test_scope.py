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

    def test_deferred_tools_are_not_in_agent(self):
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

    def test_openai_is_the_only_model_provider(self):
        agent_source = (ROOT / "agent.py").read_text(encoding="utf-8").lower()
        config_source = (ROOT / "config.py").read_text(encoding="utf-8").lower()
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()

        self.assertIn("openaiprovider", agent_source)
        self.assertIn("openai_api_key", config_source)
        self.assertIn("openai", requirements)

        for forbidden in ("anthropic", "gemini", "google-genai", "xai_api_key", "claude"):
            self.assertNotIn(forbidden, agent_source)
            self.assertNotIn(forbidden, config_source)
            self.assertNotIn(forbidden, requirements)

    def test_removed_provider_fetch_tool_is_absent(self):
        self.assertFalse((ROOT / "tools" / "fetch.py").exists())


if __name__ == "__main__":
    unittest.main()
