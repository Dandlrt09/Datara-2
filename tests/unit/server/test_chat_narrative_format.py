"""Unit tests for the narrative number formatter (rigor-mov2).

Live validation found full-precision floats (e.g. 2500.8230981333336)
leaking into explanations despite the ≤6-decimals prompt rule; formatting
is now enforced deterministically by _format_narrative_numbers.
"""

from __future__ import annotations

from server.api.routers.chat import _format_narrative_numbers


class TestFormatNarrativeNumbers:
    def test_full_precision_float_capped_to_6(self):
        assert (
            _format_narrative_numbers("La media es 2500.8230981333336 segun el perfil.")
            == "La media es 2,500.823098 segun el perfil."
        )

    def test_fifteen_decimals_capped(self):
        assert (
            _format_narrative_numbers("El promedio exacto es 10.507123333333332 unidades.")
            == "El promedio exacto es 10.507123 unidades."
        )

    def test_comma_grouped_full_precision_capped(self):
        assert (
            _format_narrative_numbers("Total 1,500,000.12345678 verificado.")
            == "Total 1,500,000.123457 verificado."
        )

    def test_short_decimals_untouched(self):
        text = "El monto va de 5.0 a 5000.0 con media de 2500.82 y total 940741259.01."
        assert _format_narrative_numbers(text) == text

    def test_integers_and_identifiers_untouched(self):
        text = "1,500,000 filas; producto prod_004; fecha 2026-01-01."
        assert _format_narrative_numbers(text) == text

    def test_multipart_text_all_numbers_capped(self):
        original = "Aprox 2500.8230981333336.\n\nExacto: 3751234567.89012345."
        formatted = _format_narrative_numbers(original)
        assert "2500.8230981333336" not in formatted
        assert "3751234567.89012345" not in formatted
        assert "2,500.823098" in formatted
        assert "3,751,234,567.890123" in formatted

    def test_empty_text_passthrough(self):
        assert _format_narrative_numbers("") == ""
