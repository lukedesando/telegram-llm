import logging
from datetime import date

from config import settings
from openai_provider import OpenAIProvider
from tools.pdf import fetch_pdf_document
from tools.weather import get_weather

logger = logging.getLogger(__name__)

_provider = OpenAIProvider(
    api_key=settings.openai_api_key,
    model=settings.openai_model,
    reasoning_effort=settings.openai_reasoning_effort,
    max_output_tokens=settings.openai_max_output_tokens,
    max_response_chars=settings.max_response_chars,
    web_search_context_size=settings.web_search_context_size,
    timeout_seconds=settings.openai_timeout_seconds,
)


def _system_prompt(context_summary: str = "") -> str:
    today = date.today().strftime("%B %d, %Y")
    prompt = f"""You are a capable personal assistant used through Telegram.
Today's date is {today}.
The user may be on constrained inflight Wi-Fi. Answer directly, but do not sacrifice important detail merely to be short.
Use web search whenever the answer depends on current, recent, changing, or uncertain external information. Never invent current facts when search is available.
Plain text is preferred. Keep each reply within {settings.max_response_chars} characters so Telegram can deliver it as one message."""
    if context_summary.strip():
        prompt += f"\n\nEarlier conversation summary:\n{context_summary.strip()}"
    return prompt


async def summarize_history(
    prior_summary: str,
    messages: list[tuple[str, str]],
) -> str:
    transcript = "\n".join(f"{role}: {text}" for role, text in messages)
    prompt = (
        "Update the durable memory using the previous memory and new transcript below. "
        "Preserve concrete facts, user preferences, decisions, names, numbers, unresolved questions, "
        "active tasks, and constraints. Remove repetition and transient chatter. Do not invent anything. "
        "Return only the updated memory.\n\n"
        f"Previous memory:\n{prior_summary or '(none)'}\n\n"
        f"New transcript:\n{transcript}"
    )
    return await _provider.generate(
        user_message=prompt,
        history=[],
        instructions="Maintain a compact, factual conversation memory. Return only memory text.",
        web_search="off",
        reasoning_effort="none",
        max_output_tokens=1200,
        max_chars=settings.max_summary_chars,
    )


async def cmd_weather(args: str) -> str:
    city = args.strip()
    if not city:
        return "Usage: /weather <city>"
    try:
        return await get_weather(city)
    except Exception as exc:
        logger.warning("Weather lookup failed: %s", exc)
        return f"Weather unavailable: {str(exc)[:160]}"


async def _web_command(prompt: str) -> str:
    return await _provider.generate(
        user_message=prompt,
        history=[],
        instructions=_system_prompt(),
        web_search="required",
    )


async def cmd_flight(args: str) -> str:
    flight = args.strip().upper()
    if not flight:
        return "Usage: /flight <number>"
    return await _web_command(
        f"Find the current status of flight {flight}. Give status, departure airport and local time, "
        "arrival airport and local time, delay/cancellation information, and the most recent source context."
    )


async def cmd_news(args: str) -> str:
    topic = args.strip() or "world"
    return await _web_command(
        f"Find the most important current news about {topic}. Prioritize recent developments and state "
        "when the reported events happened when that matters."
    )


async def cmd_search(args: str) -> str:
    query = args.strip()
    if not query:
        return "Usage: /search <query>"
    return await _web_command(
        f"Search the web for: {query}. Answer the query directly using the most relevant current sources."
    )


async def cmd_pdf(args: str) -> tuple[str, list]:
    url = args.strip()
    if not url:
        return "Usage: /pdf <url>", []
    if not url.lower().startswith(("http://", "https://")):
        return "PDF must be an http(s) URL.", []

    pdf_bytes, filename, text = await fetch_pdf_document(
        url,
        max_chars=settings.pdf_max_chars,
    )
    if not text.strip():
        return "PDF downloaded, but no extractable text was found.", [
            {"type": "document", "data": pdf_bytes, "filename": filename}
        ]

    answer = await _provider.generate(
        user_message=(
            "Summarize this PDF. Focus on the main conclusions, important facts/numbers, and anything "
            "that appears actionable or surprising. The extracted text may be truncated for safety.\n\n"
            f"PDF text:\n{text}"
        ),
        history=[],
        instructions=_system_prompt(),
        web_search="off",
    )
    attachments = []
    if len(pdf_bytes) < 50 * 1024 * 1024:
        attachments.append({"type": "document", "data": pdf_bytes, "filename": filename})
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
    text = await _provider.generate(
        user_message=user_message,
        history=history or [],
        instructions=_system_prompt(context_summary),
        web_search="auto",
    )
    return text, settings.openai_model, []
