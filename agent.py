import logging
from datetime import date

import anthropic
from google import genai
from google.genai import types as gtypes

from config import settings
from tools.fetch import SCHEMA as FETCH_SCHEMA, fetch_url
from tools.pdf import SCHEMA as PDF_SCHEMA, fetch_pdf, fetch_pdf_bytes
from tools.weather import get_weather

logger = logging.getLogger(__name__)

TOOL_DISPATCH = {
    "fetch_url": lambda inp: fetch_url(inp["url"]),
    "fetch_pdf": lambda inp: fetch_pdf(inp["url"]),
}

_FETCH_HINTS = (
    "http://",
    "https://",
    ".pdf",
    "site",
    "page",
    "article",
    "link",
    "url",
)


def _needs_fetch(message: str, history: list) -> bool:
    combined = message.lower() + " " + " ".join(text for _, text in history).lower()
    return any(hint in combined for hint in _FETCH_HINTS)


def _system_prompt(context_summary: str = "") -> str:
    today = date.today().strftime("%B %d, %Y")
    prompt = f"""You are a concise assistant used through Telegram.
Today's date is {today}.
The user may be on constrained inflight Wi-Fi, so answer directly and keep responses compact.
Use web search for current factual questions. For direct URLs, fetch the source before summarizing it. For PDFs, fetch and read the PDF rather than relying on search snippets.
Keep normal responses under {settings.max_response_chars} characters unless the request requires more detail."""
    if context_summary.strip():
        prompt += f"\n\nEarlier conversation summary:\n{context_summary.strip()}"
    return prompt


_gemini = genai.Client(api_key=settings.gemini_api_key)
_gemini_models = [m.strip() for m in settings.gemini_models.split(",") if m.strip()]
_gemini_tools = [gtypes.Tool(google_search=gtypes.GoogleSearch())]
_claude = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def _run_gemini(
    user_message: str,
    history: list,
    context_summary: str = "",
) -> tuple[str, str]:
    contents = []
    for role, text in history:
        contents.append(
            gtypes.Content(
                role="model" if role == "assistant" else "user",
                parts=[gtypes.Part(text=text)],
            )
        )
    contents.append(gtypes.Content(role="user", parts=[gtypes.Part(text=user_message)]))

    config = gtypes.GenerateContentConfig(
        tools=_gemini_tools,
        system_instruction=_system_prompt(context_summary),
        max_output_tokens=512,
    )

    last_error = None
    for model in _gemini_models:
        try:
            response = await _gemini.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            text_parts = [
                part.text
                for part in response.candidates[0].content.parts
                if getattr(part, "text", None)
            ]
            return _truncate(" ".join(text_parts).strip() or "No answer found."), model
        except Exception as exc:
            last_error = exc
            logger.warning("Gemini failed on %s: %s", model, str(exc)[:80])

    raise RuntimeError(f"All Gemini models failed: {last_error}")


async def _run_claude(
    user_message: str,
    history: list,
    context_summary: str = "",
) -> tuple[str, str]:
    messages = [{"role": role, "content": text} for role, text in history]
    messages.append({"role": "user", "content": user_message})
    tools = [
        {"type": "web_search_20250305", "name": "web_search"},
        FETCH_SCHEMA,
        PDF_SCHEMA,
    ]

    for iteration in range(settings.max_tool_iterations):
        response = await _claude.messages.create(
            model=settings.claude_model,
            max_tokens=768,
            system=_system_prompt(context_summary),
            tools=tools,
            messages=messages,
        )
        logger.info("Claude stop_reason=%s iter=%d", response.stop_reason, iteration)

        if response.stop_reason == "end_turn":
            text = " ".join(
                block.text for block in response.content if hasattr(block, "text")
            ).strip()
            return _truncate(text or "No answer found."), "claude"

        if response.stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool_fn = TOOL_DISPATCH.get(block.name)
            if tool_fn is None:
                continue
            try:
                result = await tool_fn(block.input)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": str(result)}
                )
            except Exception as exc:
                logger.warning("Tool %s failed: %s", block.name, exc)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Error: {exc}",
                        "is_error": True,
                    }
                )
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    return "Could not complete that request.", "claude"


def _truncate(text: str) -> str:
    if len(text) <= settings.max_response_chars:
        return text
    shortened = text[: settings.max_response_chars].rsplit(" ", 1)[0]
    return (shortened or text[: settings.max_response_chars - 1]) + "…"


async def summarize_history(
    prior_summary: str,
    messages: list[tuple[str, str]],
) -> str:
    transcript = "\n".join(f"{role}: {text}" for role, text in messages)
    prompt = (
        "Update a compact memory of this conversation. Preserve concrete facts, user preferences, "
        "decisions, names, numbers, unresolved questions, and active tasks. Remove repetition and chatter. "
        "Do not invent information. Return only the updated memory.\n\n"
        f"Previous memory:\n{prior_summary or '(none)'}\n\n"
        f"New messages:\n{transcript}"
    )

    last_error = None
    for model in _gemini_models:
        try:
            response = await _gemini.aio.models.generate_content(
                model=model,
                contents=[gtypes.Content(role="user", parts=[gtypes.Part(text=prompt)])],
                config=gtypes.GenerateContentConfig(max_output_tokens=1024),
            )
            text = " ".join(
                part.text
                for part in response.candidates[0].content.parts
                if getattr(part, "text", None)
            ).strip()
            if text:
                return text[: settings.max_summary_chars]
        except Exception as exc:
            last_error = exc
            logger.warning("Gemini summarizer failed on %s: %s", model, str(exc)[:80])

    try:
        response = await _claude.messages.create(
            model=settings.claude_model,
            max_tokens=1024,
            system="Maintain a compact, factual conversation memory. Return only the memory text.",
            messages=[{"role": "user", "content": prompt}],
        )
        text = " ".join(
            block.text for block in response.content if hasattr(block, "text")
        ).strip()
        if text:
            return text[: settings.max_summary_chars]
    except Exception as exc:
        last_error = exc
        logger.warning("Claude summarizer failed: %s", str(exc)[:80])

    raise RuntimeError(f"Conversation summarization failed: {last_error}")


async def cmd_weather(args: str) -> str:
    city = args.strip() or "current location"
    try:
        return await get_weather(city)
    except Exception as exc:
        return f"Weather unavailable: {exc}"


async def cmd_flight(args: str) -> str:
    if not args.strip():
        return "Usage: /flight <number>"
    prompt = (
        f"Current status of flight {args.strip().upper()}. "
        "Give flight number, status, departure airport/time, arrival airport/time, and delay."
    )
    answer, _ = await _run_gemini(prompt, [])
    return answer


async def cmd_news(args: str) -> str:
    topic = args.strip() or "world"
    prompt = f"Top current news about {topic}. Give the most important items concisely."
    try:
        answer, _ = await _run_gemini(prompt, [])
    except Exception:
        answer, _ = await _run_claude(prompt, [])
    return answer


async def cmd_search(args: str) -> str:
    if not args.strip():
        return "Usage: /search <query>"
    prompt = f"Search the web for: {args.strip()}. Answer directly with the most relevant current information."
    try:
        answer, _ = await _run_gemini(prompt, [])
    except Exception:
        answer, _ = await _run_claude(prompt, [])
    return answer


async def cmd_pdf(args: str) -> tuple[str, list]:
    if not args.strip():
        return "Usage: /pdf <url>", []

    url = args.strip()
    attachments = []
    if url.lower().startswith("http") and ".pdf" in url.lower():
        try:
            pdf_bytes, filename = await fetch_pdf_bytes(url)
            if len(pdf_bytes) < 50 * 1024 * 1024:
                attachments.append(
                    {"type": "document", "data": pdf_bytes, "filename": filename}
                )
        except Exception as exc:
            logger.warning("PDF attachment download failed: %s", exc)

    answer, _ = await _run_claude(f"Fetch and summarize this PDF: {url}", [])
    return answer, attachments


COMMANDS = {
    "weather": cmd_weather,
    "flight": cmd_flight,
    "news": cmd_news,
    "search": cmd_search,
    "pdf": cmd_pdf,
}


async def run_agent(
    user_message: str,
    history: list | None = None,
    context_summary: str = "",
) -> tuple[str, str, list]:
    history = history or []
    if _needs_fetch(user_message, history):
        text, model = await _run_claude(user_message, history, context_summary)
        return text, model, []

    try:
        text, model = await _run_gemini(user_message, history, context_summary)
        return text, model, []
    except Exception as exc:
        logger.warning("Gemini failed, falling back to Claude: %s", str(exc)[:80])
        text, model = await _run_claude(user_message, history, context_summary)
        return text, model, []
