# Telegram LLM — retired

> **Retired 2026-09-06.** This project is preserved as a historical implementation and should not be restarted or redeployed as part of the flight plan.

The standalone Telegram relay reached a working Telegram → Cloudflare → Pi → OpenAI API path and passed local Pi qualification at runtime revision `34858f28bf0b8ee1970a6698f8bfb807e24fabd1`.

It was retired because the architecture depends on separately billed OpenAI API credits and the operating constraint is **no additional spend**. A lower-quality local model is not an acceptable substitute for this use case because its output would still require GPT-level review.

See [`docs/RETIREMENT.md`](docs/RETIREMENT.md) for the accepted final state, shutdown procedure, Cloudflare cleanup, Homebrew Level-A removal, retained data policy, and reuse guidance.

## Historical implementation

This repository is a fork of [`eloquentix/hermes`](https://github.com/eloquentix/hermes) and retains its MIT license.

The retired implementation includes:

- single-user Telegram webhook handling;
- Cloudflare-protected public ingress;
- SQLite durable conversation history;
- rolling context compaction without deleting raw history;
- persistent Telegram update deduplication/leases;
- OpenAI Responses API integration;
- hosted web search, news, weather, flight, and PDF workflows;
- standalone immutable Raspberry Pi deployment with transactional activation/rollback;
- local health and revision qualification;
- Homebrew Level-A read-only service observation.

Historical design and deployment detail remains in `docs/` and the repository history. The code is retained for reference and possible component reuse, not as an active service.

## License

MIT. Original Hermes copyright/license notice retained in `LICENSE`.
