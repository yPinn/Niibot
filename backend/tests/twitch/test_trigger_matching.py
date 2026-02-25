"""Unit tests for twitch.utils.trigger_matching.match_trigger."""

from twitch.utils.trigger_matching import match_trigger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_trigger(
    *,
    pattern: str,
    match_type: str,
    case_sensitive: bool = False,
):
    """Return a minimal TriggerLike object."""

    class _T:
        pass

    t = _T()
    t.pattern = pattern
    t.match_type = match_type
    t.case_sensitive = case_sensitive
    return t


# ---------------------------------------------------------------------------
# contains
# ---------------------------------------------------------------------------


class TestContains:
    def test_pattern_in_middle(self):
        t = make_trigger(pattern="hello", match_type="contains")
        assert match_trigger(t, "say hello world") is True

    def test_pattern_at_start(self):
        t = make_trigger(pattern="hello", match_type="contains")
        assert match_trigger(t, "hello world") is True

    def test_pattern_at_end(self):
        t = make_trigger(pattern="world", match_type="contains")
        assert match_trigger(t, "hello world") is True

    def test_no_match(self):
        t = make_trigger(pattern="bye", match_type="contains")
        assert match_trigger(t, "hello world") is False

    def test_case_insensitive_default(self):
        t = make_trigger(pattern="HELLO", match_type="contains", case_sensitive=False)
        assert match_trigger(t, "say hello") is True

    def test_case_sensitive_mismatch(self):
        t = make_trigger(pattern="HELLO", match_type="contains", case_sensitive=True)
        assert match_trigger(t, "say hello") is False

    def test_case_sensitive_match(self):
        t = make_trigger(pattern="HELLO", match_type="contains", case_sensitive=True)
        assert match_trigger(t, "say HELLO there") is True

    def test_empty_pattern_always_matches(self):
        t = make_trigger(pattern="", match_type="contains")
        assert match_trigger(t, "any text") is True

    def test_empty_text_no_match_for_nonempty_pattern(self):
        t = make_trigger(pattern="x", match_type="contains")
        assert match_trigger(t, "") is False


# ---------------------------------------------------------------------------
# startswith
# ---------------------------------------------------------------------------


class TestStartswith:
    def test_text_starts_with_pattern(self):
        t = make_trigger(pattern="!cmd", match_type="startswith")
        assert match_trigger(t, "!cmd arg") is True

    def test_text_does_not_start_with_pattern(self):
        t = make_trigger(pattern="!cmd", match_type="startswith")
        assert match_trigger(t, "prefix !cmd") is False

    def test_exact_text_equals_pattern(self):
        t = make_trigger(pattern="hello", match_type="startswith")
        assert match_trigger(t, "hello") is True

    def test_case_insensitive(self):
        t = make_trigger(pattern="!CMD", match_type="startswith", case_sensitive=False)
        assert match_trigger(t, "!cmd arg") is True

    def test_case_sensitive_mismatch(self):
        t = make_trigger(pattern="!CMD", match_type="startswith", case_sensitive=True)
        assert match_trigger(t, "!cmd arg") is False


# ---------------------------------------------------------------------------
# exact
# ---------------------------------------------------------------------------


class TestExact:
    def test_identical_text(self):
        t = make_trigger(pattern="hello", match_type="exact")
        assert match_trigger(t, "hello") is True

    def test_extra_suffix_no_match(self):
        t = make_trigger(pattern="hello", match_type="exact")
        assert match_trigger(t, "hello world") is False

    def test_extra_prefix_no_match(self):
        t = make_trigger(pattern="hello", match_type="exact")
        assert match_trigger(t, "say hello") is False

    def test_case_insensitive(self):
        t = make_trigger(pattern="HELLO", match_type="exact", case_sensitive=False)
        assert match_trigger(t, "hello") is True

    def test_case_sensitive_mismatch(self):
        t = make_trigger(pattern="HELLO", match_type="exact", case_sensitive=True)
        assert match_trigger(t, "hello") is False

    def test_empty_text_matches_empty_pattern(self):
        t = make_trigger(pattern="", match_type="exact")
        assert match_trigger(t, "") is True

    def test_empty_text_no_match_nonempty_pattern(self):
        t = make_trigger(pattern="x", match_type="exact")
        assert match_trigger(t, "") is False


# ---------------------------------------------------------------------------
# regex
# ---------------------------------------------------------------------------


class TestRegex:
    def test_simple_pattern_matches(self):
        t = make_trigger(pattern=r"\d+", match_type="regex")
        assert match_trigger(t, "I have 42 cookies") is True

    def test_simple_pattern_no_match(self):
        t = make_trigger(pattern=r"\d+", match_type="regex")
        assert match_trigger(t, "no numbers here") is False

    def test_anchored_start_match(self):
        t = make_trigger(pattern=r"^hello", match_type="regex")
        assert match_trigger(t, "hello world") is True

    def test_anchored_start_no_match(self):
        t = make_trigger(pattern=r"^hello", match_type="regex")
        assert match_trigger(t, "say hello") is False

    def test_invalid_regex_returns_false(self):
        t = make_trigger(pattern=r"[invalid(", match_type="regex")
        assert match_trigger(t, "any text") is False

    def test_case_insensitive_regex(self):
        t = make_trigger(pattern=r"hello", match_type="regex", case_sensitive=False)
        assert match_trigger(t, "HELLO WORLD") is True

    def test_case_sensitive_regex(self):
        t = make_trigger(pattern=r"hello", match_type="regex", case_sensitive=True)
        assert match_trigger(t, "HELLO WORLD") is False


# ---------------------------------------------------------------------------
# Unknown match_type
# ---------------------------------------------------------------------------


class TestUnknownMatchType:
    def test_unknown_type_returns_false(self):
        t = make_trigger(pattern="x", match_type="fuzzy")
        assert match_trigger(t, "xxx") is False

    def test_empty_match_type_returns_false(self):
        t = make_trigger(pattern="x", match_type="")
        assert match_trigger(t, "x") is False
