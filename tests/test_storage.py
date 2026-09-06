import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from storage import SQLiteConversationStore


class SQLiteConversationStoreTests(unittest.TestCase):
    def _store(self, tmp: str) -> SQLiteConversationStore:
        return SQLiteConversationStore(str(pathlib.Path(tmp) / "conversation.sqlite3"))

    def test_messages_survive_store_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(pathlib.Path(tmp) / "conversation.sqlite3")
            first = SQLiteConversationStore(path)
            first.append_message("telegram:1", "user", "hello")
            first.append_message("telegram:1", "assistant", "hi")

            reopened = SQLiteConversationStore(path)
            messages = reopened.all_messages("telegram:1")

        self.assertEqual(
            [(m.role, m.content) for m in messages],
            [("user", "hello"), ("assistant", "hi")],
        )

    def test_summary_pointer_does_not_delete_raw_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            first_id = store.append_message("telegram:1", "user", "one")
            second_id = store.append_message("telegram:1", "assistant", "two")
            store.set_summary("telegram:1", "compact memory", second_id)

            self.assertEqual(store.state("telegram:1"), ("compact memory", second_id))
            self.assertEqual(len(store.all_messages("telegram:1")), 2)
            self.assertEqual(store.messages_after("telegram:1", second_id), [])
            self.assertLess(first_id, second_id)

    def test_clear_removes_messages_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            message_id = store.append_message("telegram:1", "user", "hello")
            store.set_summary("telegram:1", "memory", message_id)

            store.clear("telegram:1")

            self.assertEqual(store.all_messages("telegram:1"), [])
            self.assertEqual(store.state("telegram:1"), ("", 0))

    def test_ping_and_conversation_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            first_id = store.append_message("telegram:1", "user", "one")
            store.append_message("telegram:1", "assistant", "two")
            store.append_message("telegram:1", "user", "three")
            store.set_summary("telegram:1", "memory", first_id)

            stats = store.conversation_stats("telegram:1")

            self.assertTrue(store.ping())
            self.assertEqual(stats.message_count, 3)
            self.assertTrue(stats.summary_present)
            self.assertEqual(stats.pending_message_count, 2)

    def test_update_claim_completion_survives_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            self.assertTrue(store.claim_update(101))
            self.assertFalse(store.claim_update(101))
            store.complete_update(101)

            reopened = self._store(tmp)
            self.assertFalse(reopened.claim_update(101, stale_after_seconds=0))

    def test_release_allows_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            self.assertTrue(store.claim_update(102))
            store.release_update(102)
            self.assertTrue(store.claim_update(102))

    def test_stale_processing_lease_can_be_reclaimed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            self.assertTrue(store.claim_update(103))
            self.assertTrue(store.claim_update(103, stale_after_seconds=0))

    def test_negative_stale_window_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            with self.assertRaises(ValueError):
                store.claim_update(104, stale_after_seconds=-1)


if __name__ == "__main__":
    unittest.main()
