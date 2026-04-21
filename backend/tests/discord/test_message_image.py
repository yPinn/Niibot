"""Tests for core.message_image — renderer, wrap logic, and emoji detection."""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageFont

from core.message_image import _IMG_WIDTH, _is_emoji, _render_sync, _wrap_text, render_message_image

# ── _is_emoji ─────────────────────────────────────────────────────────────────


class TestIsEmoji:
    def test_misc_technical_range(self):
        assert _is_emoji(0x2300)
        assert _is_emoji(0x23FF)

    def test_misc_symbols_range(self):
        assert _is_emoji(0x2600)  # ☀
        assert _is_emoji(0x27BF)

    def test_main_emoji_block(self):
        assert _is_emoji(0x1F600)  # 😀
        assert _is_emoji(0x1F1FF)

    def test_ascii_is_not_emoji(self):
        assert not _is_emoji(ord("A"))
        assert not _is_emoji(ord("0"))

    def test_cjk_is_not_emoji(self):
        assert not _is_emoji(0x4E00)  # 一
        assert not _is_emoji(0x9FFF)

    def test_just_outside_ranges(self):
        assert not _is_emoji(0x22FF)  # one before 0x2300
        assert not _is_emoji(0x1EFFF)  # one before 0x1F000


# ── _wrap_text ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def font():
    return ImageFont.load_default()


class TestWrapText:
    def test_empty_string_returns_one_empty_line(self, font):
        assert _wrap_text("", font, 500) == [""]

    def test_short_text_fits_single_line(self, font):
        assert _wrap_text("hello", font, 500) == ["hello"]

    def test_newline_splits_into_separate_lines(self, font):
        result = _wrap_text("line1\nline2", font, 500)
        assert result == ["line1", "line2"]

    def test_blank_line_preserved(self, font):
        result = _wrap_text("a\n\nb", font, 500)
        assert "" in result

    def test_very_narrow_wraps_char_by_char(self, font):
        # Width=1 forces per-character breaks; all chars must appear in output
        result = _wrap_text("abcde", font, 1)
        assert "".join(result) == "abcde"
        assert len(result) > 1

    def test_long_no_space_word_breaks_correctly(self, font):
        # Simulate CJK-like token that has no spaces but exceeds line width
        word = "A" * 200
        result = _wrap_text(word, font, 50)
        assert "".join(result) == word
        assert len(result) > 1


# ── _render_sync ──────────────────────────────────────────────────────────────


class TestRenderSync:
    def test_returns_bytes(self):
        result = _render_sync(None, "User", "下午 03:00", "Hello", None, None)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_output_is_valid_png(self):
        data = _render_sync(None, "User", "上午 10:30", "Test", None, None)
        assert Image.open(io.BytesIO(data)).format == "PNG"

    def test_png_has_alpha_channel(self):
        data = _render_sync(None, "User", "上午 10:30", "Test", None, None)
        assert Image.open(io.BytesIO(data)).mode == "RGBA"

    def test_image_width_matches_constant(self):
        data = _render_sync(None, "User", "下午 01:00", "x", None, None)
        assert Image.open(io.BytesIO(data)).width == _IMG_WIDTH

    def test_multiline_content_increases_height(self):
        short = _render_sync(None, "User", "下午 01:00", "x", None, None)
        tall = _render_sync(None, "User", "下午 01:00", "L1\nL2\nL3\nL4", None, None)
        assert Image.open(io.BytesIO(tall)).height > Image.open(io.BytesIO(short)).height

    def test_cjk_content_renders(self):
        data = _render_sync(
            None, "使用者", "下午 03:00", "這是一個測試訊息，包含中文字元。", None, None
        )
        assert Image.open(io.BytesIO(data)).format == "PNG"

    def test_empty_content_uses_fallback(self):
        data = _render_sync(None, "User", "上午 09:00", "", None, None)
        assert Image.open(io.BytesIO(data)).format == "PNG"

    def test_role_color_does_not_crash(self):
        data = _render_sync(None, "User", "下午 01:00", "hi", (255, 100, 0), None)
        assert isinstance(data, bytes)

    def test_server_tag_without_badge_does_not_crash(self):
        data = _render_sync(None, "User", "下午 01:00", "hi", None, ("TAG", None))
        assert isinstance(data, bytes)


# ── render_message_image (async entry point) ──────────────────────────────────


class TestRenderMessageImage:
    async def test_returns_valid_png_no_avatar(self):
        # avatar_url=None → _fetch_bytes returns None immediately (no HTTP)
        result = await render_message_image(
            avatar_url=None,
            display_name="User",
            timestamp_str="下午 03:00",
            content="Hello",
        )
        assert Image.open(io.BytesIO(result)).format == "PNG"

    async def test_with_role_color_and_no_avatar(self):
        result = await render_message_image(
            avatar_url=None,
            display_name="User",
            timestamp_str="下午 03:00",
            content="Test",
            role_color=(255, 100, 0),
        )
        assert isinstance(result, bytes)
