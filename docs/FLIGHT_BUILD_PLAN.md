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

1. Add retry/idempotency/status/new-conversation controls. — source implemented on `wave2-flight-reliability-20260905`; credential-free suite 32/32 passing before PR creation
   - persistent Telegram update processing/completion records in SQLite
   - five-minute stale processing lease with immediate release on handler failure/cancellation
   - `/status` local status command
   - `/new` using the established context-reset behavior
   - `/health` verifies SQLite and returns 503 when durable storage is unavailable
   - `APP_REVISION` surfaced through `/health` and `/status` for exact-revision qualification
2. Deploy as a single-worker standalone Pi service behind a public HTTPS webhook. — pending
3. Qualify live OpenAI responses and Telegram delivery. — pending
4. Run restart, long-conversation, failure, and end-to-end acceptance tests on the exact deployed revision. — pending

Acceptance: exact deployed revision passes the flight qualification checklist and remains operable without the user's laptop.

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
