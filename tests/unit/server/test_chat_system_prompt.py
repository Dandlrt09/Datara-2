"""Unit tests for the chat system prompt assembly.

Covers the no-dataset branch added for sessions with no attached files:
without profiles the prompt must say there is no data and forbid writing or
running code. The profiles-present path is pinned byte-for-byte because the
regression bench (scripts/bench.py) and existing prompt tests depend on it.
"""

from __future__ import annotations

import hashlib

from server.api.routers.chat import build_system_prompt

# A fixed profile whose serialized form is deterministic (json.dumps keeps
# dict insertion order), so the SHA-256 pins the exact bytes of the
# profiles-present prompt against accidental drift.
#
# Updated deliberately for the Spanish number-format rule (dot thousands,
# comma decimal) in the narrative-quality paragraph; the bench shares this
# prompt and was updated in lockstep.
#
# Updated again deliberately for the single-result-table rule: the
# surfacing-results paragraph no longer says "assign every requested result
# table" (plural); it now states the UI shows ONE result table assigned to
# df_result, matching the sandbox's single-table capture.
_PROFILE = [
    {
        "file_id": 1,
        "filename": "data.csv",
        "format": "csv",
        "path": "/tmp/data.csv",
        "row_count": 3,
        "profile": {"columns": ["a", "b"], "stats": {}, "sample": []},
    }
]
_PROFILES_PROMPT_SHA256 = (
    "563a2759d570406f0cb32fb13633db7207ebae13b97f8f6048151e91e0641ad4"
)


class TestNoDatasetBranch:
    def test_no_dataset_rule_is_present(self):
        """No profiles: the model is told there is no data and what to do."""
        prompt = build_system_prompt([])
        assert "no dataset file is attached to this session" in prompt
        assert "do NOT invent, synthesize, fabricate or" in prompt
        assert "attach a dataset file to this session first" in prompt

    def test_no_dataset_prompt_omits_datasets_block(self):
        prompt = build_system_prompt([])
        assert "Available datasets" not in prompt

    def test_profiles_prompt_omits_no_dataset_rule(self):
        prompt = build_system_prompt(_PROFILE)
        assert "Available datasets" in prompt
        assert "data.csv" in prompt
        assert "no dataset file is attached to this session" not in prompt


class TestProfilesPresentPathUnchanged:
    def test_profiles_prompt_is_byte_identical(self):
        """Pin the exact bytes shared with scripts/bench.py."""
        prompt = build_system_prompt(_PROFILE)
        assert (
            hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            == _PROFILES_PROMPT_SHA256
        )

    def test_prompt_states_single_result_table_rule(self):
        """The prompt must be singular about result tables.

        Regression: the surfacing-results paragraph said "assign every
        requested result table" (plural) while the later paragraph said
        "EXACTLY ONE df_ variable", so models rendered several tables.
        """
        prompt = build_system_prompt(_PROFILE)
        assert "assign every requested result table" not in prompt
        assert "assign the single result table to a DataFrame variable named df_result" in prompt
