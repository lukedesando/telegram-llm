from __future__ import annotations

from urllib.parse import urlparse

WEBHOOK_PATH = "/webhook"


def normalize_hostname(value: str) -> str:
    """Normalize a Host header or parsed hostname for equality checks."""
    value = value.strip().lower().rstrip(".")
    if not value:
        return ""

    # Public webhook hosts are DNS names. Strip a conventional :port suffix
    # without trying to reinterpret IPv6 literals used by unrelated local tests.
    if value.count(":") == 1:
        host, port = value.rsplit(":", 1)
        if port.isdigit():
            value = host

    return value.rstrip(".")


def public_webhook_hostname(base_url: str) -> str:
    parsed = urlparse(base_url)
    return normalize_hostname(parsed.hostname or "")


def public_surface_allows(
    *,
    webhook_base_url: str,
    request_host: str,
    method: str,
    path: str,
) -> bool:
    """Allow only the Telegram webhook on the configured public hostname.

    Requests addressed to loopback/Tailscale/admin hostnames are not affected.
    Cloudflare is expected to preserve the original public Host header.
    """
    public_host = public_webhook_hostname(webhook_base_url)
    request_hostname = normalize_hostname(request_host)

    if not public_host or request_hostname != public_host:
        return True

    return method.upper() == "POST" and path == WEBHOOK_PATH
