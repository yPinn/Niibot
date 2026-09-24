"""Unit tests for shared.safe_urls — tolerant-but-safe URL extraction from
user-typed text (chat, channel-points redemption input, donation messages).
"""

from __future__ import annotations

from shared.safe_urls import find_allowed_http_url, iter_http_urls

_YT = frozenset({"youtu.be", "www.youtube.com"})


def _first_youtube_url(text: str) -> str | None:
    parsed = find_allowed_http_url(text, _YT)
    return parsed.geturl() if parsed else None


class TestQuoteAndBracketTrimming:
    def test_plain_url_unaffected(self):
        assert _first_youtube_url("https://youtu.be/dQw4w9WgXcQ") is not None

    def test_straight_quotes_stripped(self):
        assert _first_youtube_url("'https://youtu.be/dQw4w9WgXcQ'") is not None
        assert _first_youtube_url('"https://youtu.be/dQw4w9WgXcQ"') is not None

    def test_smart_quotes_stripped(self):
        # iOS/autocorrect commonly turns a straight quote into one of these.
        assert _first_youtube_url("‘https://youtu.be/dQw4w9WgXcQ’") is not None
        assert _first_youtube_url("“https://youtu.be/dQw4w9WgXcQ”") is not None

    def test_cjk_quotation_brackets_stripped(self):
        assert _first_youtube_url("「https://youtu.be/dQw4w9WgXcQ」") is not None
        assert _first_youtube_url("『https://youtu.be/dQw4w9WgXcQ』") is not None

    def test_cjk_title_marks_stripped(self):
        assert _first_youtube_url("《https://youtu.be/dQw4w9WgXcQ》") is not None
        assert _first_youtube_url("〈https://youtu.be/dQw4w9WgXcQ〉") is not None

    def test_fullwidth_parens_stripped(self):
        assert _first_youtube_url("（https://youtu.be/dQw4w9WgXcQ）") is not None

    def test_fullwidth_brackets_stripped(self):
        assert _first_youtube_url("【https://youtu.be/dQw4w9WgXcQ】") is not None

    def test_mixed_wrapping_still_resolves(self):
        parsed = find_allowed_http_url("「'https://youtu.be/dQw4w9WgXcQ'」", _YT)
        assert parsed is not None
        assert parsed.hostname == "youtu.be"


class TestInvisibleCharacterStripping:
    # Built from codepoints (chr()) rather than embedding the character in a
    # string literal — a formatter would otherwise happily collapse a
    # `\uXXXX`-style escape back into the actual invisible character, leaving
    # something unreviewable sitting in a diff. Ironic to get wrong in the
    # one test file about invisible characters — see shared/safe_urls.py's
    # _INVISIBLE_RE for the same convention on the production side.
    def test_zero_width_space_inside_url_stripped(self):
        # A paste artifact landing mid-URL — invisible, so a user has no way
        # to notice or manually remove it before redeeming/submitting.
        url = "https://youtu.be/dQw4w9" + chr(0x200B) + "WgXcQ"
        parsed = find_allowed_http_url(url, _YT)
        assert parsed is not None
        assert parsed.path == "/dQw4w9WgXcQ"

    def test_bom_prefix_stripped(self):
        url = chr(0xFEFF) + "https://youtu.be/dQw4w9WgXcQ"
        parsed = find_allowed_http_url(url, _YT)
        assert parsed is not None
        assert parsed.hostname == "youtu.be"

    def test_zero_width_joiner_and_non_joiner_stripped(self):
        url = "https://youtu.be/dQw4w9" + chr(0x200C) + chr(0x200D) + "WgXcQ"
        parsed = find_allowed_http_url(url, _YT)
        assert parsed is not None
        assert parsed.path == "/dQw4w9WgXcQ"


class TestSurroundingWhitespace:
    def test_leading_and_trailing_whitespace_ignored(self):
        assert _first_youtube_url("   https://youtu.be/dQw4w9WgXcQ   ") is not None

    def test_fullwidth_space_ignored(self):
        # U+3000 IDEOGRAPHIC SPACE — common from a fullwidth-mode IME. Built
        # from chr() so the blank-looking character isn't sitting bare in the
        # source file.
        url = chr(0x3000) + "https://youtu.be/dQw4w9WgXcQ" + chr(0x3000)
        assert _first_youtube_url(url) is not None

    def test_extra_surrounding_text_ignored(self):
        assert _first_youtube_url("看這個 https://youtu.be/dQw4w9WgXcQ 謝謝") is not None


class TestHostSpoofingStillRejected:
    """Regression guard: none of the added tolerance should widen what counts
    as a match for an untrusted host — see the module's security note."""

    def test_spoofed_host_in_path_rejected(self):
        assert _first_youtube_url("https://evil.example/youtu.be/dQw4w9WgXcQ") is None

    def test_userinfo_prefix_on_real_host_still_rejected(self):
        # Trimming must not accidentally defeat the existing username@host
        # check — a real allowed hostname with credentials prepended is still
        # rejected, not silently accepted because it "looks close enough".
        assert _first_youtube_url("https://user@youtu.be/dQw4w9WgXcQ") is None


class TestIterHttpUrls:
    def test_plain_text_matches_no_allowed_host(self):
        # iter_http_urls itself is permissive (any bare word becomes a
        # syntactically-plausible https://<word> candidate) — allowed-host
        # filtering is find_allowed_http_url's job, not this layer's.
        assert find_allowed_http_url("no url here", _YT) is None

    def test_yields_multiple_urls_in_order(self):
        parsed = list(iter_http_urls("https://youtu.be/aaaaaaaaaaa https://youtu.be/bbbbbbbbbbb"))
        assert [p.path for p in parsed] == ["/aaaaaaaaaaa", "/bbbbbbbbbbb"]
