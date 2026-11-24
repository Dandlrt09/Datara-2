"""Unit tests for the privacy redaction module (server/services/privacy.py)."""

import pytest

from server.services.privacy import (
    PrivacyError,
    effective_level,
    mask_value,
    redact_profile,
    stage_dataset_names,
    validate_level,
)


def _profile() -> dict:
    return {
        "columns": [
            {"name": "nombre", "dtype": "object"},
            {"name": "monto", "dtype": "float64"},
        ],
        "stats": {
            "nombre": {
                "null_count": 0,
                "unique_count": 2,
                "sample_values": ["Ana Pérez", "Luis Gómez"],
                "min": "Ana Pérez",
                "max": "Luis Gómez",
                "mean": None,
                "std": None,
            },
            "monto": {
                "null_count": 1,
                "unique_count": 2,
                "sample_values": [123.45, 67.0],
                "min": 67.0,
                "max": 123.45,
                "mean": 95.225,
                "std": 28.225,
            },
        },
        "sample": [
            {"nombre": "Ana Pérez", "monto": 123.45},
            {"nombre": "Luis Gómez", "monto": 67.0},
        ],
    }


class TestLevels:
    def test_unknown_level_raises(self):
        with pytest.raises(PrivacyError):
            validate_level("nope")

    def test_none_resolves_to_full(self):
        assert validate_level(None) == "full"

    def test_file_level_wins_over_session(self):
        assert effective_level("schema", "aggregates") == "schema"

    def test_session_level_is_the_fallback(self):
        assert effective_level(None, "masked") == "masked"

    def test_both_missing_uses_default(self):
        assert effective_level(None, None) == "full"


class TestFullLevel:
    def test_full_is_unchanged(self):
        payload = _profile()
        assert redact_profile(payload, "full") == payload

    def test_full_does_not_mutate_the_input(self):
        payload = _profile()
        redact_profile(payload, "masked")
        assert payload == _profile()


class TestAggregatesLevel:
    def test_aggregates_drops_sample_values_and_rows(self):
        redacted = redact_profile(_profile(), "aggregates")
        assert redacted["sample"] == []
        assert "sample_values" not in redacted["stats"]["nombre"]
        assert "sample_values" not in redacted["stats"]["monto"]

    def test_aggregates_keeps_the_aggregates(self):
        redacted = redact_profile(_profile(), "aggregates")
        assert redacted["stats"]["monto"]["mean"] == 95.225
        assert redacted["stats"]["monto"]["max"] == 123.45
        assert redacted["stats"]["nombre"]["null_count"] == 0


class TestSchemaLevel:
    def test_schema_keeps_only_columns(self):
        redacted = redact_profile(_profile(), "schema")
        assert redacted["columns"] == _profile()["columns"]
        assert redacted["stats"] == {}
        assert redacted["sample"] == []


class TestMaskedLevel:
    def test_masked_values_keep_their_shape(self):
        redacted = redact_profile(_profile(), "masked")
        assert redacted["stats"]["nombre"]["sample_values"] == [
            "Xxx Xxxxx",
            "Xxxx Xxxxx",
        ]
        assert redacted["stats"]["monto"]["sample_values"] == ["999.99", "99.9"]

    def test_masked_drops_disclosing_aggregates(self):
        redacted = redact_profile(_profile(), "masked")
        for key in ("min", "max", "mean", "std"):
            assert key not in redacted["stats"]["monto"]
            assert key not in redacted["stats"]["nombre"]

    def test_masked_keeps_counts(self):
        redacted = redact_profile(_profile(), "masked")
        assert redacted["stats"]["monto"]["null_count"] == 1
        assert redacted["stats"]["monto"]["unique_count"] == 2

    def test_masked_rows_are_masked(self):
        redacted = redact_profile(_profile(), "masked")
        assert redacted["sample"] == [
            {"nombre": "Xxx Xxxxx", "monto": "999.99"},
            {"nombre": "Xxxx Xxxxx", "monto": "99.9"},
        ]


class TestMaskValue:
    def test_none_stays_none(self):
        assert mask_value(None) is None

    def test_bool_is_masked(self):
        assert mask_value(True) == "***"

    def test_letters_keep_their_case(self):
        assert mask_value("Ana Pérez") == "Xxx Xxxxx"

    def test_digits_become_nines(self):
        assert mask_value(123.45) == "999.99"

    def test_negative_sign_survives(self):
        assert mask_value(-42) == "-99"


class TestAliases:
    def test_aliases_rename_columns_stats_and_sample(self):
        redacted = redact_profile(
            _profile(), "full", aliases={"nombre": "col_1", "monto": "col_2"}
        )
        assert [c["name"] for c in redacted["columns"]] == ["col_1", "col_2"]
        assert set(redacted["stats"]) == {"col_1", "col_2"}
        assert redacted["sample"][0] == {"col_1": "Ana Pérez", "col_2": 123.45}

    def test_unknown_source_column_raises(self):
        with pytest.raises(PrivacyError):
            redact_profile(_profile(), "full", aliases={"missing": "col_1"})

    def test_duplicate_alias_raises(self):
        with pytest.raises(PrivacyError):
            redact_profile(
                _profile(), "full", aliases={"nombre": "col_1", "monto": "col_1"}
            )

    def test_empty_alias_raises(self):
        with pytest.raises(PrivacyError):
            redact_profile(_profile(), "full", aliases={"nombre": "  "})


class TestStageDatasetNames:
    def test_paths_become_neutral_names(self):
        datasets = [
            {"filename": "clientes.xlsx", "format": "xlsx", "path": "/real/a.xlsx"},
            {"filename": "ventas.csv", "format": "csv", "path": "/real/b.csv"},
        ]
        outgoing, staged = stage_dataset_names(datasets)
        assert [d["path"] for d in outgoing] == ["dataset_1.xlsx", "dataset_2.csv"]
        assert [d["filename"] for d in outgoing] == ["clientes.xlsx", "ventas.csv"]
        assert staged == {
            "dataset_1.xlsx": "/real/a.xlsx",
            "dataset_2.csv": "/real/b.csv",
        }

    def test_no_absolute_path_survives(self):
        outgoing, _ = stage_dataset_names(
            [{"filename": "a.csv", "format": "csv", "path": "/secret/a.csv"}]
        )
        assert "/secret" not in str(outgoing)
