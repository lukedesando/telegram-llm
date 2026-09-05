import asyncio
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from conversation import ConversationService


class ConversationServiceTests(unittest.TestCase):
    def test_agent_receives_prior_history(self):
        seen = []

        async def fake_agent(text, history):
            seen.append((text, list(history)))
            return f"reply:{text}", "fake", []

        service = ConversationService(fake_agent, {})
        asyncio.run(service.respond("telegram:1", "first"))
        asyncio.run(service.respond("telegram:1", "second"))

        self.assertEqual(seen[0][1], [])
        self.assertEqual(
            seen[1][1],
            [("user", "first"), ("assistant", "reply:first")],
        )

    def test_clear_removes_history(self):
        async def fake_agent(text, history):
            return "ok", "fake", []

        service = ConversationService(fake_agent, {})
        asyncio.run(service.respond("telegram:1", "hello"))
        self.assertTrue(service.history("telegram:1"))
        service.clear("telegram:1")
        self.assertEqual(service.history("telegram:1"), [])

    def test_command_uses_same_conversation_history(self):
        async def fake_agent(text, history):
            return "ok", "fake", []

        async def fake_command(args):
            return f"weather:{args}"

        service = ConversationService(fake_agent, {"weather": fake_command})
        reply = asyncio.run(
            service.run_command("telegram:1", "/weather Rome", "weather", "Rome")
        )

        self.assertEqual(reply.text, "weather:Rome")
        self.assertEqual(
            service.history("telegram:1"),
            [("user", "/weather Rome"), ("assistant", "weather:Rome")],
        )

    def test_history_is_bounded(self):
        async def fake_agent(text, history):
            return f"reply:{text}", "fake", []

        service = ConversationService(fake_agent, {}, max_history_items=4)
        for text in ("one", "two", "three"):
            asyncio.run(service.respond("telegram:1", text))

        self.assertEqual(
            service.history("telegram:1"),
            [
                ("user", "two"),
                ("assistant", "reply:two"),
                ("user", "three"),
                ("assistant", "reply:three"),
            ],
        )

    def test_conversation_core_has_no_telegram_dependency(self):
        source = (ROOT / "conversation.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("from telegram", source)
        self.assertNotIn("import telegram", source)


if __name__ == "__main__":
    unittest.main()
