"""Tests for src/ai_sw_bridge/flags.py.

Covers:
  - Default-state assertion (all v0.11 flags default off)
  - Precedence chain: CLI > env var > TOML > defaults
  - Unknown-flag error handling
  - Env-var parsing edge cases
  - Contradictory enable/disable detection
  - TOML read (with and without tomllib/tomli)
"""

from __future__ import annotations

import os
import textwrap

import pytest

from ai_sw_bridge.flags import (
    FLAG_REGISTRY,
    FeatureFlag,
    _env_var_name,
    _read_env,
    _read_toml,
    parse_flag_args,
    resolve,
)


# ---------------------------------------------------------------------------
# Default-state assertion
# ---------------------------------------------------------------------------


class TestDefaultState:
    def test_all_v011_flags_default_off(self):
        for name, flag in FLAG_REGISTRY.items():
            assert flag.default is False, f"{name} should default to False"

    def test_registry_contains_expected_flags(self):
        assert len(FLAG_REGISTRY) == 5
        assert "brep_interrogation" in FLAG_REGISTRY
        assert "rag_apidoc" in FLAG_REGISTRY
        assert "checkpoint" in FLAG_REGISTRY
        assert "mcp_wrapper" in FLAG_REGISTRY
        assert "schema_v2" in FLAG_REGISTRY  # X5 (FR-1/FR-2)

    def test_each_flag_has_required_fields(self):
        for name, flag in FLAG_REGISTRY.items():
            assert isinstance(flag, FeatureFlag)
            assert flag.name == name
            assert isinstance(flag.description, str) and len(flag.description) > 0
            assert flag.lane in ("L1", "L2", "L3", "L4", "M", "core")
            assert isinstance(flag.removal_date, str) and flag.removal_date.startswith(
                "v"
            )


# ---------------------------------------------------------------------------
# Precedence chain
# ---------------------------------------------------------------------------


class TestPrecedence:
    def test_defaults_when_no_overrides(self):
        result = resolve()
        for name, flag in FLAG_REGISTRY.items():
            assert result[name] is flag.default

    def test_cli_overrides_default(self):
        result = resolve(cli_overrides={"brep_interrogation": True})
        assert result["brep_interrogation"] is True
        # Others stay default
        assert result["rag_apidoc"] is False

    def test_env_overrides_default(self, monkeypatch):
        monkeypatch.setenv(_env_var_name("brep_interrogation"), "1")
        result = resolve()
        assert result["brep_interrogation"] is True

    def test_cli_overrides_env(self, monkeypatch):
        monkeypatch.setenv(_env_var_name("brep_interrogation"), "1")
        result = resolve(cli_overrides={"brep_interrogation": False})
        assert result["brep_interrogation"] is False

    def test_toml_overrides_default(self, tmp_path):
        toml_file = tmp_path / ".ai-sw-bridge.toml"
        toml_file.write_text(
            textwrap.dedent(
                """\
                [flags]
                rag_apidoc = true
            """
            ),
            encoding="utf-8",
        )
        result = resolve(toml_path=toml_file)
        assert result["rag_apidoc"] is True
        assert result["brep_interrogation"] is False

    def test_env_overrides_toml(self, monkeypatch, tmp_path):
        toml_file = tmp_path / ".ai-sw-bridge.toml"
        toml_file.write_text(
            textwrap.dedent(
                """\
                [flags]
                rag_apidoc = true
            """
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv(_env_var_name("rag_apidoc"), "0")
        result = resolve(toml_path=toml_file)
        assert result["rag_apidoc"] is False

    def test_full_chain(self, monkeypatch, tmp_path):
        """CLI > env > TOML > default for each flag in the chain."""
        toml_file = tmp_path / ".ai-sw-bridge.toml"
        toml_file.write_text(
            textwrap.dedent(
                """\
                [flags]
                brep_interrogation = true
                checkpoint = true
            """
            ),
            encoding="utf-8",
        )
        # env overrides TOML for checkpoint
        monkeypatch.setenv(_env_var_name("checkpoint"), "0")
        result = resolve(
            cli_overrides={"rag_apidoc": True},
            toml_path=toml_file,
        )
        # rag_apidoc: CLI wins → True
        assert result["rag_apidoc"] is True
        # brep_interrogation: TOML wins (no env/CLI) → True
        assert result["brep_interrogation"] is True
        # checkpoint: env overrides TOML → False
        assert result["checkpoint"] is False
        # mcp_wrapper: default → False
        assert result["mcp_wrapper"] is False


# ---------------------------------------------------------------------------
# Unknown-flag errors
# ---------------------------------------------------------------------------


class TestUnknownFlag:
    def test_resolve_rejects_unknown_cli_flag(self):
        with pytest.raises(ValueError, match="unknown feature flag"):
            resolve(cli_overrides={"nonexistent_flag": True})

    def test_parse_flag_args_rejects_unknown_enable(self):
        with pytest.raises(ValueError, match="unknown feature flag"):
            parse_flag_args(enable=["nonexistent"], disable=[])

    def test_parse_flag_args_rejects_unknown_disable(self):
        with pytest.raises(ValueError, match="unknown feature flag"):
            parse_flag_args(enable=[], disable=["nonexistent"])

    def test_parse_flag_args_rejects_contradictory(self):
        with pytest.raises(ValueError, match="both enabled and disabled"):
            parse_flag_args(
                enable=["brep_interrogation"], disable=["brep_interrogation"]
            )


# ---------------------------------------------------------------------------
# Env-var parsing edge cases
# ---------------------------------------------------------------------------


class TestEnvVarParsing:
    def test_truthy_values(self, monkeypatch):
        for val in ("1", "true", "True", "TRUE", "yes", "Yes", "YES"):
            monkeypatch.setenv(_env_var_name("brep_interrogation"), val)
            assert _read_env("brep_interrogation") is True, f"expected True for {val!r}"

    def test_falsy_values(self, monkeypatch):
        for val in ("0", "false", "False", "FALSE", "no", "No", "NO"):
            monkeypatch.setenv(_env_var_name("brep_interrogation"), val)
            assert (
                _read_env("brep_interrogation") is False
            ), f"expected False for {val!r}"

    def test_unparseable_returns_none(self, monkeypatch):
        monkeypatch.setenv(_env_var_name("brep_interrogation"), "maybe")
        assert _read_env("brep_interrogation") is None

    def test_unset_returns_none(self):
        # Ensure the var is not set
        os.environ.pop(_env_var_name("brep_interrogation"), None)
        assert _read_env("brep_interrogation") is None

    def test_unparseable_falls_through_to_default(self, monkeypatch):
        monkeypatch.setenv(_env_var_name("brep_interrogation"), "maybe")
        result = resolve()
        assert (
            result["brep_interrogation"] is FLAG_REGISTRY["brep_interrogation"].default
        )


# ---------------------------------------------------------------------------
# TOML edge cases
# ---------------------------------------------------------------------------


class TestTomlParsing:
    def test_missing_file_returns_none(self, tmp_path):
        assert _read_toml("brep_interrogation", tmp_path / "nonexistent.toml") is None

    def test_file_without_flags_section(self, tmp_path):
        toml_file = tmp_path / ".ai-sw-bridge.toml"
        toml_file.write_text("[other]\nkey = 1\n", encoding="utf-8")
        assert _read_toml("brep_interrogation", toml_file) is None

    def test_file_with_non_bool_value(self, tmp_path):
        toml_file = tmp_path / ".ai-sw-bridge.toml"
        toml_file.write_text('[flags]\nbrep_interrogation = "yes"\n', encoding="utf-8")
        assert _read_toml("brep_interrogation", toml_file) is None

    def test_non_dict_flags_section(self, tmp_path):
        toml_file = tmp_path / ".ai-sw-bridge.toml"
        toml_file.write_text("flags = 42\n", encoding="utf-8")
        assert _read_toml("brep_interrogation", toml_file) is None


# ---------------------------------------------------------------------------
# parse_flag_args
# ---------------------------------------------------------------------------


class TestParseFlagArgs:
    def test_empty_inputs(self):
        assert parse_flag_args(None, None) == {}

    def test_enable_single(self):
        assert parse_flag_args(["brep_interrogation"], None) == {
            "brep_interrogation": True
        }

    def test_disable_single(self):
        assert parse_flag_args(None, ["brep_interrogation"]) == {
            "brep_interrogation": False
        }

    def test_mixed(self):
        result = parse_flag_args(["brep_interrogation"], ["checkpoint"])
        assert result == {"brep_interrogation": True, "checkpoint": False}
