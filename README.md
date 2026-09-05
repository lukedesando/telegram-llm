# Telegram LLM

A single-user Telegram AI relay optimized for constrained inflight connectivity and self-hosted deployment.

This repository is a fork of [`eloquentix/hermes`](https://github.com/eloquentix/hermes) and retains its MIT license. The fork is being narrowed around a specific flight-readiness target: Telegram transport, durable conversation state, OpenAI as the final model provider, and a small set of high-value tools.

## Flight-build scope

The pre-flight build intentionally supports only:

- normal AI conversation
- `/search <query>` — current web search
- `/news [topic]` — current news
- `/weather <city>` — weather
- `/flight <UA123>` — flight status
- `/pdf <url>` — fetch and summarize a PDF
- `/clear` — reset the current conversation
- `/help` — command list

Explicitly deferred until after flight qualification: Grok/xAI, image search, stocks, translation, sports, literary retrieval, WhatsApp, RCS, multi-user support, vector memory, dashboard/UI, voice, and Homebrew-managed deployment.

## Current migration state

Wave 0 keeps the upstream Gemini/Claude path temporarily so each merge remains runnable. Wave 1 will replace both with the OpenAI Responses API rather than landing an intermediate broken revision.

The current conversation store is still the upstream 12-turn in-memory buffer. SQLite persistence and rolling context compaction are Wave 1 work and are not yet complete.

See [`docs/FLIGHT_BUILD_PLAN.md`](docs/FLIGHT_BUILD_PLAN.md) for the delivery gates.

## Quick start

```bash
git clone https://github.com/lukedesando/telegram-llm.git
cd telegram-llm
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Telegram requires a public HTTPS webhook URL. Set `WEBHOOK_BASE_URL` to that endpoint and create a webhook secret with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Required configuration during Wave 0

```text
TELEGRAM_TOKEN
TELEGRAM_ALLOWED_USER_ID
WEBHOOK_BASE_URL
WEBHOOK_SECRET_TOKEN
ANTHROPIC_API_KEY        # temporary; removed in Wave 1
GEMINI_API_KEY           # temporary; removed in Wave 1
```

`CLAUDE_MODEL`, `GEMINI_MODELS`, `MAX_RESPONSE_CHARS`, and `MAX_TOOL_ITERATIONS` have defaults.

## Architecture

Current Wave 0 path:

```text
Telegram
   ↓
FastAPI /webhook
   ↓
Telegram handlers
   ↓
12-turn in-memory history
   ↓
Temporary Gemini/Claude agent
   ↓
Telegram reply
```

Target Wave 1 path:

```text
Telegram
   ↓
FastAPI webhook adapter
   ↓
Conversation service
   ↓
SQLite raw history + rolling compacted context
   ↓
OpenAI Responses API
   ↓
Telegram reply
```

## Security boundaries

- single authorized Telegram user ID
- Telegram webhook secret validation
- secrets loaded from environment / `.env`, not source control
- bounded model/tool iterations
- standalone Pi deployment first; no cross-repository runtime dependency required for flight readiness

## Tests

Wave 0 includes lightweight repository-contract tests that do not require live provider credentials:

```bash
python -m compileall -q .
python -m unittest discover -s tests -v
```

Behavioral provider, persistence, restart, and end-to-end Telegram tests are added in later waves as those boundaries are introduced.

## License

MIT. Original Hermes copyright/license notice retained in `LICENSE`.
