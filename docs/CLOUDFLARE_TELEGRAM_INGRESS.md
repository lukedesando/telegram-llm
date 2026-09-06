# Cloudflare Telegram Webhook Ingress

Status: **approved design; source controls prepared; Cloudflare control-plane changes not yet applied.**

## Purpose

Expose exactly one Telegram webhook endpoint to the Internet while keeping the relay itself loopback-bound and keeping Tailscale as the private operator/admin path.

This design reuses the existing Homebrew-owned remotely managed Cloudflare Tunnel connector on `pi-guy`. It does **not** create a second `cloudflared` service or move `telegram-llm` into Homebrew-managed application deployment.

## Approved architecture

```text
user phone
  -> Telegram
  -> Telegram Bot API webhook sender
  -> Cloudflare edge
       - DDoS/WAF
       - exact host/path/method/source-IP rule
       - path-specific Access bypass for /webhook only
  -> existing Homebrew Cloudflare Tunnel connector
  -> http://127.0.0.1:8787/webhook
  -> telegram-llm
       - public-Host route guard
       - X-Telegram-Bot-Api-Secret-Token validation
       - single authorized Telegram user ID
  -> OpenAI

operator phone/laptop
  -> Tailscale
  -> pi-guy administration
```

Cloudflare is the public Telegram transport. Tailscale is not part of Telegram message delivery.

## Fixed public endpoint

Use:

```text
https://telegram.desando.org/webhook
```

Production configuration therefore uses:

```text
WEBHOOK_BASE_URL=https://telegram.desando.org
```

`WEBHOOK_BASE_URL` is an origin only. It must not contain a path, query, fragment, credentials, or trailing slash. The application appends `/webhook` itself.

## Existing tunnel reuse

Homebrew's Cloudflare capability explicitly supports one remotely managed connector serving multiple application-specific hostnames. The accepted Auto Application production path already uses that connector for `apply.desando.org -> 127.0.0.1:8765`.

For this relay, add a second **Published application** route to the same tunnel:

```text
Hostname:    telegram.desando.org
Path:        ^/webhook$
Service URL: http://127.0.0.1:8787
```

Requirements:

- preserve the incoming public Host header; do not configure an `httpHostHeader` override;
- path routing must forward the full `/webhook` path unchanged;
- do not publish a wildcard or host-wide route to port 8787;
- do not expose port 8787 through the router or bind Uvicorn to a non-loopback interface;
- do not enable Tunnel-side Access JWT validation for this specific route, because the webhook path is intentionally an Access-bypassed machine endpoint and therefore will not carry an Access JWT.

## Why the webhook path cannot use normal Cloudflare Access

Telegram's Bot API can attach the configured webhook secret as:

```text
X-Telegram-Bot-Api-Secret-Token: <secret>
```

Telegram does not provide a mechanism for attaching Cloudflare's `CF-Access-Client-Id` and `CF-Access-Client-Secret` service-token headers. It therefore cannot complete either interactive Access authentication or normal Access Service Auth directly.

Cloudflare documents path-scoped **Bypass** policies for public webhook receivers. That is the required exception here. It is deliberately narrower than making the hostname generally public.

## Access policy contract

Keep the hostname deny-by-default, then create a more-specific path application for the webhook:

1. Host-level self-hosted Access application:

```text
telegram.desando.org
```

It remains deny-by-default for anything not covered by a more-specific rule.

2. More-specific self-hosted Access application:

```text
telegram.desando.org/webhook
```

Apply:

```text
Action:   Bypass
Include:  Everyone
```

Cloudflare's Access path precedence makes the more-specific `/webhook` application take precedence over the host-level application.

Important boundary: Bypass disables Access authentication and Access request logging for that path. It does **not** make the origin generally trusted. The WAF, tunnel path restriction, application public-Host guard, Telegram webhook secret, and Telegram user allowlist remain independent controls.

## WAF contract

Telegram's current official webhook documentation lists webhook source networks:

```text
149.154.160.0/20
91.108.4.0/22
```

Create a Cloudflare custom WAF rule for the Telegram hostname with **Block** action when any expected property is wrong:

```text
http.host eq "telegram.desando.org" and
(
  http.request.method ne "POST" or
  http.request.uri.path ne "/webhook" or
  not ip.src in {149.154.160.0/20 91.108.4.0/22}
)
```

This means the only traffic allowed past this rule for the hostname is an exact `POST /webhook` from Telegram's currently documented webhook source ranges.

Do not use an IP Access Rule with `Allow` for Telegram. Cloudflare documents that an IP Access `Allow` can bypass later WAF custom rules. Use the blocking custom rule above instead.

Telegram warns that its webhook source ranges may change. Re-check the official Telegram webhook documentation before flight qualification and whenever delivery unexpectedly stops.

## Application-side defense in depth

Even if the Cloudflare route is accidentally broadened later, `telegram-llm` treats the hostname derived from `WEBHOOK_BASE_URL` as a webhook-only public surface:

```text
public Host + POST /webhook -> may continue to webhook authentication
public Host + anything else -> 404
local/Tailscale Host          -> normal local operator routes remain available
```

The webhook then requires the configured Telegram secret using a constant-time comparison. A request that reaches the origin without the correct secret receives `403`.

`/health` remains a local qualification endpoint. It must not be intentionally published.

## Secret boundaries

Keep these values only in the reviewed Pi environment file:

```text
TELEGRAM_TOKEN
WEBHOOK_SECRET_TOKEN
OPENAI_API_KEY
```

Do not copy them into Cloudflare Access policy text, WAF expressions, GitHub, PRs, Actions logs, or chat transcripts.

The WAF relies on Telegram source networks and request shape; the application independently relies on the Telegram-generated secret header.

## Cloudflare control-plane acceptance

Before activating the relay, verify in Cloudflare that:

- the existing Homebrew tunnel connector is healthy;
- the published application route is exactly `telegram.desando.org` + `^/webhook$` -> `http://127.0.0.1:8787`;
- no origin Host override is configured;
- the host-level Access application is deny-by-default;
- the more-specific `/webhook` Access application has only the intended Bypass policy;
- the WAF blocking rule is active;
- no broader route to port 8787 exists.

## Runtime acceptance

After local Pi qualification passes:

1. `http://127.0.0.1:8787/health` must return the exact deployed revision and healthy storage.
2. `https://telegram.desando.org/health` must **not** return the local health payload.
3. A non-Telegram request to the public hostname should be blocked at Cloudflare.
4. A real Telegram message must reach the webhook and produce a bot reply.
5. Telegram delivery must continue through service restart and the remaining flight-acceptance tests in `PI_DEPLOYMENT.md`.

## Rollback

Application rollback remains independent of Cloudflare route rollback.

To remove public Telegram ingress without changing the local relay state:

1. disable/remove the `telegram.desando.org` published application route;
2. remove/disable the Telegram-host WAF rule;
3. remove/disable the path-specific `/webhook` Access application;
4. leave the existing Homebrew tunnel connector and unrelated `apply.desando.org` route unchanged.

This returns the relay to loopback/Tailscale-only reachability.

## Current external references

Re-check these before live control-plane changes:

- Telegram Bot API: `https://core.telegram.org/bots/api`
- Telegram webhook source networks: `https://core.telegram.org/bots/webhooks`
- Cloudflare Tunnel routing: `https://developers.cloudflare.com/tunnel/routing/`
- Cloudflare Tunnel configuration/path matching: `https://developers.cloudflare.com/tunnel/advanced/local-management/configuration-file/`
- Cloudflare Access application paths: `https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/`
- Cloudflare Access common policies / webhook Bypass: `https://developers.cloudflare.com/cloudflare-one/access-controls/policies/common-policies/`
- Cloudflare Access service tokens: `https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/`
- Cloudflare WAF custom rules: `https://developers.cloudflare.com/waf/custom-rules/`
