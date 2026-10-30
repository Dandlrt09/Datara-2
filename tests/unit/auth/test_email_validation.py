"""Email shape validation at the server boundary (S5).

The browser's ``type="email"`` is a convenience, not a defense: ``curl`` walks
past it. ``is_valid_email`` is the conservative server-side rule.
"""

import pytest

from server.services.auth_service import is_valid_email


class TestIsValidEmail:
    @pytest.mark.parametrize(
        "value",
        [
            "alice@example.com",
            "user+tag@example.com",
            "a.b_c-d@sub.example.co",
        ],
    )
    def test_accepts_well_formed_addresses(self, value):
        assert is_valid_email(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "notanemail",
            "a@",
            "@example.com",
            "a@b",
            "a b@example.com",
            "a@@example.com",
            "a@.com",
            "",
        ],
    )
    def test_rejects_malformed_addresses(self, value):
        assert is_valid_email(value) is False

    def test_rejects_overlong_address(self):
        local = "a" * 65
        assert is_valid_email(f"{local}@example.com") is False

    def test_rejects_more_than_254_chars(self):
        assert is_valid_email("a@" + "b" * 250 + ".com") is False
