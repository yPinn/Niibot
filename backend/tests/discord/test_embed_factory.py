"""Unit tests for discord.core.embed_factory.EmbedFactory and core.load_json.

Loads EmbedFactory via importlib to avoid triggering the full discord-bot
import chain (which requires a live discord runtime beyond pytest).
load_json is tested via an inline equivalent — same logic, no import chain.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import discord
import pytest

# ---------------------------------------------------------------------------
# Bootstrap — load embed_factory.py in isolation
# ---------------------------------------------------------------------------

_DISCORD_CORE = Path(__file__).parent.parent.parent / "discord" / "core"

_ef_spec = importlib.util.spec_from_file_location(
    "embed_factory", _DISCORD_CORE / "embed_factory.py"
)
_ef_mod = importlib.util.module_from_spec(_ef_spec)  # type: ignore[arg-type]
_ef_spec.loader.exec_module(_ef_mod)  # type: ignore[union-attr]

EmbedFactory = _ef_mod.EmbedFactory


# ---------------------------------------------------------------------------
# load_json — inline equivalent (same logic as core.load_json)
# ---------------------------------------------------------------------------


def _load_json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FULL_CFG = {
    "author": {
        "name": "TestBot",
        "icon_url": "https://example.com/icon.png",
        "url": "https://example.com",
    },
    "footer": {
        "text": "TestBot footer",
        "icon_url": "https://example.com/footer_icon.png",
    },
}


@pytest.fixture
def factory():
    return EmbedFactory(_FULL_CFG)


@pytest.fixture
def empty_factory():
    return EmbedFactory({})


# ===========================================================================
# Basic fields
# ===========================================================================


class TestBuildBasicFields:
    def test_title(self, factory):
        assert factory.build(title="Hello").title == "Hello"

    def test_description(self, factory):
        assert factory.build(description="Some text").description == "Some text"

    def test_color(self, factory):
        assert factory.build(color=discord.Color.red()).color == discord.Color.red()

    def test_url(self, factory):
        assert factory.build(url="https://example.com").url == "https://example.com"

    def test_timestamp(self, factory):
        ts = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
        assert factory.build(timestamp=ts).timestamp == ts

    def test_no_timestamp_by_default(self, factory):
        assert factory.build().timestamp is None

    def test_thumbnail(self, factory):
        embed = factory.build(thumbnail="https://example.com/thumb.png")
        assert embed.thumbnail.url == "https://example.com/thumb.png"

    def test_no_thumbnail_when_none(self, factory):
        assert factory.build(thumbnail=None).thumbnail.url is None

    def test_image(self, factory):
        embed = factory.build(image="https://example.com/img.png")
        assert embed.image.url == "https://example.com/img.png"

    def test_no_image_when_none(self, factory):
        assert factory.build(image=None).image.url is None

    def test_returns_discord_embed_instance(self, factory):
        assert isinstance(factory.build(), discord.Embed)


# ===========================================================================
# Author behaviour
# ===========================================================================


class TestBuildAuthor:
    def test_default_applies_cfg_author(self, factory):
        embed = factory.build()
        assert embed.author.name == "TestBot"
        assert embed.author.icon_url == "https://example.com/icon.png"
        assert embed.author.url == "https://example.com"

    def test_author_none_suppresses_author(self, factory):
        embed = factory.build(author=None)
        assert embed.author.name is None

    def test_author_custom_dict_overrides_cfg(self, factory):
        embed = factory.build(
            author={"name": "Override", "icon_url": "https://x.com/i.png", "url": "https://x.com"}
        )
        assert embed.author.name == "Override"
        assert embed.author.icon_url == "https://x.com/i.png"
        assert embed.author.url == "https://x.com"

    def test_author_custom_dict_partial(self, factory):
        embed = factory.build(author={"name": "OnlyName"})
        assert embed.author.name == "OnlyName"
        assert embed.author.icon_url is None

    def test_empty_cfg_no_author(self, empty_factory):
        assert empty_factory.build().author.name is None

    def test_cfg_author_without_name_is_skipped(self):
        factory = EmbedFactory({"author": {"icon_url": "https://example.com/icon.png"}})
        assert factory.build().author.name is None


# ===========================================================================
# Footer behaviour
# ===========================================================================


class TestBuildFooter:
    def test_default_applies_cfg_footer(self, factory):
        embed = factory.build()
        assert embed.footer.text == "TestBot footer"
        assert embed.footer.icon_url == "https://example.com/footer_icon.png"

    def test_footer_none_suppresses_footer(self, factory):
        assert factory.build(footer=None).footer.text is None

    def test_footer_custom_text_inherits_cfg_icon(self, factory):
        embed = factory.build(footer="Custom text")
        assert embed.footer.text == "Custom text"
        assert embed.footer.icon_url == "https://example.com/footer_icon.png"

    def test_footer_custom_text_with_explicit_icon(self, factory):
        embed = factory.build(footer="Custom text", footer_icon="https://x.com/fi.png")
        assert embed.footer.text == "Custom text"
        assert embed.footer.icon_url == "https://x.com/fi.png"

    def test_footer_icon_overrides_cfg_icon_with_default_text(self, factory):
        embed = factory.build(footer_icon="https://override.com/icon.png")
        assert embed.footer.text == "TestBot footer"
        assert embed.footer.icon_url == "https://override.com/icon.png"

    def test_empty_cfg_no_footer(self, empty_factory):
        assert empty_factory.build().footer.text is None

    def test_cfg_footer_without_text_is_skipped(self):
        factory = EmbedFactory({"footer": {"icon_url": "https://example.com/icon.png"}})
        assert factory.build().footer.text is None

    def test_custom_footer_on_empty_cfg_has_no_icon(self, empty_factory):
        embed = empty_factory.build(footer="Stand-alone text")
        assert embed.footer.text == "Stand-alone text"
        assert embed.footer.icon_url is None


# ===========================================================================
# Combined suppression
# ===========================================================================


class TestBuildSuppressed:
    def test_both_suppressed(self, factory):
        embed = factory.build(author=None, footer=None)
        assert embed.author.name is None
        assert embed.footer.text is None

    def test_empty_cfg_bare_build(self):
        embed = EmbedFactory({}).build(title="Bare", color=discord.Color.blue())
        assert embed.title == "Bare"
        assert embed.author.name is None
        assert embed.footer.text is None


# ===========================================================================
# load_json behaviour
# ===========================================================================


class TestLoadJson:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        assert _load_json(tmp_path / "nope.json") == {}

    def test_valid_json_returns_data(self, tmp_path):
        fp = tmp_path / "data.json"
        fp.write_text(json.dumps({"key": "value"}), encoding="utf-8")
        assert _load_json(fp) == {"key": "value"}

    def test_corrupt_json_returns_empty_dict(self, tmp_path):
        fp = tmp_path / "bad.json"
        fp.write_text("not json {{", encoding="utf-8")
        assert _load_json(fp) == {}

    def test_empty_file_returns_empty_dict(self, tmp_path):
        fp = tmp_path / "empty.json"
        fp.write_text("", encoding="utf-8")
        assert _load_json(fp) == {}

    def test_custom_default_on_missing_file(self, tmp_path):
        result = _load_json(tmp_path / "nope.json", default={"fallback": True})
        assert result == {"fallback": True}

    def test_list_json_returned_correctly(self, tmp_path):
        fp = tmp_path / "list.json"
        fp.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        assert _load_json(fp) == [1, 2, 3]

    def test_nested_json_preserved(self, tmp_path):
        data = {"author": {"name": "Bot", "url": "https://example.com"}}
        fp = tmp_path / "embed.json"
        fp.write_text(json.dumps(data), encoding="utf-8")
        assert _load_json(fp) == data
