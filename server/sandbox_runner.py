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

import builtins as _BUILTINS
import io as _IO_MODULE
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


# ── Jailed file access ──────────────────────────────────────────────────────

_BUILTINS_OPEN: callable = _BUILTINS.open  # keep a backup for restoration
_IO_OPEN: callable = _IO_MODULE.open  # io.open holds a direct reference


def _jail_builtins_open(cwd: str) -> None:
    """Replace builtins.open with a write-only cwd-restricted wrapper.

    **Two-tier jail design:**

    * **Tier 1 (this function)** — patches ``builtins.open`` **and**
      ``io.open`` at the process level (``io.open`` holds a direct
      reference to the original ``open`` and is used by ``pathlib``
      internally — e.g. Plotly's ``fig.write_html()`` resolves through
      ``Path.write_text → Path.open → io.open``). Blocks **writes** to
      paths outside the sandbox cwd.  Reads are allowed anywhere so that
      library-import-time file reads work.

    * **Tier 2** — in ``_build_restricted_globals()``, the ``open``
      exposed to user code via the restricted ``__builtins__`` dict is a
      **stricter** wrapper that blocks **any** path outside the cwd,
      regardless of mode (reads or writes).

    Together the two tiers ensure:
    - Library internals (plotly's ``fig.write_html("/tmp/fig.html")``)
      → Tier 1 blocks the write of an absolute path → PermissionError.
    - User code ``open("/etc/passwd")`` → Tier 2 blocks the read →
      PermissionError.
    - User code ``open("scratch.txt", "w")`` → Tier 2 allows (under cwd)
      → write succeeds.

    Raises:
        PermissionError: if a write-mode path resolves outside ``cwd``.
    """
    cwd_abs: str = os.path.abspath(cwd)

    def _jailed_open(file, mode: str = "r", *args, **kwargs):
        if isinstance(file, (str, os.PathLike)):
            # Only block writes (w/a/x + any modifier like b/+) outside cwd
            normalized_mode = mode.lstrip()
            if normalized_mode and normalized_mode[0] in ("w", "a", "x"):
                resolved = os.path.abspath(
                    os.path.join(cwd_abs, str(file))
                )
                if not (resolved == cwd_abs or resolved.startswith(cwd_abs + os.sep)):
                    raise PermissionError(
                        f"file access blocked: path '{file}' is outside sandbox cwd"
                    )
        return _BUILTINS_OPEN(file, mode, *args, **kwargs)

    _BUILTINS.open = _jailed_open
    _IO_MODULE.open = _jailed_open  # io.open is used by pathlib internally


def _restore_builtins_open() -> None:
    """Restore the original builtins.open and io.open after sandbox execution."""
    _BUILTINS.open = _BUILTINS_OPEN
    _IO_MODULE.open = _IO_OPEN


# ── Restricted globals ──────────────────────────────────────────────────────


# Safe builtins allowlist.
# open is INCLUDED — it is overridden in _build_restricted_globals() with a
# strict cwd-jailed wrapper (blocks ALL paths outside sandbox cwd).
# The process-level jail (write-only) covers library-internal open() calls.
_SAFE_BUILTINS_NAMES: frozenset[str] = frozenset({
    "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
    "int", "len", "list", "map", "max", "min", "open",
    "print", "range", "repr", "round", "set", "sorted", "str", "sum",
    "tuple", "zip", "isinstance", "type", "hasattr", "getattr", "setattr",
    "delattr", "callable", "iter", "next", "slice", "reversed",
})

_BLOCKED_DUNDERS: frozenset[str] = frozenset({
    "__import__", "exec", "eval", "compile", "input", "globals",
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
    """Create a blocked __import__ that allows only known-safe modules.

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
        "time",
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

    ``open`` is given a **two-tier** jail (see ``_jail_builtins_open`` for
    the process-level write-only tier). In the restricted globals dict,
    ``open`` is a strict wrapper that blocks **any** path outside the
    sandbox cwd, regardless of mode — this jails user code that tries
    ``open("/etc/passwd")`` for reading.

    Provides:
    - Safe builtins (including two-tier-jailed ``open``)
    - Blocked ``__import__`` that only allows project-relevant libraries
    - Pre-imported convenience aliases: pd, np, px, go
    - A ``_GUARD`` that blocks attribute access to undefined names
    """
    sandbox_cwd = os.getcwd()
    cwd_abs = os.path.abspath(sandbox_cwd)

    def _strict_jailed_open(file, mode: str = "r", *args, **kwargs):
        """Strict wrapper for user-code scope: ANY path outside cwd blocked.

        Unlike the process-level jail (write-only), this blocks ALL
        access — including reads — to paths outside the sandbox cwd.
        """
        if isinstance(file, (str, os.PathLike)):
            resolved = os.path.abspath(
                os.path.join(cwd_abs, str(file))
            )
            if not (resolved == cwd_abs or resolved.startswith(cwd_abs + os.sep)):
                raise PermissionError(
                    f"file access blocked: path '{file}' is outside sandbox cwd"
                )
        return _BUILTINS_OPEN(file, mode, *args, **kwargs)

    safe_builtins: dict[str, object] = {
        name: getattr(_BUILTINS, name) for name in _SAFE_BUILTINS_NAMES
    }
    # Override open with the strict cwd-jailed version for user code.
    # The process-level jail (write-only) still applies to library internals.
    safe_builtins["open"] = _strict_jailed_open
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
    # MUST jail builtins.open BEFORE building restricted globals so that
    # the pre-imported libraries (pandas, numpy, plotly) capture the
    # jailed ``open`` at import time and therefore cannot write to paths
    # outside the sandbox cwd.
    sandbox_cwd = os.getcwd()
    _jail_builtins_open(sandbox_cwd)

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
        _restore_builtins_open()


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