"""Unit tests for twitch.utils.event_render."""

from twitch.utils.event_render import (
    _MESSAGE_VAR_LIMIT,
    clean_message_var,
    render_template,
    tier_label,
)


class TestTierLabel:
    def test_known_tiers(self):
        assert tier_label("1000") == "T1"
        assert tier_label("3000") == "T3"

    def test_unknown_passthrough(self):
        assert tier_label("9999") == "9999"


class TestCleanMessageVar:
    def test_collapses_newlines_and_whitespace(self):
        assert clean_message_var("hi\n\nthere   world") == "hi there world"

    def test_drops_leading_command_char(self):
        assert clean_message_var("/me waves") == "me waves"
        assert clean_message_var(".timeout bob") == "timeout bob"
        assert clean_message_var("...anyway") == "..anyway"  # only the first char

    def test_caps_length(self):
        assert len(clean_message_var("x" * 999)) == _MESSAGE_VAR_LIMIT

    def test_plain_text_untouched(self):
        assert clean_message_var("thanks for the sub!") == "thanks for the sub!"


class TestRenderTemplate:
    def test_substitutes_known_placeholders(self):
        assert render_template("感謝 $(user) $(tier)", {"user": "A", "tier": "T2"}) == "感謝 A T2"

    def test_unknown_placeholder_left_as_is(self):
        assert render_template("$(user) $(missing)", {"user": "A"}) == "A $(missing)"
