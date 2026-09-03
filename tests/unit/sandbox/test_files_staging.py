"""Sandbox file staging: session files must be readable by plain filename.

Regression for the first real chat run: generated code did
``pd.read_csv('orders.csv')`` (relative) and the sandbox cwd is a fresh
temp dir, so the read crashed with FileNotFoundError. The chat route now
stages session uploads into the sandbox cwd under their basename.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from server.services.sandbox_local import run_code


def test_run_code_stages_files_readable_by_basename():
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "orders.csv")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write("product,units\nEspresso,10\nFlat White,7\n")

        code = (
            "import pandas as pd\n"
            "df = pd.read_csv('orders.csv')\n"
            f"print('rows:', len(df))\n"
        )
        result = asyncio.run(
            run_code(code, files={"orders.csv": src}, limits={"timeout_seconds": 30})
        )

    assert result["status"] == "ok", result
    assert "rows: 2" in result["text"]


def test_run_code_without_files_still_clean():
    result = asyncio.run(
        run_code("print('hi')", limits={"timeout_seconds": 30})
    )
    assert result["status"] == "ok"
    assert result["text"].strip() == "hi"
