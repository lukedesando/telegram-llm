import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from storage import SQLiteConversationStore


class SQLiteConversationStoreTests(unittest.TestCase):
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
            store = SQLiteConversationStore(str(pathlib.Path(tmp) / "conversation.sqlite3"))
            first_id = store.append_message("telegram:1", "user", "one")
            second_id = store.append_message("telegram:1", "assistant", "two")
            store.set_summary("telegram:1", "compact memory", second_id)

            self.assertEqual(store.state("telegram:1"), ("compact memory", second_id))
            self.assertEqual(len(store.all_messages("telegram:1")), 2)
            self.assertEqual(store.messages_after("telegram:1", second_id), [])
            self.assertLess(first_id, second_id)

    def test_clear_removes_messages_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteConversationStore(str(pathlib.Path(tmp) / "conversation.sqlite3"))
            message_id = store.append_message("telegram:1", "user", "hello")
            store.set_summary("telegram:1", "memory", message_id)

            store.clear("telegram:1")

            self.assertEqual(store.all_messages("telegram:1"), [])
            self.assertEqual(store.state("telegram:1"), ("", 0))


if __name__ == "__main__":
    unittest.main()
