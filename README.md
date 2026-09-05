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

The Telegram adapter now uses a transport-neutral conversation service backed by SQLite. Raw user/assistant messages remain durable across process restarts. Model context uses a rolling summary plus uncompacted recent messages; compaction never deletes raw history.

The Gemini/Claude path remains temporary only so each intermediate merge is runnable. The next Wave 1 PR replaces both model providers and the summarizer with the OpenAI Responses API.

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

For the flight build, run a single Uvicorn worker. Conversation serialization currently uses an in-process per-conversation lock; multi-worker deployment is intentionally deferred.

## Required configuration during the temporary-provider stage

```text
TELEGRAM_TOKEN
TELEGRAM_ALLOWED_USER_ID
WEBHOOK_BASE_URL
WEBHOOK_SECRET_TOKEN
ANTHROPIC_API_KEY        # temporary; removed at OpenAI cutover
GEMINI_API_KEY           # temporary; removed at OpenAI cutover
```

Conversation defaults are configurable with `DATABASE_PATH`, `RECENT_CONTEXT_ITEMS`, `COMPACT_AFTER_ITEMS`, and `MAX_SUMMARY_CHARS`.

## Architecture

Current path:

```text
Telegram
   ↓
FastAPI webhook adapter
   ↓
Conversation service
   ↓
SQLite raw history
   ├── rolling compacted summary
   └── uncompacted recent messages
   ↓
Temporary Gemini/Claude agent
   ↓
Telegram reply
```

Next Wave 1 target:

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

The repository includes credential-free contract, persistence, restart, and compaction tests:

```bash
python -m compileall -q .
PYTHONWARNINGS='error::ResourceWarning' python -m unittest discover -s tests -v
```

Live provider and end-to-end Telegram qualification are separate gates because they require runtime credentials and public webhook connectivity.

## License

MIT. Original Hermes copyright/license notice retained in `LICENSE`.
