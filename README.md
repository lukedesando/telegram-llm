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
- `/status` — local relay/storage/revision status without an OpenAI call
- `/new` — start over using the established context-reset behavior
- `/clear` — reset the current conversation
- `/help` — command list

Explicitly deferred until after flight qualification: Grok/xAI, Gemini, Claude, image search, stocks, translation, sports, literary retrieval, WhatsApp, RCS, multi-user support, vector memory, dashboard/UI, voice, and Homebrew-managed application deployment.

## Current architecture

The Telegram adapter uses a transport-neutral conversation service backed by SQLite. Raw user/assistant messages remain durable across process restarts. Model context uses a rolling summary plus uncompacted recent messages; compaction never deletes raw history.

OpenAI's Responses API is the only model-provider path. The default model is configurable with `OPENAI_MODEL`; the flight build defaults to `gpt-5.6-terra`. Current/news/flight/search commands require hosted web search, while normal conversation exposes web search for the model to use when needed. Conversation compaction and local PDF summarization do not enable web search.

Telegram update IDs are persisted in SQLite. Completed updates are suppressed across process restarts; in-flight updates use a five-minute processing lease so an abandoned update can be retried rather than remaining permanently wedged. A failed/cancelled handler releases its lease immediately. This is duplicate suppression, not a transactional outbound-message queue: a process crash after Telegram accepts a reply but before completion is recorded can still produce a duplicate after lease expiry.

```text
phone on constrained messaging Wi-Fi
   ↓
Telegram
   ↓
Cloudflare edge
   ↓
existing Homebrew Cloudflare Tunnel
   ↓
127.0.0.1:8787/webhook
   ↓
public Host/path guard + Telegram secret validation
   ↓
persistent update lease / duplicate suppression
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

private administration
   ↓
Tailscale
   ↓
pi-guy
```

The approved public webhook origin is `https://telegram.desando.org`; only exact `POST /webhook` is intended to be publicly reachable. The application independently returns 404 for other routes addressed to that public Host. `/health` remains a local/Tailscale qualification surface.

See [`docs/CLOUDFLARE_TELEGRAM_INGRESS.md`](docs/CLOUDFLARE_TELEGRAM_INGRESS.md) for the ingress security contract and [`docs/FLIGHT_BUILD_PLAN.md`](docs/FLIGHT_BUILD_PLAN.md) for the remaining qualification gates.

## Quick start

```bash
git clone https://github.com/lukedesando/telegram-llm.git
cd telegram-llm
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
```

Telegram requires a public HTTPS webhook origin. Production uses:

```text
WEBHOOK_BASE_URL=https://telegram.desando.org
```

The application appends `/webhook`. `WEBHOOK_BASE_URL` must therefore be a pathless HTTPS origin with no trailing slash. Create a webhook secret with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

For the flight build, run a single Uvicorn worker. Conversation serialization currently uses an in-process per-conversation lock; multi-worker deployment is intentionally deferred.

## Standalone Pi deployment

The repository includes an exact-revision standalone deployment package for `pi-guy`:

- `deploy/systemd/telegram-llm.service` — single-worker service bound only to `127.0.0.1:8787`;
- `deploy/preflight.py` — secret-safe startup validation;
- `deploy/install_pi.sh` — immutable release preparation and transactional activation;
- `deploy/rollback_pi.sh` — rollback to an already-installed exact revision;
- `deploy/qualify_pi.sh` — non-mutating local runtime qualification;
- `deploy/telegram-llm.env.example` — secret environment field template.

Preparation can be completed without credentials and cannot change the active release. Public Telegram ingress reuses the existing Homebrew-owned remotely managed Cloudflare Tunnel connector; `telegram-llm` application deployment itself remains standalone.

Full commands, security boundaries, rollback, Cloudflare checks, and live Telegram/OpenAI acceptance are in [`docs/PI_DEPLOYMENT.md`](docs/PI_DEPLOYMENT.md).

## Required configuration

```text
TELEGRAM_TOKEN
TELEGRAM_ALLOWED_USER_ID
WEBHOOK_BASE_URL=https://telegram.desando.org
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
APP_REVISION=unknown
MAX_RESPONSE_CHARS=3500
PDF_MAX_CHARS=60000
```

Production deployment sets `APP_REVISION` from the exact selected release rather than the secret file. `/health` and `/status` expose that value so local qualification can prove which source revision is running.

## Security and reliability boundaries

- one authorized Telegram user ID
- Telegram webhook secret validation uses constant-time comparison
- configured public Host exposes only exact `POST /webhook`; other public-Host routes return 404
- Cloudflare route is intended to publish only `/webhook` to the loopback service
- Cloudflare WAF restricts the public webhook to the expected method/path and Telegram's currently documented webhook source networks
- host-level Cloudflare Access remains deny-by-default; only the machine webhook path uses a narrowly scoped Bypass because Telegram cannot present Cloudflare Access credentials
- OpenAI and Telegram secrets are loaded from environment / `.env`, not source control
- OpenAI SDK is pinned for deployment reproducibility
- Responses API calls use `store=false`; SQLite is the conversation source of truth
- raw history survives compaction and restart
- completed Telegram update IDs survive restart for duplicate suppression
- `/health` returns 503 when the SQLite store is unavailable
- standalone service binds only to loopback; no router port is opened
- Tailscale remains the private administration path and is not required for Telegram delivery
- same-conversation processing is serialized in the single-worker runtime

## Tests

The repository includes credential-free contracts for scope, webhook protection, public-host isolation, SQLite persistence, restart behavior, compaction, Telegram update leases/deduplication, OpenAI Responses request shape, PDF extraction, and standalone deployment invariants:

```bash
python -m compileall -q .
PYTHONWARNINGS='error::ResourceWarning' python -m unittest discover -s tests -v
```

Live Cloudflare policy/route state, OpenAI execution, Telegram delivery, Pi service restart, and long-conversation qualification remain separate runtime gates.

## License

MIT. Original Hermes copyright/license notice retained in `LICENSE`.
