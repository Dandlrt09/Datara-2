"""Unit tests for base_url_guard."""

import ipaddress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.services.base_url_guard import (
    BaseUrlRejected,
    _BLOCKED_NETWORKS,
    _LOOPBACK_EXEMPT_PROVIDERS,
    validate_base_url,
)


class TestBaseUrlGuard:
    """Test the SSRF guard against the 8 spec scenarios."""

    @pytest.mark.asyncio
    async def test_custom_https_public(self):
        """GIVEN custom preset WHEN PUT https://api.example.com/v1 (public host) THEN saved."""
        # Mock DNS resolution to return a public IP
        with patch(
            "server.services.base_url_guard._resolve_hostname",
            return_value=[ipaddress.ip_address("93.184.216.34")],  # example.com
        ):
            # Should not raise
            await validate_base_url("https://api.example.com/v1", provider_type="custom")

    @pytest.mark.asyncio
    async def test_custom_http_rejected(self):
        """GIVEN custom preset WHEN PUT http://api.example.com/v1 THEN 422 invalid_base_url."""
        with patch(
            "server.services.base_url_guard._resolve_hostname",
            return_value=[ipaddress.ip_address("93.184.216.34")],
        ):
            with pytest.raises(BaseUrlRejected) as exc_info:
                await validate_base_url("http://api.example.com/v1", provider_type="custom")
            assert exc_info.value.code == "invalid_base_url"
            assert "HTTPS" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_custom_https_literal_private_ip_rejected(self):
        """GIVEN custom preset WHEN PUT https://192.168.1.5/v1 THEN 422."""
        # No DNS mock needed — literal IP
        with pytest.raises(BaseUrlRejected) as exc_info:
            await validate_base_url("https://192.168.1.5/v1", provider_type="custom")
        assert exc_info.value.code == "invalid_base_url"
        assert "locales" in exc_info.value.reason or "privadas" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_custom_dns_resolves_to_private_rejected(self):
        """GIVEN custom preset WHEN PUT https://internal.example.com that resolves to 10.0.0.5 THEN 422."""
        with patch(
            "server.services.base_url_guard._resolve_hostname",
            return_value=[ipaddress.ip_address("10.0.0.5")],
        ):
            with pytest.raises(BaseUrlRejected) as exc_info:
                await validate_base_url(
                    "https://internal.example.com/v1", provider_type="custom"
                )
            assert exc_info.value.code == "invalid_base_url"

    @pytest.mark.asyncio
    async def test_ollama_http_localhost_allowed(self):
        """GIVEN ollama preset WHEN PUT http://localhost:11434/v1 THEN saved."""
        # localhost resolves to 127.0.0.1 (loopback)
        with patch(
            "server.services.base_url_guard._resolve_hostname",
            return_value=[ipaddress.ip_address("127.0.0.1")],
        ):
            # Should not raise
            await validate_base_url("http://localhost:11434/v1", provider_type="ollama")

    @pytest.mark.asyncio
    async def test_lmstudio_http_127_allowed(self):
        """GIVEN lmstudio preset WHEN PUT http://127.0.0.1:1234/v1 THEN saved."""
        # Literal 127.0.0.1
        await validate_base_url("http://127.0.0.1:1234/v1", provider_type="lmstudio")

    @pytest.mark.asyncio
    async def test_custom_https_localhost_rejected(self):
        """GIVEN custom preset WHEN PUT https://localhost:8000/v1 THEN 422."""
        with patch(
            "server.services.base_url_guard._resolve_hostname",
            return_value=[ipaddress.ip_address("127.0.0.1")],
        ):
            with pytest.raises(BaseUrlRejected) as exc_info:
                await validate_base_url("https://localhost:8000/v1", provider_type="custom")
            assert exc_info.value.code == "invalid_base_url"

    @pytest.mark.asyncio
    async def test_ollama_http_lan_rejected(self):
        """GIVEN ollama preset WHEN PUT http://192.168.1.50:11434/v1 THEN 422."""
        with pytest.raises(BaseUrlRejected) as exc_info:
            await validate_base_url("http://192.168.1.50:11434/v1", provider_type="ollama")
        assert exc_info.value.code == "invalid_base_url"
        # LAN blocked even for ollama (only loopback exempt)

    # Additional edge‑case tests

    @pytest.mark.asyncio
    async def test_malformed_url(self):
        with pytest.raises(BaseUrlRejected) as exc_info:
            await validate_base_url("not-a-url", provider_type="custom")
        assert exc_info.value.code == "invalid_url"

    @pytest.mark.asyncio
    async def test_missing_scheme(self):
        with pytest.raises(BaseUrlRejected) as exc_info:
            await validate_base_url("example.com/v1", provider_type="custom")
        assert exc_info.value.code == "invalid_url"

    @pytest.mark.asyncio
    async def test_dns_error(self):
        with patch(
            "server.services.base_url_guard._resolve_hostname",
            side_effect=BaseUrlRejected("dns_error", "Could not resolve hostname: ..."),
        ):
            with pytest.raises(BaseUrlRejected) as exc_info:
                await validate_base_url("https://unresolvable.example.com/v1", provider_type="custom")
            assert exc_info.value.code == "dns_error"

    @pytest.mark.asyncio
    async def test_ipv6_loopback_allowed_for_ollama(self):
        await validate_base_url("http://[::1]:11434/v1", provider_type="ollama")

    @pytest.mark.asyncio
    async def test_ipv6_private_rejected(self):
        with pytest.raises(BaseUrlRejected) as exc_info:
            await validate_base_url("https://[fc00::1]/v1", provider_type="custom")
        assert exc_info.value.code == "invalid_base_url"

    @pytest.mark.asyncio
    async def test_multiple_ips_one_blocked_rejects(self):
        """If any resolved IP is blocked, the whole URL is rejected."""
        with patch(
            "server.services.base_url_guard._resolve_hostname",
            return_value=[
                ipaddress.ip_address("93.184.216.34"),
                ipaddress.ip_address("192.168.1.1"),  # blocked
            ],
        ):
            with pytest.raises(BaseUrlRejected) as exc_info:
                await validate_base_url("https://dual.example.com/v1", provider_type="custom")
            assert exc_info.value.code == "invalid_base_url"

    @pytest.mark.asyncio
    async def test_null_provider_type_treated_as_custom(self):
        """provider_type=None defaults to strictest rules (https, no loopback)."""
        # Should reject http
        with patch(
            "server.services.base_url_guard._resolve_hostname",
            return_value=[ipaddress.ip_address("93.184.216.34")],
        ):
            with pytest.raises(BaseUrlRejected) as exc_info:
                await validate_base_url("http://api.example.com/v1", provider_type=None)
            assert exc_info.value.code == "invalid_base_url"
        # Should reject localhost
        with patch(
            "server.services.base_url_guard._resolve_hostname",
            return_value=[ipaddress.ip_address("127.0.0.1")],
        ):
            with pytest.raises(BaseUrlRejected) as exc_info:
                await validate_base_url("https://localhost:8000/v1", provider_type=None)
            assert exc_info.value.code == "invalid_base_url"

    @pytest.mark.asyncio
    async def test_unknown_provider_type_treated_as_custom(self):
        """Unknown provider_type falls back to custom rules."""
        with patch(
            "server.services.base_url_guard._resolve_hostname",
            return_value=[ipaddress.ip_address("93.184.216.34")],
        ):
            with pytest.raises(BaseUrlRejected) as exc_info:
                await validate_base_url("http://api.example.com/v1", provider_type="unknown")
            assert exc_info.value.code == "invalid_base_url"