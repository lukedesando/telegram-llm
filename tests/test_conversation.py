import asyncio
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from conversation import ConversationService
from storage import SQLiteConversationStore


class ConversationServiceTests(unittest.TestCase):
    def _store(self, directory: str) -> SQLiteConversationStore:
        return SQLiteConversationStore(str(pathlib.Path(directory) / "test.sqlite3"))

    def test_agent_receives_persisted_history_after_restart(self):
        seen = []

        async def fake_agent(text, history, summary):
            seen.append((text, list(history), summary))
            return f"reply:{text}", "fake", []

        async def fake_summarizer(prior, messages):
            return prior

        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            first = ConversationService(fake_agent, {}, store, fake_summarizer)
            asyncio.run(first.respond("telegram:1", "first"))

            reopened = self._store(tmp)
            second = ConversationService(fake_agent, {}, reopened, fake_summarizer)
            asyncio.run(second.respond("telegram:1", "second"))

        self.assertEqual(seen[0][1], [])
        self.assertEqual(
            seen[1][1],
            [("user", "first"), ("assistant", "reply:first")],
        )
        self.assertEqual(seen[1][2], "")

    def test_compaction_preserves_raw_history_and_supplies_summary(self):
        seen = []
        summaries = []

        async def fake_agent(text, history, summary):
            seen.append((text, list(history), summary))
            return f"reply:{text}", "fake", []

        async def fake_summarizer(prior, messages):
            summaries.append((prior, list(messages)))
            return "summary-of-old-turns"

        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            service = ConversationService(
                fake_agent,
                {},
                store,
                fake_summarizer,
                recent_context_items=2,
                compact_after_items=4,
            )
            for text in ("one", "two", "three"):
                asyncio.run(service.respond("telegram:1", text))

            self.assertEqual(len(store.all_messages("telegram:1")), 6)
            summary, recent = service.context("telegram:1")

        self.assertEqual(summary, "summary-of-old-turns")
        self.assertEqual(
            recent,
            [("user", "three"), ("assistant", "reply:three")],
        )
        self.assertEqual(
            summaries[0][1],
            [
                ("user", "one"),
                ("assistant", "reply:one"),
                ("user", "two"),
                ("assistant", "reply:two"),
            ],
        )

    def test_compaction_failure_does_not_lose_messages(self):
        async def fake_agent(text, history, summary):
            return f"reply:{text}", "fake", []

        async def failing_summarizer(prior, messages):
            raise RuntimeError("summary unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            service = ConversationService(
                fake_agent,
                {},
                store,
                failing_summarizer,
                recent_context_items=2,
                compact_after_items=4,
            )
            for text in ("one", "two", "three"):
                asyncio.run(service.respond("telegram:1", text))

            self.assertEqual(len(store.all_messages("telegram:1")), 6)
            summary, recent = service.context("telegram:1")

        self.assertEqual(summary, "")
        self.assertEqual(len(recent), 2)

    def test_clear_removes_persisted_state(self):
        async def fake_agent(text, history, summary):
            return "ok", "fake", []

        async def fake_summarizer(prior, messages):
            return prior

        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            service = ConversationService(fake_agent, {}, store, fake_summarizer)
            asyncio.run(service.respond("telegram:1", "hello"))
            self.assertTrue(service.history("telegram:1"))
            service.clear("telegram:1")
            self.assertEqual(service.history("telegram:1"), [])
            self.assertEqual(store.state("telegram:1"), ("", 0))

    def test_command_uses_same_persistent_history(self):
        async def fake_agent(text, history, summary):
            return "ok", "fake", []

        async def fake_command(args):
            return f"weather:{args}"

        async def fake_summarizer(prior, messages):
            return prior

        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            service = ConversationService(
                fake_agent,
                {"weather": fake_command},
                store,
                fake_summarizer,
            )
            reply = asyncio.run(
                service.run_command("telegram:1", "/weather Rome", "weather", "Rome")
            )

            self.assertEqual(reply.text, "weather:Rome")
            self.assertEqual(
                service.history("telegram:1"),
                [("user", "/weather Rome"), ("assistant", "weather:Rome")],
            )


if __name__ == "__main__":
    unittest.main()
