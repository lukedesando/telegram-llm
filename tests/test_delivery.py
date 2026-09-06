import asyncio
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from delivery import UpdateDeduplicator


class FakeStore:
    def __init__(self):
        self.claimed = set()
        self.completed = set()
        self.released = set()

    def claim_update(self, update_id, stale_after_seconds):
        if update_id in self.completed or update_id in self.claimed:
            return False
        self.claimed.add(update_id)
        return True

    def complete_update(self, update_id):
        self.claimed.discard(update_id)
        self.completed.add(update_id)

    def release_update(self, update_id):
        self.claimed.discard(update_id)
        self.released.add(update_id)


class UpdateDeduplicatorTests(unittest.TestCase):
    def test_completed_update_is_not_run_twice(self):
        store = FakeStore()
        dedupe = UpdateDeduplicator(store)
        calls = []

        async def action():
            calls.append("ran")

        self.assertTrue(asyncio.run(dedupe.run(10, action)))
        self.assertFalse(asyncio.run(dedupe.run(10, action)))
        self.assertEqual(calls, ["ran"])
        self.assertIn(10, store.completed)

    def test_failure_releases_update_for_retry(self):
        store = FakeStore()
        dedupe = UpdateDeduplicator(store)

        async def failing_action():
            raise RuntimeError("boom")

        with self.assertRaisesRegex(RuntimeError, "boom"):
            asyncio.run(dedupe.run(11, failing_action))

        self.assertIn(11, store.released)
        self.assertNotIn(11, store.claimed)

        calls = []

        async def retry_action():
            calls.append("retried")

        self.assertTrue(asyncio.run(dedupe.run(11, retry_action)))
        self.assertEqual(calls, ["retried"])

    def test_missing_update_id_runs_without_bookkeeping(self):
        store = FakeStore()
        dedupe = UpdateDeduplicator(store)
        calls = []

        async def action():
            calls.append("ran")

        self.assertTrue(asyncio.run(dedupe.run(None, action)))
        self.assertEqual(calls, ["ran"])
        self.assertEqual(store.claimed, set())
        self.assertEqual(store.completed, set())

    def test_negative_lease_window_is_rejected(self):
        with self.assertRaises(ValueError):
            UpdateDeduplicator(FakeStore(), stale_after_seconds=-1)


if __name__ == "__main__":
    unittest.main()
