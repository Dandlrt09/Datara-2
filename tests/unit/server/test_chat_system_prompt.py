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


# Two profiled datasets of one session: the shape a crossing produces.
_TWO_PROFILES = [
    _PROFILE[0],
    {
        "file_id": 2,
        "filename": "orders.csv",
        "format": "csv",
        "path": "/tmp/orders.csv",
        "row_count": 4,
        "profile": {"columns": ["order_id", "a"], "stats": {}, "sample": []},
    },
]

# The stored recipe as the store returns it (F5 / S4, T1).
_CROSSING = {
    "id": 7,
    "chat_session": "session-1",
    "left_file_id": 1,
    "right_file_id": 2,
    "left_key": "a",
    "right_key": "a",
    "how": "left",
    "created_at": "2026-01-01 00:00:00",
    "left_filename": "data.csv",
    "right_filename": "orders.csv",
}

# The exact instruction A3 puts in the turn's prompt: the recipe travels as
# words, never as code injected into the sandbox.
_CROSSING_INSTRUCTION = (
    "Build the crossed dataset with pd.merge(...) using exactly those keys and "
    "that join kind, and assign the merged frame to a variable named df_result "
    "\u2014 it is the dataset the user's questions are about, and the existing "
    "capture rule only publishes df_result."
)


class TestCrossingBlock:
    """F5 / T3 (S3, S4): the confirmed recipe reaches the model as instructions."""

    def test_crossing_block_is_present(self):
        prompt = build_system_prompt(_TWO_PROFILES, crossing=_CROSSING)
        assert "IMPORTANT \u2014 dataset crossing (confirmed by the user):" in prompt

    def test_crossing_block_names_both_datasets_their_keys_and_the_join(self):
        prompt = build_system_prompt(_TWO_PROFILES, crossing=_CROSSING)
        assert (
            "- left dataset: 'data.csv' (read it from its 'path' above), key 'a'"
            in prompt
        )
        assert (
            "- right dataset: 'orders.csv' (read it from its 'path' above), key 'a'"
            in prompt
        )
        assert "- join kind: 'left'" in prompt

    def test_crossing_block_ends_in_df_result(self):
        prompt = build_system_prompt(_TWO_PROFILES, crossing=_CROSSING)
        assert _CROSSING_INSTRUCTION in prompt

    def test_no_crossing_carries_none_of_the_block(self):
        prompt = build_system_prompt(_TWO_PROFILES, crossing=None)
        assert "dataset crossing" not in prompt
        assert "join kind" not in prompt
        assert _CROSSING_INSTRUCTION not in prompt

    def test_no_crossing_prompt_matches_the_default(self):
        """The default argument keeps today's prompt byte-identical."""
        assert build_system_prompt(_TWO_PROFILES) == build_system_prompt(
            _TWO_PROFILES, crossing=None
        )

    def test_a_crossing_whose_dataset_has_no_profile_renders_no_block(self):
        """Never promise the model a dataset the prompt does not describe.

        The block says "read it from its 'path' above"; a crossing whose right
        side has no profile (the file was deleted from disk, so the lazy
        re-profile cannot rebuild it) must lose the block instead of pointing
        at a path that is nowhere in the prompt. The control line proves the
        full profile list does match the recipe, so this test cannot pass
        merely because no filename ever matches.
        """
        only_the_left_side = [{"filename": "data.csv", "path": "/tmp/data.csv"}]
        prompt = build_system_prompt(only_the_left_side, crossing=_CROSSING)
        assert "dataset crossing" not in prompt
        assert _CROSSING_INSTRUCTION not in prompt
        assert "dataset crossing" in build_system_prompt(
            _TWO_PROFILES, crossing=_CROSSING
        )


class TestNumberFormatPreference:
    def test_default_prompt_keeps_the_spanish_rule(self):
        prompt = build_system_prompt(_PROFILE)
        assert "Format numeric values in Spanish convention" in prompt

    def test_international_preference_swaps_the_rule(self):
        prompt = build_system_prompt(_PROFILE, number_format="intl")
        assert "Format numeric values in international convention" in prompt
        assert "Format numeric values in Spanish convention" not in prompt
