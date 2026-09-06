# Flight Build Plan

Target: a single-user Telegram AI relay suitable for an eight-hour flight, deployed as a standalone Raspberry Pi service.

## Locked decisions

- Transport: Telegram only.
- Model architecture: OpenAI only.
- Flight-critical tools: web search, news, weather, flight status, and PDF retrieval/summarization.
- Deployment: standalone Raspberry Pi service before any Homebrew integration.
- Persistence: SQLite with durable raw history and rolling context compaction.

## Delivery waves

### Wave 0 — trustworthy fork — COMPLETE

1. Remove Grok and non-flight-critical commands/providers from the exposed Telegram surface. — complete
2. Add baseline tests around command scope, health, and webhook rejection. — complete
3. Clean configuration and documentation while preserving a runnable migration path. — complete

Accepted in PR #1.

### Wave 1 — durable OpenAI relay — COMPLETE

1. Extract transport-neutral conversation handling. — accepted in PR #2
2. Add SQLite persistence and rolling context compaction. — accepted in PR #3
3. Replace temporary model providers with OpenAI Responses API. — accepted in PR #4

Credential-free source qualification passed before each merge. Live Telegram -> relay -> OpenAI -> Telegram qualification remains a Wave 2 runtime gate because it requires runtime credentials and public webhook connectivity.

### Wave 2 — flight reliability and deployment — IN PROGRESS

1. Add retry/idempotency/status/new-conversation controls. — accepted in PR #5
   - persistent Telegram update processing/completion records in SQLite
   - five-minute stale processing lease with immediate release on handler failure/cancellation
   - `/status` local status command
   - `/new` using the established context-reset behavior
   - `/health` verifies SQLite and returns 503 when durable storage is unavailable
   - `APP_REVISION` surfaced through `/health` and `/status` for exact-revision qualification
2. Standalone Pi deployment package. — source implemented on `wave2-standalone-pi-deployment-20260906`; live activation pending
   - OpenAI SDK pinned for repeatable installation
   - immutable releases under `/opt/telegram-llm/releases/<sha>`
   - prepare-only path cannot change the active release/unit
   - activation requires a clean exact `main` SHA and an existing secret environment file
   - systemd unit runs as `luke`, one worker, bound only to `127.0.0.1:8787`
   - startup preflight validates required secrets/configuration without printing secret values and rejects SQLite-path overrides
   - rollback selects only an already-installed exact release and can validate it even if `current` is broken
   - non-mutating local Pi qualification binds runtime evidence to the expected SHA
   - deployment scripts are executable in the Git tree
   - deployment delta tests: 10/10 passing
   - exact systemd unit syntax/directives passed `systemd-analyze verify` in a host-like validation sandbox; activation repeats verification on `pi-guy`
3. Activate the exact release behind a selected public HTTPS webhook route. — pending
4. Qualify live OpenAI responses and Telegram delivery. — pending
5. Run service-restart, long-conversation/compaction, PDF, search, reset, and end-to-end acceptance on the exact deployed revision. — pending

Acceptance: exact deployed revision passes the flight qualification checklist and remains operable without the user's laptop.

## Current live-runtime boundary

The source repository deliberately does not choose or configure the public HTTPS ingress mechanism and does not contain real Telegram/OpenAI credentials. Activation therefore requires externally established values for:

- `TELEGRAM_TOKEN`;
- `TELEGRAM_ALLOWED_USER_ID`;
- `WEBHOOK_SECRET_TOKEN`;
- `OPENAI_API_KEY`;
- `WEBHOOK_BASE_URL`, whose public HTTPS route must forward `/webhook` to `127.0.0.1:8787`.

Homebrew-managed deployment remains deferred. The current Homebrew Remote Operator scope does not include `telegram-llm` and must not be broadened merely to bypass this standalone deployment boundary.

## Reliability boundary

Telegram duplicate suppression is intentionally lightweight for the flight build. Completed update IDs survive restart and in-flight work can be retried after an abandoned lease. This does not claim transactional exactly-once delivery: a crash after Telegram accepts an outbound reply but before completion is durably recorded can permit a duplicate after lease expiry. A transactional outbound queue is not required by the current flight scope.

## Explicitly deferred

- WhatsApp/Twilio
- RCS
- Grok/xAI
- Gemini
- Claude
- multi-user support
- vector memory
- dashboard/UI
- voice
- image search
- stocks
- translation
- sports
- literary retrieval
- Homebrew-managed deployment
- multi-worker service deployment
- transactional outbound-message queue / exactly-once Telegram delivery
