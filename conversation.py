from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from storage import SQLiteConversationStore

logger = logging.getLogger(__name__)

AgentRunner = Callable[
    [str, list[tuple[str, str]], str],
    Awaitable[tuple[str, str | None, list[dict[str, Any]]]],
]
CommandRunner = Callable[[str], Awaitable[str | tuple[str, list[dict[str, Any]]]]]
Summarizer = Callable[[str, list[tuple[str, str]]], Awaitable[str]]


@dataclass(slots=True)
class ConversationReply:
    text: str
    model: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)


class ConversationService:
    """Transport-neutral durable conversation orchestration."""

    def __init__(
        self,
        agent_runner: AgentRunner,
        commands: Mapping[str, CommandRunner],
        store: SQLiteConversationStore,
        summarizer: Summarizer,
        recent_context_items: int = 12,
        compact_after_items: int = 24,
    ) -> None:
        if recent_context_items < 2:
            raise ValueError("recent_context_items must be at least 2")
        if compact_after_items <= recent_context_items:
            raise ValueError("compact_after_items must exceed recent_context_items")
        self._agent_runner = agent_runner
        self._commands = dict(commands)
        self._store = store
        self._summarizer = summarizer
        self._recent_context_items = recent_context_items
        self._compact_after_items = compact_after_items
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, conversation_id: str) -> asyncio.Lock:
        if conversation_id not in self._locks:
            self._locks[conversation_id] = asyncio.Lock()
        return self._locks[conversation_id]

    def history(self, conversation_id: str) -> list[tuple[str, str]]:
        return [(m.role, m.content) for m in self._store.all_messages(conversation_id)]

    def clear(self, conversation_id: str) -> None:
        self._store.clear(conversation_id)

    def context(self, conversation_id: str) -> tuple[str, list[tuple[str, str]]]:
        summary, through_id = self._store.state(conversation_id)
        pending = self._store.messages_after(conversation_id, through_id)
        if len(pending) <= self._compact_after_items:
            selected = pending
        else:
            # A failed/overdue compaction must not make model context unbounded.
            selected = pending[-self._recent_context_items :]
        return summary, [(m.role, m.content) for m in selected]

    async def respond(self, conversation_id: str, text: str) -> ConversationReply:
        async with self._lock(conversation_id):
            summary, history = self.context(conversation_id)
            answer, model, attachments = await self._agent_runner(text, history, summary)
            self._store.append_message(conversation_id, "user", text)
            self._store.append_message(conversation_id, "assistant", answer)
            await self._compact_if_needed(conversation_id)
            return ConversationReply(answer, model, list(attachments))

    async def run_command(
        self,
        conversation_id: str,
        raw_text: str,
        command: str,
        args: str,
    ) -> ConversationReply | None:
        fn = self._commands.get(command)
        if fn is None:
            return None

        async with self._lock(conversation_id):
            result = await fn(args)
            if isinstance(result, tuple):
                answer, attachments = result
            else:
                answer, attachments = result, []

            self._store.append_message(conversation_id, "user", raw_text)
            if answer:
                self._store.append_message(conversation_id, "assistant", answer)
            await self._compact_if_needed(conversation_id)
            return ConversationReply(answer, None, list(attachments))

    async def _compact_if_needed(self, conversation_id: str) -> None:
        prior_summary, through_id = self._store.state(conversation_id)
        pending = self._store.messages_after(conversation_id, through_id)
        if len(pending) <= self._compact_after_items:
            return

        compactable = pending[: -self._recent_context_items]
        if not compactable:
            return

        try:
            summary = await self._summarizer(
                prior_summary,
                [(m.role, m.content) for m in compactable],
            )
        except Exception:
            logger.exception("Conversation compaction failed for %s", conversation_id)
            return

        summary = summary.strip()
        if not summary:
            logger.warning("Conversation compaction returned an empty summary for %s", conversation_id)
            return

        self._store.set_summary(conversation_id, summary, compactable[-1].id)
