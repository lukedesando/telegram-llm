# Flight Build Plan

Target: a single-user Telegram AI relay suitable for an eight-hour flight, deployed as a standalone Raspberry Pi service.

## Locked decisions

- Transport: Telegram only.
- Model architecture: OpenAI only.
- Flight-critical tools: web search, news, weather, flight status, and PDF retrieval/summarization.
- Deployment: standalone Raspberry Pi service before any Homebrew application-management integration.
- Persistence: SQLite with durable raw history and rolling context compaction.
- Public webhook ingress: reuse the existing Homebrew-owned Cloudflare Tunnel connector.
- Public hostname: `telegram.desando.org`; only `POST /webhook` is a public application surface.
- Private administration: Tailscale; it is not in the Telegram delivery path.

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

Credential-free source qualification passed before each merge.

### Wave 2 — flight reliability and deployment — RUNTIME BOUNDARY

1. Reliability controls. — accepted in PR #5
   - persistent Telegram update processing/completion records in SQLite
   - five-minute stale processing lease with immediate release on handler failure/cancellation
   - `/status` local status command
   - `/new` using the established context-reset behavior
   - `/health` verifies SQLite and returns 503 when durable storage is unavailable
   - `APP_REVISION` surfaced through `/health` and `/status` for exact-revision qualification
2. Standalone Pi deployment package. — accepted in PR #6; merge revision `aec4400ca260ef919c2ee63c6ad2aaaacdccd115`
   - OpenAI SDK pinned for repeatable installation
   - immutable releases under `/opt/telegram-llm/releases/<sha>`
   - prepare-only path cannot change the active release/unit
   - activation requires a clean exact `main` SHA and an existing secret environment file
   - activation is transactional and verifies restoration after post-promotion failure
   - systemd unit runs as `luke`, one worker, bound only to `127.0.0.1:8787`
   - startup preflight validates required secrets/configuration without printing secret values and rejects SQLite-path overrides
   - explicit rollback selects only an already-installed exact release
   - non-mutating local Pi qualification binds runtime evidence to the expected SHA
   - deployment scripts are executable in the Git tree
   - deployment delta tests: 11/11 passing
3. Runtime-boundary closeout. — accepted in PR #7; `main` revision `9a54649614f0440e485238bb18d2ba050f47e0cc`
4. Approved Cloudflare ingress hardening. — accepted in PR #8; merge revision `8e57306aaa6df8d23dfb2605057db2ae70f0fbae`
   - reuse the existing Homebrew remotely managed Cloudflare Tunnel connector rather than creating another connector
   - `WEBHOOK_BASE_URL=https://telegram.desando.org`
   - Cloudflare published application is path-scoped to `/webhook` -> `127.0.0.1:8787`
   - host-level Access remains deny-by-default; the machine webhook uses only a more-specific path Bypass because Telegram cannot present Cloudflare Access credentials
   - Cloudflare WAF blocks wrong method/path and sources outside Telegram's currently documented webhook source networks
   - application independently returns 404 for every non-webhook request addressed to the configured public Host
   - Telegram webhook secret is compared in constant time
   - `/health` and operator surfaces remain local/Tailscale-only
   - `WEBHOOK_BASE_URL` preflight requires a pathless HTTPS origin
   - complete credential-free suite: 47/47 passing with `ResourceWarning` fatal before merge
5. Apply the reviewed Cloudflare control-plane configuration. — pending external control-plane action
6. Prepare/activate the exact standalone Pi release and run local qualification. — pending runtime credentials and host execution
7. Qualify live Telegram -> relay -> OpenAI -> Telegram delivery. — pending runtime activation
8. Run service-restart, long-conversation/compaction, PDF, search, weather, reset, and end-to-end acceptance on the exact deployed revision. — pending runtime activation

Acceptance: the exact deployed revision passes the Cloudflare boundary checks and flight qualification checklist and remains operable without the user's laptop.

## Current live-runtime boundary

The ingress architecture is no longer undecided. The approved path is:

```text
Telegram
-> Cloudflare edge
-> existing Homebrew Cloudflare Tunnel
-> 127.0.0.1:8787/webhook
-> telegram-llm

operator administration
-> Tailscale
-> pi-guy
```

Source can define and test this contract, but the current GitHub control surface cannot mutate the user's Cloudflare account or place runtime secrets on `pi-guy`.

Remaining external state/actions are:

- add the reviewed `telegram.desando.org` + exact `/webhook` published application to the existing tunnel;
- add the reviewed host/path Access policies and WAF rule from `docs/CLOUDFLARE_TELEGRAM_INGRESS.md`;
- place `TELEGRAM_TOKEN`, `TELEGRAM_ALLOWED_USER_ID`, `WEBHOOK_SECRET_TOKEN`, and `OPENAI_API_KEY` in `/etc/telegram-llm/telegram-llm.env` with the reviewed permissions;
- execute the standalone Pi prepare/activation/qualification commands;
- run live Telegram/OpenAI acceptance.

Homebrew-managed **application deployment** remains deferred. Reusing Homebrew's already-established Cloudflare connector does not grant or require arbitrary Homebrew Remote Operator authority over `telegram-llm`.

See `docs/CLOUDFLARE_TELEGRAM_INGRESS.md`, `docs/PI_DEPLOYMENT.md`, and `docs/WAVE2_RUNTIME_BOUNDARY_HANDOFF_2026-09-06.md`.

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
- Homebrew-managed application deployment
- multi-worker service deployment
- transactional outbound-message queue / exactly-once Telegram delivery
