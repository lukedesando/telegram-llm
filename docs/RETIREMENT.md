# Telegram LLM retirement

**Retired:** 2026-09-06

## Decision

The standalone Telegram-to-OpenAI relay is retired and should not be restarted or redeployed as part of the flight plan.

The project reached a technically working relay path, but its core model dependency requires separately billed OpenAI API credits. The operating constraint is no additional spend. Replacing GPT-5.6 with a lower-quality local model is not an acceptable substitute for this use case because the output would still require GPT-level review, defeating the purpose of the relay.

This is therefore a product/economic retirement, not a Telegram, Cloudflare, Pi, or deployment failure.

## Accepted state at retirement

The last accepted runtime-bearing revision was:

```text
34858f28bf0b8ee1970a6698f8bfb807e24fabd1
```

Qualification evidence established:

- standalone immutable Pi deployment activated successfully;
- `LOCAL_PI_QUALIFICATION=PASS` on `pi-guy`;
- `telegram-llm.service` was active and enabled;
- listener was loopback-only at `127.0.0.1:8787`;
- SQLite storage health was `ok`;
- public `/health` and non-Telegram `POST /webhook` probes were blocked with HTTP 403 at Cloudflare;
- Telegram updates reached the application after the Cloudflare Access redirect was corrected;
- the authorized bot handler reached the OpenAI API;
- OpenAI returned HTTP 429 with `You have no credits remaining`, proving the remaining blocker was API billing rather than relay transport.

## Retirement scope

Retire all relay-specific operational surfaces while preserving source and data for audit/reference:

1. remove Telegram webhook registration and discard pending updates;
2. stop and disable `telegram-llm.service` on `pi-guy`;
3. remove the installed systemd unit after the service is stopped;
4. remove `telegram.desando.org` Cloudflare webhook ingress surfaces;
5. remove `telegram-llm.service` from Homebrew Remote Operator Level-A observation scope;
6. preserve the repository, immutable release directories, SQLite database, and secret file unless a separate secure-deletion decision is made.

Do **not** stop or remove the shared Homebrew Cloudflare Tunnel service; only the Telegram-specific hostname/path configuration is retired.

## Pi shutdown procedure

Run from `pi-guy`.

### 1. Delete the Telegram webhook without exposing the token

```bash
sudo bash -c 'set -a; . /etc/telegram-llm/telegram-llm.env; curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/deleteWebhook" -d "drop_pending_updates=true" | python3 -m json.tool'
```

Expected Telegram result contains `"ok": true`.

### 2. Stop and disable the service

```bash
sudo systemctl disable --now telegram-llm.service
```

### 3. Remove the installed unit and reload systemd

```bash
sudo rm -f /etc/systemd/system/telegram-llm.service
sudo systemctl daemon-reload
sudo systemctl reset-failed telegram-llm.service 2>/dev/null || true
```

### 4. Verify the runtime is gone

```bash
systemctl is-active telegram-llm.service 2>/dev/null || true
systemctl is-enabled telegram-llm.service 2>/dev/null || true
ss -ltn | grep ':8787' || echo 'TELEGRAM_LLM_LISTENER=absent'
```

Accepted retired state is no active service and no listener on port 8787.

The following are intentionally retained unless separately deleted:

```text
/opt/telegram-llm/
/var/lib/telegram-llm/
/etc/telegram-llm/
```

## Cloudflare retirement

Remove only Telegram-specific edge resources for `telegram.desando.org`:

- the path-specific Access application for `telegram.desando.org/webhook`;
- the Telegram-host WAF rule that permits only Telegram-source `POST /webhook`;
- the Tunnel public-hostname/path route that forwards the webhook to `http://127.0.0.1:8787`;
- the `telegram.desando.org` DNS/tunnel hostname if no other service uses it.

Do not stop, delete, or reconfigure the shared `homebrew-cloudflared.service` beyond removing the Telegram-specific route.

After removal, `telegram.desando.org` should no longer provide a route to the Pi.

## Homebrew retirement

`telegram-llm.service` was added to Homebrew only as a Level-A, read-only `service.status` target. Retirement removes that entry and its corresponding scope regression assertion. No Telegram mutation authority was ever added to Homebrew.

## Reuse policy

The repository is retained as a historical implementation and may be mined for reusable components such as Telegram ingress, SQLite conversation persistence, update deduplication, immutable Pi deployment, and webhook hardening.

Reactivation should be treated as a new product decision. Before any future reactivation, explicitly confirm model-provider cost, subscription/API billing boundaries, and expected recurring spend before implementation begins.
