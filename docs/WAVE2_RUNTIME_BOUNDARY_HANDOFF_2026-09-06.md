# Wave 2 Runtime Boundary Handoff — 2026-09-06

## Objective

Complete the flight-ready single-user Telegram relay and deploy it as a standalone Raspberry Pi service without broadening Homebrew runtime authority or silently choosing a new public-ingress trust boundary.

## Current authoritative source state

- Repository: `lukedesando/telegram-llm`
- Accepted source through PR #6
- PR #6 squash merge on `main`: `aec4400ca260ef919c2ee63c6ad2aaaacdccd115`
- OpenAI-only Responses API relay: accepted
- SQLite durable history/rolling compaction: accepted
- Telegram update duplicate suppression/status/reset controls: accepted
- Standalone Pi deployment/rollback/qualification package: accepted
- No live `telegram-llm` service deployment has been performed by this work
- No public webhook route has been created by this work

## Completed source work

### PR #5 — reliability controls

Accepted and merged before PR #6.

- persistent Telegram update processing/completion records
- five-minute processing lease with retry after abandonment
- immediate processing-lease release on handler failure/cancellation
- `/status` local status command
- `/new` context reset alias
- storage-aware `/health`
- exact `APP_REVISION` reporting
- credential-free source suite: 32/32 passing before merge

### PR #6 — standalone Pi deployment

Accepted and merged as `aec4400ca260ef919c2ee63c6ad2aaaacdccd115`.

- OpenAI Python SDK pinned to `3.8.0`
- immutable releases under `/opt/telegram-llm/releases/<sha>`
- `--prepare-only` cannot change active/next-start release
- single-worker systemd service on `127.0.0.1:8787`
- service user/group `luke:luke`
- secret-safe startup preflight
- deployment-owned SQLite path `/var/lib/telegram-llm/telegram-llm.sqlite3`
- transactional activation with verified restoration of prior managed state on post-promotion failure
- first-install activation failure returns to no selected unit/revision/current state and inactive/disabled service state
- explicit rollback to already-installed exact releases
- non-mutating local Pi qualification
- executable install/rollback/qualification entrypoints
- deployment delta contract suite: 11/11 passing
- shell syntax gates passing
- systemd unit verified in a host-like sandbox; installer re-verifies on `pi-guy`

## Exact execution boundary

Continuing from source into live activation requires external runtime state that is not available through the current repository/GitHub control surface and includes user-owned trust/credential decisions.

Required values/state:

- `TELEGRAM_TOKEN`
- `TELEGRAM_ALLOWED_USER_ID`
- `WEBHOOK_SECRET_TOKEN`
- `OPENAI_API_KEY`
- a selected public HTTPS ingress mechanism and resulting `WEBHOOK_BASE_URL`

The public endpoint must route:

```text
POST https://<public-base>/webhook
```

to:

```text
http://127.0.0.1:8787/webhook
```

## Why current authority does not cover it

- `telegram-llm` is not in the current Homebrew Remote Operator repository scope.
- The Homebrew Remote Operator is a typed operation surface, not an arbitrary shell; the standalone deployment scripts cannot be routed through it as command text or paths.
- Adding `telegram-llm` to Homebrew managed deployment/Remote Operator scope is explicitly deferred and would be a separate architecture/authority change.
- Selecting Cloudflare Tunnel, Tailscale Funnel, another reverse proxy, or another public ingress mechanism changes the external exposure/trust boundary and is reserved for the user.
- Real Telegram/OpenAI credential material is intentionally absent from source and must not be placed in GitHub issues, PRs, Actions logs, or repository files.

## Smallest input/action needed to resume

1. Select/approve the public HTTPS ingress mechanism for this relay.
2. Make the required Telegram/OpenAI credential values available on `pi-guy` in `/etc/telegram-llm/telegram-llm.env` with `root:luke:0640` permissions, without placing them in GitHub/chat-visible source.
3. Ensure the corresponding public `WEBHOOK_BASE_URL` is known.
4. Provide a host execution path for the standalone commands, or explicitly authorize a separate reviewed Homebrew integration project if remote managed deployment is desired instead.

No product or source-design decision remains before these runtime prerequisites.

## Continuation sequence after boundary resolution

From a clean exact `main` checkout on `pi-guy`:

```bash
git fetch origin main
git checkout main
git merge --ff-only origin/main
git status --short
SHA="$(git rev-parse HEAD)"
```

Then:

```bash
sudo ./deploy/install_pi.sh "$SHA" --prepare-only
```

After secret environment and HTTPS ingress are ready:

```bash
sudo ./deploy/install_pi.sh "$SHA"
sudo ./deploy/qualify_pi.sh "$SHA"
```

Then complete the live Telegram/OpenAI acceptance sequence in `docs/PI_DEPLOYMENT.md`:

1. `/status`
2. normal OpenAI reply
3. `/search`
4. `/weather`
5. `/pdf`
6. service restart with memory persistence check
7. enough conversation turns to cross compaction threshold, then verify early memory
8. `/new` reset verification

Wave 2 is complete only after those exact-revision runtime gates pass.

## Intentionally deferred / out of current scope

- Homebrew-managed deployment
- multi-worker deployment
- transactional exactly-once Telegram outbound queue
- WhatsApp/Twilio
- RCS
- alternative model providers
- dashboard/UI
- voice
- other deferred tools listed in `docs/FLIGHT_BUILD_PLAN.md`
