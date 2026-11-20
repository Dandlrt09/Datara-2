"""The SPA must not be able to go stale in the browser.

Bug history: the built frontend was served with only ``last-modified``/``etag``
and no ``Cache-Control``, so browsers fell back to their own heuristic and kept
the old ``index.html`` -- which is the file that names the old hashed bundles.
A deploy was therefore invisible to the analyst until they forced a hard reload;
it was found during F4's live validation.

The rule the server now states, and what these tests pin:

* name-stable files -- ``index.html`` above all, and every client route that
  falls back to it -- must be REVALIDATED (``no-cache``: keep it, but ask),
  which costs a 304 thanks to the existing ETag and never hides a deploy;
* hashed build output under ``assets/`` may be cached FOREVER
  (``max-age=31536000, immutable``): if the content changes, Vite changes the
  name, so a stale entry can never be served.
"""

from __future__ import annotations

import glob
import os

import pytest
from fastapi.testclient import TestClient

from server.api.main import app

REVALIDATE = "no-cache"
IMMUTABLE = "public, max-age=31536000, immutable"


def _client(tmp_path, monkeypatch) -> TestClient:
    """A client whose lifespan boots against its own throwaway database."""
    monkeypatch.setenv("DATARA_DB_PATH", str(tmp_path / "spa-cache" / "datara.db"))
    return TestClient(app)


def _require_build() -> None:
    if not os.path.exists("web/dist/index.html"):
        pytest.skip("frontend not built in this environment; nothing to assert")


def _a_hashed_asset() -> str:
    """One real build artifact, by its repository-relative path."""
    for candidate in sorted(glob.glob("web/dist/assets/*")):
        if os.path.isfile(candidate):
            return candidate.replace("web/dist/", "")
    pytest.skip("no hashed assets in web/dist in this environment")


def test_the_shell_is_revalidated(tmp_path, monkeypatch):
    _require_build()

    with _client(tmp_path, monkeypatch) as client:
        resp = client.get("/")

    assert resp.status_code == 200
    assert 'id="root"' in resp.text
    assert resp.headers.get("cache-control") == REVALIDATE


def test_a_client_route_falling_back_to_the_shell_is_revalidated(tmp_path, monkeypatch):
    _require_build()

    with _client(tmp_path, monkeypatch) as client:
        resp = client.get("/app/files")

    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == REVALIDATE


def test_hashed_assets_may_be_cached_forever(tmp_path, monkeypatch):
    _require_build()
    asset = _a_hashed_asset()

    with _client(tmp_path, monkeypatch) as client:
        resp = client.get(f"/{asset}")

    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == IMMUTABLE


def test_a_missing_asset_is_not_marked_immutable(tmp_path, monkeypatch):
    """The header must describe what was SERVED, not what was asked for.

    A missing ``assets/...`` path falls back to the shell; marking that answer
    ``immutable`` would freeze a copy of ``index.html`` under a URL the next
    build could legitimately reuse.
    """
    _require_build()

    with _client(tmp_path, monkeypatch) as client:
        resp = client.get("/assets/does-not-exist-anywhere.js")

    assert resp.status_code == 200
    assert 'id="root"' in resp.text
    assert resp.headers.get("cache-control") == REVALIDATE
