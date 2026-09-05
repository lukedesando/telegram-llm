import asyncio
import pathlib
import sys
import unittest
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openai_provider import OpenAIProvider


class FakeResponses:
    def __init__(self, output_text="ok"):
        self.output_text = output_text
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text)


class FakeClient:
    def __init__(self, output_text="ok"):
        self.responses = FakeResponses(output_text)


class OpenAIProviderTests(unittest.TestCase):
    def _provider(self, client):
        return OpenAIProvider(
            api_key="unused",
            model="gpt-5.6-terra",
            reasoning_effort="low",
            max_output_tokens=1800,
            max_response_chars=3500,
            web_search_context_size="medium",
            client=client,
        )

    def test_auto_search_request_shape(self):
        client = FakeClient("answer")
        provider = self._provider(client)

        answer = asyncio.run(
            provider.generate(
                user_message="latest status",
                history=[("user", "first"), ("assistant", "second")],
                instructions="system rules",
                web_search="auto",
            )
        )

        self.assertEqual(answer, "answer")
        request = client.responses.calls[0]
        self.assertEqual(request["model"], "gpt-5.6-terra")
        self.assertEqual(request["reasoning"], {"effort": "low"})
        self.assertEqual(request["text"], {"verbosity": "low"})
        self.assertFalse(request["store"])
        self.assertEqual(
            request["tools"],
            [{"type": "web_search", "search_context_size": "medium"}],
        )
        self.assertNotIn("tool_choice", request)
        self.assertEqual(
            request["input"],
            [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "second"},
                {"role": "user", "content": "latest status"},
            ],
        )

    def test_required_search_forces_web_search(self):
        client = FakeClient()
        provider = self._provider(client)

        asyncio.run(
            provider.generate(
                user_message="news",
                instructions="rules",
                web_search="required",
            )
        )

        request = client.responses.calls[0]
        self.assertEqual(request["tool_choice"], {"type": "web_search"})
        self.assertEqual(request["tools"][0]["type"], "web_search")

    def test_search_off_omits_tools_and_allows_summary_overrides(self):
        client = FakeClient("abcdefghijk")
        provider = self._provider(client)

        answer = asyncio.run(
            provider.generate(
                user_message="summarize",
                instructions="memory",
                web_search="off",
                reasoning_effort="none",
                max_output_tokens=1200,
                max_chars=6,
            )
        )

        request = client.responses.calls[0]
        self.assertNotIn("tools", request)
        self.assertNotIn("tool_choice", request)
        self.assertEqual(request["reasoning"], {"effort": "none"})
        self.assertEqual(request["max_output_tokens"], 1200)
        self.assertEqual(answer, "abcde…")

    def test_empty_output_fails(self):
        provider = self._provider(FakeClient("   "))
        with self.assertRaisesRegex(RuntimeError, "no text output"):
            asyncio.run(
                provider.generate(
                    user_message="hello",
                    instructions="rules",
                    web_search="off",
                )
            )


if __name__ == "__main__":
    unittest.main()
