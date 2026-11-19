"""Integration tests for the deployment-mode endpoint (F1 / T1, D2).

The mode is a property of the *deployment*, read from ``DATARA_MODE``, never of
the data. The endpoint is unauthenticated on purpose: the frontend needs it
before any login to decide which screens exist.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers.app_config import router as app_config_router
from server.app_mode import get_mode


@pytest.fixture
def client():
    application = FastAPI()
    application.include_router(app_config_router)
    return TestClient(application)


class TestGetMode:
    def test_unset_defaults_to_hosted(self, monkeypatch):
        """Bare uvicorn and the test suite keep every email flow reachable."""
        monkeypatch.delenv("DATARA_MODE", raising=False)
        assert get_mode() == "hosted"

    @pytest.mark.parametrize("value", ["local", "hosted"])
    def test_explicit_value_is_honoured(self, monkeypatch, value):
        monkeypatch.setenv("DATARA_MODE", value)
        assert get_mode() == value

    def test_value_is_normalised(self, monkeypatch):
        monkeypatch.setenv("DATARA_MODE", "  LOCAL ")
        assert get_mode() == "local"

    def test_unknown_value_fails_loudly(self, monkeypatch):
        """A typo must not silently pick a mode that hides or shows auth."""
        monkeypatch.setenv("DATARA_MODE", "locla")
        with pytest.raises(ValueError, match="DATARA_MODE"):
            get_mode()


class TestAppConfigEndpoint:
    def test_reports_the_mode_without_credentials(self, client, monkeypatch):
        monkeypatch.setenv("DATARA_MODE", "local")

        response = client.get("/api/app-config")

        assert response.status_code == 200
        assert response.json() == {"mode": "local"}

    def test_default_is_hosted(self, client, monkeypatch):
        monkeypatch.delenv("DATARA_MODE", raising=False)

        assert client.get("/api/app-config").json() == {"mode": "hosted"}
