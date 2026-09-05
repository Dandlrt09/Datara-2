"""Architecture fitness test: the store boundary is LAW.

The planned Supabase migration (roadmap Fase 5) is only cheap if ALL
persistence lives behind ``server/services/sqlite_store.py``. These
tests fail the build the moment ``sqlite3`` imports or raw SQL string
literals appear outside the sanctioned modules — turning the "never
leak SQLite outside the store" rule from reviewer discipline into an
enforced invariant.
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# The ONLY modules allowed to import sqlite3 or write SQL literals.
SANCTIONED: set[str] = {
    "server/services/sqlite_store.py",
    "server/migrate.py",  # schema migrations
}

_SCAN_ROOTS = ("server", "core")

# A string is "SQL-looking" when it pairs a DML verb with a DML keyword:
# SELECT ... FROM, INSERT ... INTO/VALUES, UPDATE ... SET, DELETE ... FROM.
_SQL_RE = re.compile(
    r"\b(select|insert|update|delete)\b[\s\S]*\b(from|into|set|values)\b",
    re.IGNORECASE,
)


def _iter_py_files():
    for root in _SCAN_ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            yield path.relative_to(REPO_ROOT).as_posix(), path


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Node ids of module/class/function docstrings (prose, not SQL)."""
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    return docstrings


def _violations(source: str) -> list[str]:
    """Return human-readable violations for one module's source."""
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    reasons: list[str] = []

    def _sql_hit(text: str) -> bool:
        return bool(_SQL_RE.search(text))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "sqlite3":
                    reasons.append(f"line {node.lineno}: import sqlite3")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "sqlite3":
                reasons.append(f"line {node.lineno}: from sqlite3 import ...")
        elif isinstance(node, ast.JoinedStr):
            # f-string: DML keywords may split across literal parts
            # (f"SELECT {cols} FROM users"), so test the joined prose.
            joined = "".join(
                part.value
                for part in node.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
            if _sql_hit(joined):
                reasons.append(f"line {node.lineno}: raw SQL in f-string")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Docstrings are prose, not SQL.
            if id(node) not in docstrings and _sql_hit(node.value):
                reasons.append(f"line {node.lineno}: raw SQL literal")
    return reasons


class TestStoreBoundary:
    def test_no_sqlite3_or_raw_sql_outside_store(self):
        offenders: list[str] = []
        for rel, path in _iter_py_files():
            if rel in SANCTIONED:
                continue
            for reason in _violations(path.read_text(encoding="utf-8")):
                offenders.append(f"{rel}: {reason}")
        assert not offenders, "Store boundary violated:\n" + "\n".join(offenders)

    def test_detector_catches_offenders(self):
        """Canary: the detector must flag known-bad code, so this suite
        cannot silently rot into a no-op."""
        assert _violations("import sqlite3\nconn = sqlite3.connect('x')\n")
        assert _violations('QUERY = "SELECT id FROM users"\n')
        assert _violations('QUERY = f"SELECT {cols} FROM users WHERE x = ?"\n')
        # Prose and non-SQL strings must NOT be flagged.
        assert not _violations('MSG = "invalid SELECTION text in column"\n')
        assert not _violations('HINT = "rows deleted so far: none"\n')

    def test_events_module_no_sqlite3(self):
        """The new events module must not import sqlite3 or contain SQL
        literals — the store boundary is law [R2]."""
        events_py = REPO_ROOT / "server" / "services" / "events.py"
        if not events_py.exists():
            pytest.skip("events.py not yet created")
        violations = _violations(events_py.read_text(encoding="utf-8"))
        assert not violations, (
            f"server/services/events.py violates store boundary:\n"
            + "\n".join(violations)
        )
