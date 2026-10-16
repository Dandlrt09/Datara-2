"""Architecture fitness test: the client mirror of the D6 model gate is LAW.

The provider-aware model gate (D6) exists on both sides of the wire:

- server — the real gate. ``allowed_models_for_provider`` decides at chat time
  whether a model id must be in the curated whitelist;
- web — a UI mirror so the wizard and the settings hub render the same model
  list the server will accept.

Both encode the same fact. Editing one side alone silently re-introduces the
D6 dead-end — an unrestricted provider starts filtering its live catalog
against OpenRouter slugs, leaving no selectable model — and no behavior test
covers the pair. This test reads the mirror's declaration and fails the build
when the two sets differ, turning the invariant into an enforced one.
"""

from __future__ import annotations

import re
from pathlib import Path

from server.api.routers import settings as settings_module

REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_GATE_TS = REPO_ROOT / "web" / "src" / "routes" / "settings" / "modelGate.ts"

# Anchored on the exported declaration: a rename or reshape of the mirror must
# fail loudly here instead of matching nothing and passing vacuously.
_DECL_RE = re.compile(
    r"export\s+const\s+UNRESTRICTED_PROVIDERS\s*=\s*new\s+Set\(\[(?P<body>[^\]]*)\]\)",
)
_LITERAL_RE = re.compile(r"""["']([^"']+)["']""")


def _client_unrestricted_providers() -> set[str]:
    """Parse the provider ids declared in the web mirror."""
    source = MODEL_GATE_TS.read_text(encoding="utf-8")
    match = _DECL_RE.search(source)
    assert match is not None, (
        "modelGate.ts no longer declares "
        "`export const UNRESTRICTED_PROVIDERS = new Set([...])`; update this "
        "guard together with the file."
    )
    return set(_LITERAL_RE.findall(match.group("body")))


def test_client_model_gate_mirrors_server_gate():
    """The web mirror and the server gate must name the same providers."""
    server = set(settings_module._UNRESTRICTED_PROVIDERS)
    client = _client_unrestricted_providers()

    assert client == server, (
        "The web model gate mirror drifted from the server gate.\n"
        f"  server/api/routers/settings.py: {sorted(server)}\n"
        f"  web/src/routes/settings/modelGate.ts: {sorted(client)}\n"
        "Update both sides; the parity guard then stays green."
    )
