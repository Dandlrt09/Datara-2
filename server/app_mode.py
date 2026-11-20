"""Deployment mode (F1 / T1, D2).

``local`` is the packaged desktop app: one analyst on their own machine, no
email. ``hosted`` is the multi-user deployment with the email flows
(registration, verification, recovery). The mode is a property of the
*deployment*, not of the data, so it comes from the environment.

An unset variable means ``hosted``: bare ``uvicorn`` and the test suite keep
every email flow reachable. The desktop launcher is the one place that opts in
to ``local``.
"""

from __future__ import annotations

import os
from typing import Literal

Mode = Literal["local", "hosted"]

MODE_ENV = "DATARA_MODE"
_VALID: tuple[Mode, ...] = ("local", "hosted")


def get_mode() -> Mode:
    """Return the deployment mode; a typo raises instead of guessing."""
    raw = os.environ.get(MODE_ENV)
    if raw is None or not raw.strip():
        return "hosted"
    value = raw.strip().lower()
    if value not in _VALID:
        raise ValueError(
            f"{MODE_ENV} must be one of {', '.join(_VALID)}; got {raw!r}"
        )
    return value  # type: ignore[return-value]
