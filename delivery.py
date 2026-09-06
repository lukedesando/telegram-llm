from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class UpdateDeduplicator:
    """Run a Telegram update at most once unless an abandoned lease expires."""

    def __init__(self, store: Any, stale_after_seconds: int = 300) -> None:
        if stale_after_seconds < 0:
            raise ValueError("stale_after_seconds must be non-negative")
        self._store = store
        self._stale_after_seconds = stale_after_seconds

    async def run(
        self,
        update_id: int | None,
        action: Callable[[], Awaitable[None]],
    ) -> bool:
        if update_id is None:
            await action()
            return True

        if not self._store.claim_update(update_id, self._stale_after_seconds):
            return False

        try:
            await action()
        except BaseException:
            self._store.release_update(update_id)
            raise
        else:
            self._store.complete_update(update_id)
            return True
