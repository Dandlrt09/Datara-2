"""The terms of use version cannot drift (terms-of-use D3).

The number the register route stamps into an account lives in
``server/services/terms.py``, while the text a person actually reads lives in
two markdown documents under ``web/src/content/terms``. Three places, one
number: this probe fails the moment a document is edited without bumping the
version, which is precisely the mistake no behavior test would notice.
"""

import re
from pathlib import Path

from server.services.terms import TERMS_VERSION

TERMS_DIR = Path(__file__).resolve().parents[2] / "web" / "src" / "content" / "terms"
DOCUMENTS = ("terms.es.md", "terms.en.md")

# "Versión:" in Spanish and "Version:" in English: one pattern covers both. It is
# anchored at the start of a line so the "Última actualización" date cannot match.
_VERSION_LINE = re.compile(r"^Versi[oó]n:\s*(\S+)\s*$", re.MULTILINE)


def _document(name: str) -> str:
    path = TERMS_DIR / name
    assert path.is_file(), f"missing terms document: {path}"
    return path.read_text(encoding="utf-8")


def _declared_version(name: str) -> str:
    match = _VERSION_LINE.search(_document(name))
    assert match, f"{name} declares no version line"
    return match.group(1)


def _section_numbers(name: str) -> list[str]:
    return re.findall(r"^## (\d+)\.", _document(name), re.MULTILINE)


class TestTermsDocuments:
    def test_every_document_declares_the_version_in_force(self):
        """D3: the version printed in the text is the one the server enforces."""
        for name in DOCUMENTS:
            assert _declared_version(name) == TERMS_VERSION, name

    def test_both_languages_carry_the_same_sections(self):
        """S4: a translation that drops a clause would be a different contract."""
        spanish, english = (_section_numbers(name) for name in DOCUMENTS)
        assert spanish == english

    def test_sections_are_numbered_without_gaps(self):
        """A silently removed section is the one edit nobody would read twice."""
        numbers = _section_numbers("terms.es.md")
        assert numbers == [str(index) for index in range(1, len(numbers) + 1)]
