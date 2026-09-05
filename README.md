# Telegram LLM

A single-user Telegram AI relay optimized for constrained inflight connectivity and self-hosted deployment.

This repository is a fork of [`eloquentix/hermes`](https://github.com/eloquentix/hermes) and retains its MIT license. The fork is narrowed around a flight-readiness target: Telegram transport, durable conversation state, OpenAI, and a small set of high-value tools.

## Flight-build scope

The pre-flight build intentionally supports only:

- normal AI conversation with optional hosted web search
- `/search <query>` — current web search
- `/news [topic]` — current news
- `/weather <city>` — direct weather lookup
- `/flight <UA123>` — current flight status
- `/pdf <url>` — download, locally extract, summarize, and return a PDF
- `/clear` — reset the current conversation
- `/help` — command list

Explicitly deferred until after flight qualification: Grok/xAI, Gemini, Claude, image search, stocks, translation, sports, literary retrieval, WhatsApp, RCS, multi-user support, vector memory, dashboard/UI, voice, and Homebrew-managed deployment.

## Current architecture

The Telegram adapter uses a transport-neutral conversation service backed by SQLite. Raw user/assistant messages remain durable across process restarts. Model context uses a rolling summary plus uncompacted recent messages; compaction never deletes raw history.

OpenAI's Responses API is the only model-provider path. The default model is configurable with `OPENAI_MODEL`; the flight build defaults to `gpt-5.6-terra`. Current/news/flight/search commands require hosted web search, while normal conversation exposes web search for the model to use when needed. Conversation compaction and local PDF summarization do not enable web search.

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
OpenAI Responses API
   ├── hosted web search when needed
   ├── direct weather helper
   └── local PDF extraction
   ↓
Telegram reply
```

See [`docs/FLIGHT_BUILD_PLAN.md`](docs/FLIGHT_BUILD_PLAN.md) for the remaining qualification gates.

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

## Required configuration

```text
TELEGRAM_TOKEN
TELEGRAM_ALLOWED_USER_ID
WEBHOOK_BASE_URL
WEBHOOK_SECRET_TOKEN
OPENAI_API_KEY
```

Useful optional overrides:

```text
OPENAI_MODEL=gpt-5.6-terra
OPENAI_REASONING_EFFORT=low
OPENAI_TIMEOUT_SECONDS=45
OPENAI_MAX_OUTPUT_TOKENS=1800
WEB_SEARCH_CONTEXT_SIZE=medium
DATABASE_PATH=data/telegram-llm.sqlite3
RECENT_CONTEXT_ITEMS=12
COMPACT_AFTER_ITEMS=24
MAX_SUMMARY_CHARS=4000
MAX_RESPONSE_CHARS=3500
PDF_MAX_CHARS=60000
```

## Security and reliability boundaries

- one authorized Telegram user ID
- Telegram webhook secret validation
- OpenAI and Telegram secrets loaded from environment / `.env`, not source control
- Responses API calls use `store=false`; SQLite is the conversation source of truth
- raw history survives compaction and restart
- same-conversation processing is serialized in the single-worker runtime
- standalone Pi deployment first; no cross-repository runtime dependency required for flight readiness

## Tests

The repository includes credential-free contracts for scope, webhook protection, SQLite persistence, restart behavior, compaction, OpenAI Responses request shape, and PDF extraction:

```bash
python -m compileall -q .
PYTHONWARNINGS='error::ResourceWarning' python -m unittest discover -s tests -v
```

Live OpenAI, public webhook, Telegram delivery, restart, and long-conversation qualification are separate runtime gates.

## License

MIT. Original Hermes copyright/license notice retained in `LICENSE`.
