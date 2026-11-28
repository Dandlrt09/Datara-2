"""Unit tests for the privacy redaction module (server/services/privacy.py)."""

import pytest

from server.services.privacy import (
    PrivacyError,
    effective_level,
    mask_value,
    parse_aliases,
    redact_profile,
    stage_dataset_names,
    validate_aliases,
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
        # D2/S2: every number collapses to a fixed placeholder, whatever its
        # magnitude or digit count.
        assert redacted["stats"]["monto"]["sample_values"] == ["9.9", "9.9"]

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
            {"nombre": "Xxx Xxxxx", "monto": "9.9"},
            {"nombre": "Xxxx Xxxxx", "monto": "9.9"},
        ]


class TestMaskValue:
    def test_none_stays_none(self):
        assert mask_value(None) is None

    def test_bool_is_masked(self):
        assert mask_value(True) == "***"

    def test_letters_keep_their_case(self):
        assert mask_value("Ana Pérez") == "Xxx Xxxxx"

    def test_int_is_a_fixed_nine(self):
        assert mask_value(42) == "9"

    def test_float_is_a_fixed_nine_dot_nine(self):
        assert mask_value(123.45) == "9.9"

    def test_sign_is_dropped(self):
        assert mask_value(-42) == "9"

    def test_digit_count_is_not_disclosed(self):
        assert mask_value(1234567) == "9"

    def test_exponent_form_is_not_disclosed(self):
        assert mask_value(1e20) == "9.9"


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
    def test_paths_and_filenames_become_neutral_names(self):
        datasets = [
            {"filename": "clientes.xlsx", "format": "xlsx", "path": "/real/a.xlsx"},
            {"filename": "ventas.csv", "format": "csv", "path": "/real/b.csv"},
        ]
        outgoing, staged = stage_dataset_names(datasets)
        assert [d["path"] for d in outgoing] == ["dataset_1.xlsx", "dataset_2.csv"]
        # S1/D1: the real filename must not reach the provider either.
        assert [d["filename"] for d in outgoing] == ["dataset_1.xlsx", "dataset_2.csv"]
        assert staged == {
            "dataset_1.xlsx": "/real/a.xlsx",
            "dataset_2.csv": "/real/b.csv",
        }

    def test_no_absolute_path_survives(self):
        outgoing, _ = stage_dataset_names(
            [{"filename": "a.csv", "format": "csv", "path": "/secret/a.csv"}]
        )
        assert "/secret" not in str(outgoing)

    def test_no_real_filename_survives(self):
        outgoing, _ = stage_dataset_names(
            [
                {
                    "filename": "clientes-ACME.csv",
                    "format": "csv",
                    "path": "/real/clientes.csv",
                }
            ]
        )
        assert "clientes-ACME" not in str(outgoing)
        assert outgoing[0]["filename"] == "dataset_1.csv"


class TestParseAliases:
    def test_empty_raw_is_an_empty_map(self):
        assert parse_aliases(None) == {}
        assert parse_aliases("") == {}

    def test_invalid_json_is_ignored(self):
        assert parse_aliases("not json") == {}

    def test_non_dict_json_is_ignored(self):
        assert parse_aliases("[]") == {}

    def test_a_null_alias_entry_is_dropped_not_stringified(self):
        # S4/D4: never coerce JSON null into the string "None".
        assert parse_aliases('{"nombre": null}') == {}

    def test_a_malformed_entry_does_not_cost_the_valid_aliases(self):
        # S2: one corrupt entry used to make validate_aliases raise, which
        # discarded every good alias for that file. Only the bad entry goes.
        aliases = parse_aliases('{"nombre": "cliente", "monto": 5}')
        assert aliases == {"nombre": "cliente"}
        redacted = redact_profile(_profile(), "full", aliases=aliases)
        names = [column["name"] for column in redacted["columns"]]
        assert "cliente" in names
        assert "monto" in names

    def test_validate_aliases_still_rejects_a_null(self):
        # The write path keeps rejecting malformed values, so they cannot be
        # stored anew; only rows already stored are tolerated.
        with pytest.raises(PrivacyError):
            validate_aliases({"nombre": None}, ["nombre", "monto"])
