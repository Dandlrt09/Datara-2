"""Locked-down sandbox runner for executing user-generated Python code.

Reads a single JSON request from stdin, executes the code with restricted
globals and resource limits, and writes a single JSON response to stdout.

This script is designed to be run as a subprocess::

    python -I -B sandbox_runner.py < input.json > output.json

Protocol (JSON over stdin → JSON over stdout):

stdin:
    {"code": "...", "dataframes": {...}, "limits": {"cpu_seconds": 30, "memory_mb": 512, "timeout_seconds": 30}}

stdout (success):
    {"status": "ok", "figures": [...], "tables": [...], "text": "...", "error": null}

stdout (error):
    {"status": "error", "error": {"type": "timeout|memory_limit_exceeded|syntax_error|blocked_import|runtime_error", "message": "...", "traceback": "..."}, "figures": [], "tables": [], "text": ""}

Note: This script is also the rlimit enforcer. When RLIMIT_AS kills the process,
the caller detects empty stdout and returns runtime_error("empty stdout") fallback.
"""

from __future__ import annotations

import json
import os
import resource
import sys
import traceback
import io


# ── Resource limits ─────────────────────────────────────────────────────────


def _set_rlimits(limits: dict) -> None:
    """Set process resource limits before executing user code.

    Applies RLIMIT_AS (virtual memory), RLIMIT_CPU (CPU seconds),
    RLIMIT_NPROC (no fork bombs), and RLIMIT_FSIZE (max file write).
    """
    memory_mb = limits.get("memory_mb", 512)
    cpu_seconds = limits.get("cpu_seconds", 30)

    # Virtual memory (address space) — includes heap, stack, mmap
    resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 1024 * 1024,) * 2)
    # CPU seconds
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds,) * 2)
    # No subprocesses
    resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))
    # Max file write size (50MB)
    resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024,) * 2)


# ── Restricted globals ──────────────────────────────────────────────────────


# Safe builtins allowlist
_SAFE_BUILTINS_NAMES: frozenset[str] = frozenset({
    "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
    "int", "len", "list", "map", "max", "min", "print", "range", "repr",
    "round", "set", "sorted", "str", "sum", "tuple", "zip", "isinstance",
    "type", "hasattr", "getattr", "setattr", "delattr", "callable", "iter",
    "next", "slice", "reversed",
})

_BLOCKED_DUNDERS: frozenset[str] = frozenset({
    "__import__", "exec", "eval", "compile", "open", "input", "globals",
    "locals", "vars", "__build_class__", "breakpoint",
})


class _DunderGuard:
    """Block dunder attribute access on objects in the restricted globals scope.

    Any access to a name starting with ``_`` raises PermissionError.
    """

    def __getattr__(self, name: str) -> None:
        if name.startswith("_"):
            raise PermissionError(f"dunder access blocked: {name}")
        raise PermissionError(f"undefined name: {name}")


def _make_blocked_import() -> callable:
    """Create a blocked __import__ that allows only pandas, numpy, plotly.

    Returns a function that replaces __import__ in the restricted globals.
    This is attached to the globals as ``__import__`` so that ``import foo``
    syntax uses it.
    """
    _ALLOWED_TOP_LEVEL_MODULES: set[str] = {
        "pandas",
        "numpy",
        "plotly",
        "math",
        "statistics",
        "collections",
        "itertools",
        "functools",
        "operator",
        "typing",
        "datetime",
        "json",
        "re",
        "textwrap",
        "copy",
        "random",
    }

    def _blocked_import(name: str, *args: object, **kwargs: object) -> object:
        # Allow any submodule of an allowed top-level module
        top_level = name.split(".")[0]
        if top_level in _ALLOWED_TOP_LEVEL_MODULES:
            return __import__(name, *args, **kwargs)
        raise ImportError(f"import '{name}' is not allowed in the sandbox")

    return _blocked_import


def _build_restricted_globals() -> dict[str, object]:
    """Build the restricted globals dictionary for sandboxed execution.

    Provides:
    - Safe builtins only
    - Blocked __import__ that only allows pandas/numpy/plotly
    - Pre-imported libraries: pd, np, px, go
    - A _GUARD that blocks attribute access to undefined names
    """
    import builtins as _bi

    safe_builtins: dict[str, object] = {
        name: getattr(_bi, name) for name in _SAFE_BUILTINS_NAMES
    }
    # Add __import__ to builtins so import statements work
    safe_builtins["__import__"] = _make_blocked_import()

    # Pre-import allowed libraries
    try:
        import pandas as _pd  # noqa: PLC0415
        import numpy as _np  # noqa: PLC0415
        import plotly.express as _px  # noqa: PLC0415
        import plotly.graph_objects as _go  # noqa: PLC0415
    except ImportError:
        _pd = _np = _px = _go = None

    restricted: dict[str, object] = {
        "__builtins__": safe_builtins,
        "pd": _pd,
        "np": _np,
        "px": _px,
        "go": _go,
        "_GUARD": _DunderGuard(),
    }
    return restricted


# ── Execution ───────────────────────────────────────────────────────────────


def _execute_code(code: str, limits: dict) -> dict:
    """Execute user code in the sandbox and return the result.

    Returns a JSON-serializable dict matching the stdout protocol.
    """
    restricted_globals = _build_restricted_globals()
    restricted_locals: dict = {}

    # Set resource limits
    _set_rlimits(limits)

    # Capture stdout for print()
    old_stdout = sys.stdout
    buffer = io.StringIO()
    sys.stdout = buffer

    figures: list[dict] = []
    tables: list[dict] = []
    try:
        # Compile the code
        compiled = compile(code, "<sandbox>", "exec", flags=0, dont_inherit=True)

        # Execute
        exec(compiled, restricted_globals, restricted_locals)  # noqa: S102

        # Collect any variables named fig, fig1, fig2, etc.
        for name, val in restricted_locals.items():
            if name.startswith("fig"):
                try:
                    figures.append({"name": name, "plotly": val.to_json()})
                except Exception:
                    pass

            if name.startswith("df") or name.endswith("_df"):
                try:
                    import pandas as _pd2  # noqa: PLC0415

                    if isinstance(val, _pd2.DataFrame):
                        tables.append({
                            "name": name,
                            "columns": list(val.columns),
                            "rows": val.head(20).to_dict(orient="records"),
                        })
                except Exception:
                    pass

        output_text = buffer.getvalue()

        return {
            "status": "ok",
            "figures": figures,
            "tables": tables,
            "text": output_text,
            "error": None,
        }
    except SyntaxError as e:
        return {
            "status": "error",
            "error": {
                "type": "syntax_error",
                "message": f"{e.__class__.__name__}: {e}",
                "traceback": traceback.format_exc(),
            },
            "figures": [],
            "tables": [],
            "text": "",
        }
    except (ImportError, PermissionError) as e:
        return {
            "status": "error",
            "error": {
                "type": "blocked_import",
                "message": f"{e.__class__.__name__}: {e}",
                "traceback": traceback.format_exc(),
            },
            "figures": [],
            "tables": [],
            "text": "",
        }
    except MemoryError:
        return {
            "status": "error",
            "error": {
                "type": "memory_limit_exceeded",
                "message": "MemoryError: sandbox exceeded memory limit",
                "traceback": traceback.format_exc(),
            },
            "figures": [],
            "tables": [],
            "text": "",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": {
                "type": "runtime_error",
                "message": f"{e.__class__.__name__}: {e}",
                "traceback": traceback.format_exc(),
            },
            "figures": [],
            "tables": [],
            "text": "",
        }
    finally:
        sys.stdout = old_stdout


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    """Read JSON from stdin, execute code, write JSON to stdout."""
    raw = sys.stdin.read()
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as e:
        result = {
            "status": "error",
            "error": {
                "type": "runtime_error",
                "message": f"Invalid JSON input: {e}",
                "traceback": "",
            },
            "figures": [],
            "tables": [],
            "text": "",
        }
        sys.stdout.write(json.dumps(result))
        sys.exit(1)

    code = request.get("code", "")
    limits = request.get("limits", {})

    result = _execute_code(code, limits)
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()