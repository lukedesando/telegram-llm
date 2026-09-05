from __future__ import annotations

from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

AgentRunner = Callable[[str, list[tuple[str, str]]], Awaitable[tuple[str, str | None, list[dict[str, Any]]]]]
CommandRunner = Callable[[str], Awaitable[str | tuple[str, list[dict[str, Any]]]]]


@dataclass(slots=True)
class ConversationReply:
    text: str
    model: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)


class ConversationService:
    """Transport-neutral conversation state and agent/command orchestration."""

    def __init__(
        self,
        agent_runner: AgentRunner,
        commands: Mapping[str, CommandRunner],
        max_history_items: int = 12,
    ) -> None:
        if max_history_items < 2:
            raise ValueError("max_history_items must be at least 2")
        self._agent_runner = agent_runner
        self._commands = dict(commands)
        self._max_history_items = max_history_items
        self._history: dict[str, deque[tuple[str, str]]] = {}

    def _get_history(self, conversation_id: str) -> deque[tuple[str, str]]:
        if conversation_id not in self._history:
            self._history[conversation_id] = deque(maxlen=self._max_history_items)
        return self._history[conversation_id]

    def history(self, conversation_id: str) -> list[tuple[str, str]]:
        return list(self._get_history(conversation_id))

    def clear(self, conversation_id: str) -> None:
        self._history.pop(conversation_id, None)

    async def respond(self, conversation_id: str, text: str) -> ConversationReply:
        history = self._get_history(conversation_id)
        answer, model, attachments = await self._agent_runner(text, list(history))
        history.append(("user", text))
        history.append(("assistant", answer))
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

        result = await fn(args)
        if isinstance(result, tuple):
            answer, attachments = result
        else:
            answer, attachments = result, []

        history = self._get_history(conversation_id)
        history.append(("user", raw_text))
        if answer:
            history.append(("assistant", answer))

        return ConversationReply(answer, None, list(attachments))
