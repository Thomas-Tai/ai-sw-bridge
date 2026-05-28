"""Tests for the i18n locale scaffold (W4.5, UIUX §13).

Verifies that:
- ``_("Hello")`` returns ``"Hello"`` with the default en_US locale
- ``set_locale`` / ``get_locale`` work correctly
- The ``--locale`` CLI flag is accepted by ai-sw-build
- The locale package imports cleanly
"""

from __future__ import annotations

import pytest


class TestLocaleScaffold:
    def test_import_cleanly(self) -> None:
        from ai_sw_bridge.locale import _, get_locale, set_locale  # noqa: F401

    def test_default_locale_is_en_us(self) -> None:
        from ai_sw_bridge.locale import get_locale, set_locale

        set_locale("en_US")
        assert get_locale() == "en_US"

    def test_underscore_passthrough_en_us(self) -> None:
        from ai_sw_bridge.locale import _, set_locale

        set_locale("en_US")
        assert _("Hello") == "Hello"
        assert _("Build complete") == "Build complete"

    def test_missing_locale_falls_back(self) -> None:
        """A locale with no compiled .mo falls back to pass-through."""
        from ai_sw_bridge.locale import _, get_locale, set_locale

        set_locale("xx_XX")
        assert get_locale() == "xx_XX"
        assert _("Hello") == "Hello"

    def test_set_locale_returns_none(self) -> None:
        from ai_sw_bridge.locale import set_locale

        assert set_locale("en_US") is None


class TestLocaleCliFlag:
    def test_build_accepts_locale_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ai-sw-build --locale en_US is accepted without error."""
        from ai_sw_bridge.cli.build import main

        monkeypatch.setattr(
            "sys.argv",
            ["ai-sw-build", "nonexistent.json", "--locale", "en_US"],
        )
        rc = main()
        assert rc == 2  # file not found, not argparse error

    def test_build_help_mentions_locale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import io
        from contextlib import redirect_stderr, redirect_stdout

        from ai_sw_bridge.cli.build import main

        monkeypatch.setattr("sys.argv", ["ai-sw-build", "--help"])
        buf = io.StringIO()
        err_buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(err_buf):
            with pytest.raises(SystemExit):
                main()
        help_text = buf.getvalue()
        assert "--locale" in help_text
        assert "en_US" in help_text


class TestLocaleStreamsHelper:
    def test_add_locale_flag(self) -> None:
        import argparse

        from ai_sw_bridge.cli.streams import add_locale_flag

        parser = argparse.ArgumentParser()
        add_locale_flag(parser)
        args = parser.parse_args([])
        assert args.locale == "en_US"

    def test_add_locale_flag_custom(self) -> None:
        import argparse

        from ai_sw_bridge.cli.streams import add_locale_flag

        parser = argparse.ArgumentParser()
        add_locale_flag(parser)
        args = parser.parse_args(["--locale", "de_DE"])
        assert args.locale == "de_DE"

    def test_apply_locale(self) -> None:
        import argparse

        from ai_sw_bridge.cli.streams import apply_locale
        from ai_sw_bridge.locale import get_locale

        args = argparse.Namespace(locale="en_US")
        apply_locale(args)
        assert get_locale() == "en_US"
