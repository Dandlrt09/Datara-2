"""Architecture fitness test: the curated model catalog is LAW on both sides.

The recommended OpenRouter/Groq catalog is hand-curated data written down twice:

- web — ``web/src/routes/settings/recommended.ts`` holds the labels, the tiers
  and the USD-per-1M prices the analyst actually reads (``priceLabel``);
- server — ``server/api/routers/settings.py`` holds the accepted slugs
  (``_RECOMMENDED_MODELS``) and ``server/services/llm_openai.py`` holds the
  per-token rates ``_estimate_cost`` multiplies by a token count.

Editing one side alone stays invisible: the wizard keeps recommending a model
the server prices with the old number, or the analyst reads one price while the
backend estimates another. A ``tier: "free"`` entry with a non-zero price is
worse: ``priceLabel`` prints "Gratis" and the backend still charges. No behavior
test covers these pairs, so this guard reads the TypeScript catalog and fails
the build when the two sides disagree — the same pattern
``test_model_gate_parity.py`` already uses for the D6 model gate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from server.api.routers import settings as settings_module
from server.services.llm_openai import _MODEL_COST_MAP, _PROVIDER_SCOPED_RATES

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_TS = (
    REPO_ROOT / "web" / "src" / "routes" / "settings" / "recommended.ts"
)

# Anchored on the exported declaration and its closing line: a rename or a
# reshape of the catalog must fail loudly here instead of matching nothing and
# passing vacuously.
_DECL_RE = re.compile(
    r"export\s+const\s+RECOMMENDED_MODELS\s*:\s*RecommendedModel\[\]\s*=\s*\["
    r"(?P<body>.*?)\n\];",
    re.S,
)
_ENTRY_RE = re.compile(r"\{(?P<entry>[^{}]*)\}", re.S)
_FIELD_RES = {
    "model": re.compile(r"\bmodel:\s*\"([^\"]+)\""),
    "provider": re.compile(r"\bprovider:\s*\"([^\"]+)\""),
    "tier": re.compile(r"\btier:\s*\"([^\"]+)\""),
    "input": re.compile(r"\binputUsdPerMillion:\s*([0-9]+(?:\.[0-9]+)?)"),
    "output": re.compile(r"\boutputUsdPerMillion:\s*([0-9]+(?:\.[0-9]+)?)"),
}


def _catalog_entries() -> list[dict[str, object]]:
    """Parse the shipped TypeScript catalog into plain rows."""
    source = CATALOG_TS.read_text(encoding="utf-8")
    match = _DECL_RE.search(source)
    assert match is not None, (
        "recommended.ts no longer declares "
        "`export const RECOMMENDED_MODELS: RecommendedModel[] = [...]`; "
        "update this guard together with the file."
    )
    entries: list[dict[str, object]] = []
    for block in _ENTRY_RE.finditer(match.group("body")):
        text = block.group("entry")
        fields: dict[str, str] = {}
        for name, pattern in _FIELD_RES.items():
            found = pattern.search(text)
            assert found is not None, (
                f"recommended.ts entry is missing `{name}`: {text.strip()[:120]}"
            )
            fields[name] = found.group(1)
        entries.append(
            {
                "model": fields["model"],
                "provider": fields["provider"],
                "tier": fields["tier"],
                "input": float(fields["input"]),
                "output": float(fields["output"]),
            }
        )
    # A zero-row parse would make the price and tier checks below pass without
    # looking at anything; the catalog always ships several entries.
    assert len(entries) >= 2, (
        f"parsed {len(entries)} catalog entries out of recommended.ts; the "
        "guard would pass vacuously — fix the parse before trusting it."
    )
    return entries


def _server_rates(provider: str, model: str) -> tuple[float, float] | None:
    """The server's per-token rates for one catalog row."""
    if provider == "openrouter":
        return _MODEL_COST_MAP.get(model)
    return _PROVIDER_SCOPED_RATES.get((provider, model))


def test_web_catalog_openrouter_slugs_match_server_whitelist():
    """The offered OpenRouter slugs and the accepted whitelist are one set."""
    web = {
        str(entry["model"])
        for entry in _catalog_entries()
        if entry["provider"] == "openrouter"
    }
    server = set(settings_module._RECOMMENDED_MODELS)

    assert web == server, (
        "The web catalog and the server whitelist drifted apart.\n"
        f"  web/src/routes/settings/recommended.ts: {sorted(web)}\n"
        f"  server/api/routers/settings.py: {sorted(server)}\n"
        "A slug offered by the wizard but not whitelisted is rejected at "
        "submit time (the D6 dead-end); a whitelisted slug nobody offers is "
        "dead weight. Update both sides."
    )


def test_web_catalog_prices_match_server_rates():
    """Every displayed USD-per-1M price equals the server's rate table."""
    problems = []
    for entry in _catalog_entries():
        provider = str(entry["provider"])
        model = str(entry["model"])
        rates = _server_rates(provider, model)
        if rates is None:
            problems.append(
                f"{provider}/{model}: no server rate entry "
                "(add it to _MODEL_COST_MAP or _PROVIDER_SCOPED_RATES)"
            )
            continue
        shown = (
            float(entry["input"]) / 1_000_000,
            float(entry["output"]) / 1_000_000,
        )
        same_input = rates[0] == pytest.approx(shown[0])
        same_output = rates[1] == pytest.approx(shown[1])
        if not (same_input and same_output):
            shown_1m = f"${float(entry['input']):g}/${float(entry['output']):g}"
            rates_1m = f"${rates[0] * 1_000_000:g}/${rates[1] * 1_000_000:g}"
            problems.append(
                f"{provider}/{model}: the wizard shows {shown_1m} per 1M but the "
                f"server estimates {rates_1m} per 1M"
            )

    assert not problems, (
        "A displayed price no longer matches the rate the server charges:\n  "
        + "\n  ".join(problems)
        + "\nUpdate web/src/routes/settings/recommended.ts and the server rate "
        "table together (prices are curated by hand on both sides)."
    )


def test_web_catalog_tier_matches_its_price():
    """`free` means zero on both rates, because the UI prints "Gratis"."""
    problems = []
    for entry in _catalog_entries():
        priced = float(entry["input"]) != 0 or float(entry["output"]) != 0
        if entry["tier"] == "free" and priced:
            problems.append(
                f"{entry['provider']}/{entry['model']}: tier `free` with a non-zero "
                "price — the wizard prints \"Gratis\" while the server charges"
            )
        if entry["tier"] == "paid" and not priced:
            problems.append(
                f"{entry['provider']}/{entry['model']}: tier `paid` with zero rates — "
                "the wizard would show a $0.00 price"
            )

    assert not problems, "Catalog tier and price disagree:\n  " + "\n  ".join(problems)
