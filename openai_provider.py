from __future__ import annotations

from typing import Any, Literal

try:
    from openai import AsyncOpenAI
except ImportError:  # Allows credential-free unit tests with an injected client.
    AsyncOpenAI = None  # type: ignore[assignment]

WebSearchMode = Literal["auto", "required", "off"]


class OpenAIProvider:
    """Small Responses API boundary with injectable client for offline tests."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        reasoning_effort: str,
        max_output_tokens: int,
        max_response_chars: int,
        web_search_context_size: str = "medium",
        timeout_seconds: float = 45.0,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.max_response_chars = max_response_chars
        self.web_search_context_size = web_search_context_size

        if client is not None:
            self.client = client
        else:
            if AsyncOpenAI is None:
                raise RuntimeError("The openai package is required at runtime")
            self.client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)

    async def generate(
        self,
        *,
        user_message: str,
        history: list[tuple[str, str]] | None = None,
        instructions: str,
        web_search: WebSearchMode = "auto",
        reasoning_effort: str | None = None,
        max_output_tokens: int | None = None,
        max_chars: int | None = None,
    ) -> str:
        input_items = [
            {"role": role, "content": text}
            for role, text in (history or [])
        ]
        input_items.append({"role": "user", "content": user_message})

        request: dict[str, Any] = {
            "model": self.model,
            "instructions": instructions,
            "input": input_items,
            "reasoning": {"effort": reasoning_effort or self.reasoning_effort},
            "text": {"verbosity": "low"},
            "max_output_tokens": max_output_tokens or self.max_output_tokens,
            "store": False,
        }

        if web_search != "off":
            request["tools"] = [
                {
                    "type": "web_search",
                    "search_context_size": self.web_search_context_size,
                }
            ]
            if web_search == "required":
                request["tool_choice"] = {"type": "web_search"}

        response = await self.client.responses.create(**request)
        text = (getattr(response, "output_text", "") or "").strip()
        if not text:
            raise RuntimeError("OpenAI returned no text output")
        return self._truncate(text, max_chars or self.max_response_chars)

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        if limit < 1:
            raise ValueError("limit must be positive")
        if len(text) <= limit:
            return text
        if limit == 1:
            return "…"
        body_limit = limit - 1
        shortened = text[:body_limit].rsplit(" ", 1)[0]
        return (shortened or text[:body_limit]) + "…"
