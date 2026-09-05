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

### Wave 1 — durable OpenAI relay — SOURCE COMPLETE AFTER PR #4

1. Extract transport-neutral conversation handling. — accepted in PR #2
2. Add SQLite persistence and rolling context compaction. — accepted in PR #3
3. Replace temporary model providers with OpenAI Responses API. — PR #4

Source acceptance requires the credential-free suite to pass with OpenAI as the only model-provider dependency. Live Telegram -> relay -> OpenAI -> Telegram qualification belongs to Wave 2 because it requires runtime credentials and public webhook connectivity.

### Wave 2 — flight reliability and deployment — NEXT

1. Add retry/idempotency/status/new-conversation controls.
2. Deploy as a single-worker standalone Pi service behind a public HTTPS webhook.
3. Qualify live OpenAI responses and Telegram delivery.
4. Run restart, long-conversation, failure, and end-to-end acceptance tests on the exact deployed revision.

Acceptance: exact deployed revision passes the flight qualification checklist and remains operable without the user's laptop.

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
