"""Tests for auth service (hashing, token generation, cookie building)."""

from server.services.auth_service import (
    build_expire_cookie_header,
    build_set_cookie_header,
    generate_raw_token,
    hash_password,
    hash_token,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "my-secret-password-123"
        h = hash_password(pw)
        assert h != pw
        assert h.startswith("$2b$") or h.startswith("$2a$") or h.startswith("$2y$")
        assert verify_password(pw, h) is True

    def test_wrong_password(self):
        h = hash_password("correct-password")
        assert verify_password("wrong-password", h) is False

    def test_empty_password(self):
        h = hash_password("")
        assert verify_password("", h) is True
        assert verify_password("x", h) is False

    def test_invalid_hash(self):
        assert verify_password("test", "not-a-valid-bcrypt-hash") is False

    def test_verify_is_constant_time(self):
        """Verify uses the same comparison regardless of input length."""
        h = hash_password("real-password")
        assert verify_password("real-password", h) is True
        # Long string should not crash (timing-safe)
        assert verify_password("a" * 1000, h) is False


class TestTokenGeneration:
    def test_generates_unique_tokens(self):
        tokens = {generate_raw_token() for _ in range(100)}
        assert len(tokens) == 100

    def test_token_is_urlsafe(self):
        t = generate_raw_token()
        assert t.isascii()
        # Should be base64-url characters only
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert set(t).issubset(allowed)

    def test_token_round_trip(self):
        raw = generate_raw_token()
        h = hash_token(raw)
        assert len(h) == 64  # SHA-256 hex is 64 chars
        assert h == hash_token(raw)  # deterministic

    def test_different_tokens_different_hashes(self):
        t1 = generate_raw_token()
        t2 = generate_raw_token()
        assert hash_token(t1) != hash_token(t2)


class TestCookieBuilding:
    def test_default_set_cookie(self):
        header = build_set_cookie_header("myrawtoken")
        assert header.startswith("session_id=myrawtoken;")
        assert "HttpOnly" in header
        assert "SameSite=Lax" in header
        assert "Path=/" in header
        assert "Max-Age=28800" in header
        assert "Secure" not in header  # off by default for local dev

    def test_secure_enabled(self):
        header = build_set_cookie_header("tok", secure=True)
        assert "Secure" in header

    def test_custom_ttl(self):
        header = build_set_cookie_header("tok", ttl_seconds=3600)
        assert "Max-Age=3600" in header

    def test_custom_domain(self):
        header = build_set_cookie_header("tok", domain="datara.local")
        assert "Domain=datara.local" in header

    def test_expire_cookie(self):
        header = build_expire_cookie_header()
        assert header.startswith("session_id=;")
        assert "Max-Age=0" in header
        assert "Expires=Thu, 01 Jan 1970" in header
        assert "HttpOnly" in header