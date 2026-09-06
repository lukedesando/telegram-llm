# Wave 2 Runtime Boundary Handoff — 2026-09-06

## Objective

Complete the flight-ready single-user Telegram relay and deploy it as a standalone Raspberry Pi service using the approved Cloudflare public-webhook / Tailscale private-admin architecture.

## Current authoritative source state

- Repository: `lukedesando/telegram-llm`
- Base `main` before the current ingress-hardening tranche: `9a54649614f0440e485238bb18d2ba050f47e0cc`
- Current source branch: `wave2-cloudflare-ingress-hardening-20260906`
- OpenAI-only Responses API relay: accepted
- SQLite durable history/rolling compaction: accepted
- Telegram update duplicate suppression/status/reset controls: accepted
- Standalone Pi deployment/rollback/qualification package: accepted
- Cloudflare/Tailscale architecture: approved by the user
- Cloudflare ingress hardening and runbook: implemented on the current branch; merge pending
- No live `telegram-llm` Pi deployment has been performed by this work
- No `telegram.desando.org` Cloudflare route has been created by this work

## Completed accepted source work

### PR #5 — reliability controls

- persistent Telegram update processing/completion records
- five-minute processing lease with retry after abandonment
- immediate processing-lease release on handler failure/cancellation
- `/status` local status command
- `/new` context reset alias
- storage-aware `/health`
- exact `APP_REVISION` reporting

### PR #6 — standalone Pi deployment

Merged as `aec4400ca260ef919c2ee63c6ad2aaaacdccd115`.

- OpenAI Python SDK pinned to `3.8.0`
- immutable releases under `/opt/telegram-llm/releases/<sha>`
- prepare-only cannot change active/next-start release
- single-worker systemd service on `127.0.0.1:8787`
- service user/group `luke:luke`
- secret-safe startup preflight
- deployment-owned SQLite path `/var/lib/telegram-llm/telegram-llm.sqlite3`
- transactional activation with verified restoration after post-promotion failure
- explicit rollback to already-installed exact releases
- non-mutating local Pi qualification
- deployment delta contract suite: 11/11 passing

### PR #7 — first runtime-boundary closeout

Merged as `9a54649614f0440e485238bb18d2ba050f47e0cc`.

That handoff originally left the ingress mechanism undecided. The user has since resolved that decision: use Cloudflare Tunnel for public Telegram webhook ingress and Tailscale only for private administration.

## Current ingress-hardening tranche

The current branch makes the approved design explicit and fail-closed in source:

- public base is `https://telegram.desando.org`;
- reuse the existing Homebrew-owned remotely managed Cloudflare Tunnel connector;
- publish only exact `/webhook` to `http://127.0.0.1:8787`;
- keep the hostname deny-by-default under Cloudflare Access;
- use a more-specific Access Bypass only for `/webhook`, because Telegram cannot supply Cloudflare Access service-token headers;
- use a Cloudflare WAF Block rule so only exact `POST /webhook` from Telegram's currently documented webhook source ranges proceeds;
- application middleware independently returns 404 for all non-webhook requests addressed to the configured public Host;
- Telegram's secret header is validated with constant-time comparison;
- `WEBHOOK_BASE_URL` must be a pathless HTTPS origin;
- `/health` remains a local/Tailscale-only qualification endpoint.

Full ingress contract: `docs/CLOUDFLARE_TELEGRAM_INGRESS.md`.

Credential-free branch qualification after these changes: **47/47 passing**, with `ResourceWarning` promoted to an error. The logged compaction exception is intentional test evidence and passes because raw history is preserved.

## Exact remaining execution boundary

The ingress **design decision is resolved**. Continuing into live service acceptance now requires external control-plane/secret/host state that is not available through the current GitHub tool surface:

1. Apply the reviewed Cloudflare configuration to the existing tunnel:
   - `telegram.desando.org`
   - exact `/webhook` published route to `http://127.0.0.1:8787`
   - host-level deny-by-default Access policy
   - path-specific `/webhook` Access Bypass
   - Telegram-host WAF rule from `docs/CLOUDFLARE_TELEGRAM_INGRESS.md`.
2. Put the runtime values on `pi-guy` in `/etc/telegram-llm/telegram-llm.env` with `root:luke:0640` permissions:
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_ALLOWED_USER_ID`
   - `WEBHOOK_BASE_URL=https://telegram.desando.org`
   - `WEBHOOK_SECRET_TOKEN`
   - `OPENAI_API_KEY`.
3. Execute the standalone Pi prepare/activate/qualification commands.
4. Run live Telegram/OpenAI acceptance.

No Cloudflare management plugin is available in the current ChatGPT tool environment, and the real credential values are intentionally absent from Git/GitHub/chat. `telegram-llm` also remains outside Homebrew Remote Operator application-deployment scope.

## Why existing authority does not cover those actions

- User approval covers the Cloudflare/Tailscale architecture, so no further design selection is needed.
- Applying policies/routes to the user's Cloudflare account requires a Cloudflare control-plane capability or dashboard/API credential not available here.
- Real Telegram/OpenAI secrets must not be committed or pasted into GitHub/chat-visible surfaces.
- Standalone application deployment on `pi-guy` requires a host execution path; the existing Homebrew Remote Operator must not be broadened into arbitrary shell execution.

## Smallest input/action needed after source merge

- Apply or provide an authorized way to apply the reviewed Cloudflare settings.
- Put the required runtime secrets on `pi-guy` without exposing their values in chat/GitHub.
- Provide/use a standalone SSH/Termius execution path for the source-controlled deployment commands.

No additional product, model, transport, deployment-style, or ingress-architecture decision remains.

## Continuation sequence after external prerequisites exist

From a clean exact `main` checkout on `pi-guy`:

```bash
git fetch origin main
git checkout main
git merge --ff-only origin/main
git status --short
SHA="$(git rev-parse HEAD)"
```

Prepare:

```bash
sudo ./deploy/install_pi.sh "$SHA" --prepare-only
```

After the secret environment and Cloudflare route/policies are present:

```bash
sudo ./deploy/install_pi.sh "$SHA"
sudo ./deploy/qualify_pi.sh "$SHA"
```

Then perform the Cloudflare boundary checks and live Telegram/OpenAI acceptance in `docs/PI_DEPLOYMENT.md`:

1. public `/health` is not exposed;
2. `/status`;
3. normal OpenAI reply;
4. `/search`;
5. `/weather`;
6. `/pdf`;
7. service restart with durable-memory check;
8. cross the compaction threshold and verify early memory;
9. `/new` reset verification.

Wave 2 is complete only after those exact-revision runtime gates pass.

## Intentionally deferred / out of current scope

- Homebrew-managed application deployment
- multi-worker deployment
- transactional exactly-once Telegram outbound queue
- WhatsApp/Twilio
- RCS
- alternative model providers
- dashboard/UI
- voice
- other deferred tools listed in `docs/FLIGHT_BUILD_PLAN.md`
