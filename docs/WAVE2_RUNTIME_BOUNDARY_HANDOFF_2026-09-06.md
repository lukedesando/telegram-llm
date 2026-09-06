# Wave 2 Runtime Boundary Handoff — 2026-09-06

## Objective

Complete the flight-ready single-user Telegram relay and deploy it as a standalone Raspberry Pi service using the approved Cloudflare public-webhook / Tailscale private-admin architecture.

## Current authoritative source state

- Repository: `lukedesando/telegram-llm`
- Current accepted `main`: `8e57306aaa6df8d23dfb2605057db2ae70f0fbae`
- PR #5: reliability controls — accepted
- PR #6: standalone Pi deployment/rollback/qualification — accepted
- PR #7: first runtime-boundary closeout — accepted
- PR #8: approved Cloudflare ingress hardening — accepted
- Credential-free complete suite before PR #8 merge: **47/47 passing** with `ResourceWarning` fatal
- No live `telegram-llm` Pi deployment has been performed by this work
- No `telegram.desando.org` Cloudflare route/policy/WAF mutation has been performed by this work

## Locked architecture

```text
user phone
-> Telegram
-> Cloudflare edge
-> existing Homebrew-owned Cloudflare Tunnel connector
-> 127.0.0.1:8787/webhook
-> telegram-llm
-> OpenAI

private administration
-> Tailscale
-> pi-guy
```

Decisions now established in source:

- Telegram only; OpenAI only.
- Standalone `telegram-llm` application deployment on `pi-guy`.
- Reuse the existing Homebrew remotely managed Cloudflare Tunnel connector; do not create a second connector.
- Public origin: `https://telegram.desando.org`.
- Tunnel publishes only exact `/webhook` to `http://127.0.0.1:8787`.
- Host-level Cloudflare Access remains deny-by-default.
- A more-specific `/webhook` Access application uses Bypass because Telegram cannot present Cloudflare Access service-token credentials.
- Cloudflare WAF blocks wrong method/path and sources outside Telegram's currently documented webhook source ranges.
- Application middleware independently returns 404 for non-webhook requests addressed to the configured public Host.
- Telegram webhook secret validation uses constant-time comparison.
- `/health` and operator surfaces remain local/Tailscale-only.
- Runtime history is durable SQLite with rolling compaction.

Full ingress contract: `docs/CLOUDFLARE_TELEGRAM_INGRESS.md`.
Full host deployment/acceptance procedure: `docs/PI_DEPLOYMENT.md`.

## Completed source work relevant to runtime

### Reliability / conversation

- persistent Telegram update processing/completion records
- five-minute processing lease with retry after abandonment
- immediate processing-lease release on handler failure/cancellation
- `/status`, `/new`, `/clear`, `/health`
- exact `APP_REVISION` reporting
- SQLite raw-history persistence and rolling summary compaction
- OpenAI Responses API only
- hosted web search plus retained weather/flight/PDF paths

### Standalone Pi deployment

- immutable releases under `/opt/telegram-llm/releases/<sha>`
- prepare-only cannot change active/next-start release
- single-worker systemd service on `127.0.0.1:8787`
- service user/group `luke:luke`
- secrets at `/etc/telegram-llm/telegram-llm.env`, required `root:luke:0640`
- deployment-owned SQLite path `/var/lib/telegram-llm/telegram-llm.sqlite3`
- transactional activation with verified restoration after post-promotion failure
- explicit rollback to already-installed exact releases
- non-mutating local Pi qualification

### Cloudflare ingress hardening — PR #8

- production `WEBHOOK_BASE_URL=https://telegram.desando.org`
- pathless HTTPS-origin preflight
- public-Host webhook-only middleware guard
- constant-time Telegram webhook-secret comparison
- source-controlled Cloudflare route/Access/WAF runbook
- explicit shared-tunnel reuse and independent Cloudflare rollback boundary

## Exact remaining execution boundary

No ingress architecture decision remains. The remaining work requires external control-plane, secret, and host state that the current GitHub tool surface cannot supply.

### 1. Cloudflare control plane

Apply the reviewed configuration to the existing Homebrew tunnel:

- published application: `telegram.desando.org` + exact `/webhook` -> `http://127.0.0.1:8787`
- preserve the public Host header and full `/webhook` path
- host-level deny-by-default Access application
- more-specific `/webhook` Access Bypass
- Telegram-host WAF Block rule from `docs/CLOUDFLARE_TELEGRAM_INGRESS.md`
- no broader route to port 8787

No Cloudflare management plugin is available in the current ChatGPT tool environment.

### 2. Runtime secrets on `pi-guy`

Place these values directly in `/etc/telegram-llm/telegram-llm.env` without exposing them in GitHub/chat:

```text
TELEGRAM_TOKEN
TELEGRAM_ALLOWED_USER_ID
WEBHOOK_BASE_URL=https://telegram.desando.org
WEBHOOK_SECRET_TOKEN
OPENAI_API_KEY
```

### 3. Standalone host execution

From a clean exact `main` checkout on `pi-guy`:

```bash
git fetch origin main
git checkout main
git merge --ff-only origin/main
git status --short
SHA="$(git rev-parse HEAD)"
sudo ./deploy/install_pi.sh "$SHA" --prepare-only
```

After Cloudflare and secrets are ready:

```bash
sudo ./deploy/install_pi.sh "$SHA"
sudo ./deploy/qualify_pi.sh "$SHA"
```

`telegram-llm` remains outside Homebrew Remote Operator application-deployment scope; do not broaden that typed authority into arbitrary shell execution merely to cross this boundary.

## Runtime acceptance still required

1. local `/health` reports exact deployed revision and healthy SQLite state;
2. public `https://telegram.desando.org/health` does not expose the local health payload;
3. Cloudflare route/Access/WAF state matches the reviewed contract;
4. Telegram `/status` succeeds;
5. normal OpenAI response succeeds;
6. `/search` succeeds with current information;
7. `/weather` succeeds;
8. `/pdf` succeeds;
9. service restart preserves conversation memory;
10. conversation crosses compaction threshold and retains an early fact;
11. `/new` clears prior context.

Wave 2 and the requested flight-ready scope are complete only after those exact-revision runtime gates pass.

## Smallest user/external action needed

- apply or provide an authorized way to apply the reviewed Cloudflare settings;
- put the required secrets on `pi-guy` without revealing them in chat/GitHub;
- use/provide the standalone SSH/Termius host execution path for the source-controlled commands.

No additional product, model, transport, deployment-style, or ingress-architecture decision is required.

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
