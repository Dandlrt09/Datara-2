"""Unit tests for the preference normalizer (server/services/preferences.py)."""

from server.services.preferences import DEFAULTS, effective_preferences


class TestEffectivePreferences:
    def test_none_returns_defaults(self):
        assert effective_preferences(None) == DEFAULTS

    def test_stored_values_win(self):
        resolved = effective_preferences(
            {
                "number_format": "intl",
                "date_format": "absolute",
                "currency_symbol": "none",
                "open_behavior": "last_session",
            }
        )
        assert resolved == {
            "number_format": "intl",
            "date_format": "absolute",
            "currency_symbol": "none",
            "open_behavior": "last_session",
        }

    def test_null_columns_fall_back_to_defaults(self):
        resolved = effective_preferences(
            {
                "number_format": None,
                "date_format": None,
                "currency_symbol": None,
                "open_behavior": None,
            }
        )
        assert resolved == DEFAULTS

    def test_unknown_legacy_value_falls_back(self):
        """A value the API would reject today must not leak to readers."""
        resolved = effective_preferences(
            {"number_format": "fr", "currency_symbol": "ARS"}
        )
        assert resolved["number_format"] == "es"
        assert resolved["currency_symbol"] == "US$"

    def test_extra_store_keys_are_ignored(self):
        resolved = effective_preferences({"user_id": 1, "api_key_enc": None})
        assert resolved == DEFAULTS
