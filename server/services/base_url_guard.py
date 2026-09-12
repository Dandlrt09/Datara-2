"""SSRF guard for custom base_url values.

Validates that a provided base_url points to a public, reachable host and is not
a private/metadata IP address. Used at settings save time to block SSRF vectors.

Guard rules:
- All non‑local presets (openrouter, groq, custom) require https.
- ollama and lmstudio permit http (loopback exemption).
- The hostname is resolved (via DNS) to all A/AAAA records; **every** resolved IP
  must be public (i.e., not in any of the blocked private/metadata ranges).
- Loopback (127.0.0.0/8, ::1) is exempt only for provider_type ollama or lmstudio.
- All other blocked ranges reject every provider (including ollama/lmstudio).
"""

import asyncio
import ipaddress
import socket
from typing import List
from urllib.parse import urlparse

from fastapi import HTTPException


class BaseUrlRejected(Exception):
    """Raised by validate_base_url when the URL fails SSRF checks."""

    def __init__(self, code: str, reason: str):
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


# Blocked IP ranges (RFC 1918, RFC 4193, RFC 3927, loopback, link‑local)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # IPv4 loopback
    ipaddress.ip_network("10.0.0.0/8"),       # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),    # RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),   # RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),   # RFC 3927 link‑local
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # RFC 4193 unique‑local
    ipaddress.ip_network("fe80::/10"),        # RFC 4291 link‑local
]

# Provider types that permit loopback (http://localhost, http://127.0.0.1)
_LOOPBACK_EXEMPT_PROVIDERS = {"ollama", "lmstudio"}

# Provider types that require HTTPS
_HTTPS_REQUIRED_PROVIDERS = {"openrouter", "groq", "custom"}


async def _resolve_hostname(hostname: str) -> List[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve a hostname to all A/AAAA records via asyncio.to_thread.

    Returns a list of ipaddress objects. If the hostname is already a literal IP,
    returns that IP wrapped in the appropriate class.
    """
    # First, try parsing as an IP address
    try:
        ip = ipaddress.ip_address(hostname)
        return [ip]
    except ValueError:
        pass  # Not a literal IP, proceed with DNS

    # DNS lookup with getaddrinfo (blocking) → wrap in thread
    def _getaddrinfo_blocking():
        try:
            # Get all A/AAAA records (family=0, type=SOCK_STREAM)
            infos = socket.getaddrinfo(
                hostname, None, 0, socket.SOCK_STREAM, socket.IPPROTO_IP
            )
            # Extract IP strings
            ips = []
            for info in infos:
                # info[4] is (ip, port) for IPv4 or (ip, port, flowinfo, scopeid) for IPv6
                ip_str = info[4][0]
                try:
                    ips.append(ipaddress.ip_address(ip_str))
                except ValueError:
                    # Should not happen for a getaddrinfo result, but guard
                    continue
            return ips
        except socket.gaierror as e:
            raise BaseUrlRejected("dns_error", f"Could not resolve hostname: {e}")

    return await asyncio.to_thread(_getaddrinfo_blocking)


def _is_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address lies within any blocked network."""
    for net in _BLOCKED_NETWORKS:
        if ip in net:
            return True
    return False


async def validate_base_url(base_url: str, *, provider_type: str | None) -> None:
    """Validate that base_url is safe against SSRF attacks.

    Args:
        base_url: The full URL to validate (e.g., "https://api.example.com/v1").
        provider_type: One of "openrouter", "ollama", "lmstudio", "groq", "custom".
            If None, the guard assumes the strictest rules (https required,
            no loopback exemption).

    Raises:
        BaseUrlRejected: with `code` and `reason` fields if validation fails.
        HTTPException is NOT raised here — the caller should map BaseUrlRejected
        to an appropriate HTTP response.
    """
    # Parse URL
    try:
        parsed = urlparse(base_url)
    except Exception as e:
        raise BaseUrlRejected("invalid_url", f"Malformed URL: {e}")

    if not parsed.scheme:
        raise BaseUrlRejected("invalid_url", "Missing URL scheme")
    if not parsed.netloc:
        raise BaseUrlRejected("invalid_url", "Missing hostname")

    # Scheme validation
    effective_provider = provider_type or "custom"
    if effective_provider in _HTTPS_REQUIRED_PROVIDERS and parsed.scheme != "https":
        raise BaseUrlRejected(
            "invalid_base_url",
            "La URL base debe usar HTTPS y apuntar a un host público. "
            "No se permiten direcciones locales ni privadas."
        )

    # For ollama/lmstudio, allow http (loopback exemption will be checked later)
    if effective_provider in _LOOPBACK_EXEMPT_PROVIDERS:
        if parsed.scheme not in ("http", "https"):
            raise BaseUrlRejected("invalid_url", f"Unsupported scheme: {parsed.scheme}")
    else:
        if parsed.scheme != "https":
            raise BaseUrlRejected(
                "invalid_base_url",
                "La URL base debe usar HTTPS y apuntar a un host público. "
                "No se permiten direcciones locales ni privadas."
            )

    # Hostname resolution
    ips = await _resolve_hostname(parsed.hostname)

    # Check each resolved IP
    for ip in ips:
        if _is_ip_blocked(ip):
            # Determine if this is a loopback IP
            is_loopback = (
                (isinstance(ip, ipaddress.IPv4Address) and ip.is_loopback) or
                (isinstance(ip, ipaddress.IPv6Address) and ip.is_loopback)
            )
            if is_loopback and effective_provider in _LOOPBACK_EXEMPT_PROVIDERS:
                # Loopback is allowed for ollama/lmstudio
                continue
            # Blocked IP → reject
            raise BaseUrlRejected(
                "invalid_base_url",
                "La URL base debe usar HTTPS y apuntar a un host público. "
                "No se permiten direcciones locales ni privadas."
            )

    # All checks passed