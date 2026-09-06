# Standalone Raspberry Pi Deployment

This runbook deploys `telegram-llm` as a standalone service on `pi-guy`. It deliberately does not add the repository to Homebrew's managed-service or Remote Operator scope.

## Fixed deployment contract

- Host: `pi-guy`
- Service user/group: `luke:luke`
- Service: `telegram-llm.service`
- Runtime root: `/opt/telegram-llm`
- Immutable releases: `/opt/telegram-llm/releases/<git-sha>`
- Active symlink: `/opt/telegram-llm/current`
- Secret environment: `/etc/telegram-llm/telegram-llm.env`
- Non-secret revision environment: `/etc/telegram-llm/revision.env`
- SQLite state: `/var/lib/telegram-llm/telegram-llm.sqlite3`
- Local listener: `127.0.0.1:8787`
- Uvicorn workers: exactly 1

Port 8787 is intentionally separate from the currently documented Auto-Application listener on 8765 and status dashboard listener on 8766. The installer also refuses first activation if 8787 is already listening.

## External prerequisites

Activation requires two things that are intentionally not created by the repository installer:

1. real Telegram/OpenAI credentials in the secret environment file;
2. a public HTTPS endpoint represented by `WEBHOOK_BASE_URL` that routes Telegram's `POST <base>/webhook` to `http://127.0.0.1:8787/webhook` on the Pi.

The public-ingress mechanism is not selected by this repository. Cloudflare Tunnel, Tailscale Funnel, a conventional reverse proxy, or another mechanism would change the external exposure/trust boundary and must be chosen separately. Do not expose Uvicorn directly to the Internet; the systemd unit binds only to loopback.

`/health` is required locally. It does not need to be publicly exposed for Telegram operation.

## 1. Reconcile exact source

From the existing Pi checkout of this repository, establish a clean exact `main` before deployment:

```bash
git fetch origin main
git checkout main
git merge --ff-only origin/main
git status --short
SHA="$(git rev-parse HEAD)"
printf '%s\n' "$SHA"
```

`git status --short` must print nothing. Record the full SHA; every preparation, activation, rollback, and qualification command is bound to it.

## 2. Prepare the immutable release

Preparation downloads Python dependencies and creates an immutable release, but it does not change `/opt/telegram-llm/current`, install/refresh the active systemd unit, enable the service, restart it, or require secrets.

```bash
sudo ./deploy/install_pi.sh "$SHA" --prepare-only
```

Expected terminal state:

```text
PREPARED_REVISION=<SHA>
PREPARED_RELEASE=/opt/telegram-llm/releases/<SHA>
DEPLOYMENT_STATE=PREPARED_INACTIVE
```

This step is safe to complete before the public endpoint or credentials are ready.

## 3. Create the secret environment file

The file must be a regular file owned by `root:luke` with mode `0640`.

```bash
sudo install -d -m 0750 -o root -g luke /etc/telegram-llm
sudo touch /etc/telegram-llm/telegram-llm.env
sudo chown root:luke /etc/telegram-llm/telegram-llm.env
sudo chmod 0640 /etc/telegram-llm/telegram-llm.env
sudoedit /etc/telegram-llm/telegram-llm.env
```

Use `deploy/telegram-llm.env.example` as the field list. Required values are:

```text
TELEGRAM_TOKEN
TELEGRAM_ALLOWED_USER_ID
WEBHOOK_BASE_URL
WEBHOOK_SECRET_TOKEN
OPENAI_API_KEY
```

Do not put `APP_REVISION` or `DATABASE_PATH` in this file. Deployment owns those values separately so a secret-file edit cannot change source identity or move SQLite state.

Do not paste real credentials into GitHub issues, PRs, Actions logs, shell history, or this repository.

## 4. Establish public HTTPS ingress

Configure the separately selected ingress mechanism so the configured base URL sends:

```text
POST https://<public-base>/webhook
```

to:

```text
http://127.0.0.1:8787/webhook
```

`WEBHOOK_BASE_URL` is the base only and must not end with `/`; the application appends `/webhook` itself.

The startup preflight fails before contacting Telegram if the URL is not an absolute HTTPS URL, required credentials are absent, the revision is not a full Git SHA, or the SQLite state directory is not writable.

## 5. Activate the exact prepared revision

Run from the same clean `main` checkout and use the recorded SHA:

```bash
sudo ./deploy/install_pi.sh "$SHA"
```

Activation atomically selects the immutable release, writes `/etc/telegram-llm/revision.env`, installs the unit from that release, verifies it with `systemd-analyze`, enables and restarts the service, then requires local `/health` to report the exact SHA and healthy SQLite state.

Expected final lines:

```text
DEPLOYMENT_STATE=ACTIVE
HEALTH=PASS
REVISION=<SHA>
CURRENT_RELEASE=/opt/telegram-llm/releases/<SHA>
```

## 6. Run non-mutating local qualification

```bash
sudo ./deploy/qualify_pi.sh "$SHA"
```

Acceptance requires all of these simultaneously:

- host is `pi-guy`;
- exact immutable release marker and `current` symlink match the expected SHA;
- revision environment matches the SHA;
- secret-file metadata is `root:luke:0640` without reading/printing secret values;
- installed unit exactly matches the release unit;
- service is enabled and active as `luke`;
- exactly one listener exists on `127.0.0.1:8787` and none on wildcard/other addresses for that port;
- StateDirectory is `luke:luke:0700`;
- SQLite database exists;
- `/health` returns `status=ok`, `storage=ok`, and the expected SHA.

Expected result:

```text
LOCAL_PI_QUALIFICATION=PASS
```

## 7. Live Telegram/OpenAI acceptance

Local qualification does not prove public routing, Telegram delivery, or paid OpenAI execution. Complete these checks from the user's Telegram client after the local gate passes:

1. Send `/status`. It must return the expected `APP_REVISION`, configured OpenAI model, and `storage ok` without consuming an OpenAI model call.
2. Send a normal prompt such as `Reply exactly: FLIGHT-RELAY-OK`. The reply must arrive through Telegram and match the instruction.
3. Send `/search <a current factual query>`. It must return a current answer, proving the hosted web-search path.
4. Send `/weather Rome` (or another city) to prove the direct weather path.
5. Send `/pdf <public PDF URL>` to prove download, local extraction, OpenAI summarization, and Telegram document delivery.
6. Send a distinctive fact to remember, restart only `telegram-llm.service`, then ask for that fact. It must survive the process restart through SQLite.
7. Continue for enough turns to cross the configured compaction threshold, then ask about an early fact. The rolling summary must preserve the relevant information while raw history remains in SQLite.
8. Send `/new`, then verify prior context has been cleared.

A real host reboot is not part of the default acceptance procedure because it is disruptive. `systemctl is-enabled` plus service-process restart proves the configured boot-start contract without rebooting unrelated Pi workloads.

## Rollback

Rollback never downloads code. It can select only an already-installed immutable release whose marker matches the requested SHA.

```bash
sudo ./deploy/rollback_pi.sh <previous-40-character-sha>
```

The rollback helper restores the release's own unit, revision environment, and active symlink, restarts the service, and requires `/health` to report that exact previous SHA.

## Failure interpretation

- `PREFLIGHT_ERROR=...`: configuration or state directory is invalid; no application process starts.
- `TCP port 8787 is already in use before first activation`: investigate the listener; do not change the port ad hoc.
- systemd verification failure: repair the source unit before activation.
- local health fails after restart: inspect `systemctl status telegram-llm.service` and its journal; the installer prints both on failure.
- local qualification passes but Telegram messages do not arrive: investigate the public HTTPS route and Telegram webhook configuration before changing the application.
- Telegram delivery works but model prompts fail: investigate OpenAI credential/API errors without weakening the webhook or storage gates.

## Authority boundary

The deployment scripts are standalone host-admin tools. They are not Homebrew Remote Operator operations and must not be smuggled through its typed request protocol as arbitrary commands or paths. If remote managed deployment is desired later, that is a separate Homebrew integration project with its own reviewed operation/manifest and authority model.
