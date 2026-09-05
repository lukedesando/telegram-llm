# Flight Build Plan

Target: a single-user Telegram AI relay suitable for an eight-hour flight, deployed as a standalone Raspberry Pi service.

## Locked decisions

- Transport: Telegram only.
- Primary model architecture: OpenAI only in the target state.
- Flight-critical tools: web search, news, weather, flight status, and PDF retrieval/summarization.
- Deployment: standalone Raspberry Pi service before any Homebrew integration.
- Persistence target: SQLite with durable raw history and rolling context compaction.

## Delivery waves

### Wave 0 — trustworthy fork

1. Remove Grok and non-flight-critical commands/providers from the exposed Telegram surface.
2. Add baseline tests around command scope, health, and webhook rejection.
3. Clean configuration and documentation while preserving a runnable upstream provider path until OpenAI replaces it.

Acceptance: the reduced Telegram bot remains runnable and baseline tests pass.

### Wave 1 — durable OpenAI relay

1. Extract transport-neutral conversation handling.
2. Add SQLite persistence and rolling context compaction.
3. Replace the temporary Gemini/Claude model path with OpenAI Responses API.

Acceptance: Telegram -> relay -> OpenAI -> Telegram works across process restart and long conversations.

### Wave 2 — flight reliability and deployment

1. Add retry/idempotency/status controls.
2. Deploy as a standalone Pi service.
3. Run restart, long-conversation, failure, and end-to-end acceptance tests.

Acceptance: exact deployed revision passes the flight qualification checklist.

## Explicitly deferred

- WhatsApp/Twilio
- RCS
- Grok/xAI
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
