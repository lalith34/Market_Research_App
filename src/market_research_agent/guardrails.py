"""Safety guardrails for the agent.

Two concerns for an agent that researches arbitrary targets and fetches
model-chosen URLs:

1. Input validation — keep the target a sane, bounded string.
2. SSRF protection — the LLM (or a poisoned search result) must not be able to
   make the fetch tool hit internal/cloud-metadata endpoints. `is_safe_url`
   resolves the host and rejects anything that isn't a public address.

Prompt-injection of fetched page *content* is mitigated separately, in the
research prompt (fetched text is treated as untrusted data, not instructions).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

MAX_TARGET_LEN = 200

# Hostnames that are never legitimate research targets for fetch_page.
_BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost")
_BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}


class GuardrailError(ValueError):
    """Raised when input fails a guardrail check."""


def validate_target(target: str) -> str:
    """Validate and normalize the research target. Raises GuardrailError."""
    t = (target or "").strip()
    if not t:
        raise GuardrailError(
            "Target must be a non-empty company, product, or market category."
        )
    if len(t) > MAX_TARGET_LEN:
        raise GuardrailError(
            f"Target is too long ({len(t)} chars; max {MAX_TARGET_LEN})."
        )
    # Reject control characters (newlines/tabs/etc.) that could be used to smuggle
    # extra instructions into prompts built from the target.
    if any(ord(c) < 32 for c in t):
        raise GuardrailError("Target contains invalid control characters.")
    return t


def is_safe_url(url: str) -> tuple[bool, str]:
    """Return (ok, reason). Blocks non-http(s) schemes and non-public addresses.

    Resolves the hostname via DNS and rejects the URL if *any* resolved address
    is private, loopback, link-local, reserved, multicast, or unspecified — the
    classic SSRF targets (127.0.0.1, 10/172.16/192.168, 169.254.169.254, etc.).
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:  # pragma: no cover - urlparse is very tolerant
        return False, f"unparseable URL: {exc}"

    if parsed.scheme not in ("http", "https"):
        return False, f"blocked scheme {parsed.scheme or '(none)'!r} (only http/https)"

    host = parsed.hostname
    if not host:
        return False, "URL has no host"

    host_l = host.lower()
    if host_l in _BLOCKED_HOSTS or host_l.endswith(_BLOCKED_HOST_SUFFIXES):
        return False, f"blocked internal host {host!r}"

    # If the host is a literal IP, check it directly; otherwise resolve it.
    try:
        addrs = [ipaddress.ip_address(host_l)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            return False, f"DNS resolution failed: {exc}"
        addrs = []
        for info in infos:
            try:
                addrs.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                continue
        if not addrs:
            return False, "no resolvable IP address"

    for addr in addrs:
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return False, f"blocked non-public address {addr}"

    return True, "ok"
