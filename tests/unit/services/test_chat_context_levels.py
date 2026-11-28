"""Unit tests for the chat context's stored-level resolution and the outgoing
sheet index (F6-advisories-2 S1, S5, S6, S9)."""

from __future__ import annotations

import asyncio
import logging

import pandas as pd

from server.services.chat_context import _resolve_level, _sheet_index_for
from server.services.privacy import CORRUPT_LEVEL_FALLBACK


class TestResolveLevel:
    def test_a_valid_file_level_wins_over_the_session(self):
        assert _resolve_level(7, "schema", "aggregates") == "schema"

    def test_a_corrupt_file_level_inherits_a_valid_session_level(self):
        # S1: an unknown file level falls back to the session level, which is
        # a level the user did declare.
        assert _resolve_level(7, "nope", "aggregates") == "aggregates"

    def test_a_corrupt_session_level_fails_closed(self):
        # S1: never ``full``.
        assert _resolve_level(7, None, "nope") == CORRUPT_LEVEL_FALLBACK
        assert _resolve_level(7, "also-nope", "nope") == CORRUPT_LEVEL_FALLBACK

    def test_a_corrupt_file_level_with_no_session_row_fails_closed(self):
        # S1: a missing session level is not a declaration of ``full``, so it
        # must not rescue a corrupt file level into disclosure.
        assert _resolve_level(7, "nope", None) == CORRUPT_LEVEL_FALLBACK

    def test_nothing_stored_and_nothing_corrupt_keeps_the_default(self):
        # The documented default is untouched by the fail-closed rule.
        assert _resolve_level(7, None, None) == "full"

    def test_the_warnings_name_the_file_and_the_fallback(self, caplog):
        # S5: both warnings identify the file and the fallback that applies.
        with caplog.at_level(
            logging.WARNING, logger="server.services.chat_context"
        ):
            assert _resolve_level(7, "nope", "also-nope") == CORRUPT_LEVEL_FALLBACK
        messages = [record.getMessage() for record in caplog.records]
        file_warning = next(m for m in messages if "invalid file" in m)
        session_warning = next(m for m in messages if "invalid session" in m)
        assert "file 7" in file_warning
        assert repr(CORRUPT_LEVEL_FALLBACK) in file_warning
        assert "file 7" in session_warning
        assert repr(CORRUPT_LEVEL_FALLBACK) in session_warning


class TestSheetIndexFor:
    @staticmethod
    def _workbook(tmp_path) -> str:
        path = tmp_path / "wb.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame({"a": [1]}).to_excel(
                writer, sheet_name="Resumen", index=False
            )
            pd.DataFrame({"b": [2]}).to_excel(
                writer, sheet_name="Ventas", index=False
            )
        return str(path)

    def test_the_index_is_the_workbook_position(self, tmp_path):
        row = {
            "id": 9,
            "format": "xlsx",
            "sheet_name": "Ventas",
            "storage_path": self._workbook(tmp_path),
        }
        assert asyncio.run(_sheet_index_for(row)) == 1

    def test_a_non_workbook_has_no_index(self):
        row = {"id": 9, "format": "csv", "sheet_name": None, "storage_path": "x"}
        assert asyncio.run(_sheet_index_for(row)) is None

    def test_a_vanished_label_or_an_unreadable_file_yields_none(self, tmp_path):
        # S9: the failure mode is a logged ``None``, never a raise.
        path = self._workbook(tmp_path)
        gone = {
            "id": 9,
            "format": "xlsx",
            "sheet_name": "Gone",
            "storage_path": path,
        }
        assert asyncio.run(_sheet_index_for(gone)) is None
        missing = {**gone, "storage_path": str(tmp_path / "missing.xlsx")}
        assert asyncio.run(_sheet_index_for(missing)) is None
