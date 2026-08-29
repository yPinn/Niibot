"""Unit tests for twitch.utils.event_render."""

from twitch.utils.event_render import MESSAGE_VAR_LIMIT, clean_message_var, render_template

from shared.events import tier_label


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

    def test_empty_string(self):
        assert clean_message_var("") == ""

    def test_caps_length(self):
        assert len(clean_message_var("x" * 999)) == MESSAGE_VAR_LIMIT

    def test_plain_text_untouched(self):
        assert clean_message_var("thanks for the sub!") == "thanks for the sub!"


class TestRenderTemplate:
    def test_substitutes_known_placeholders(self):
        assert render_template("感謝 $(user) $(tier)", {"user": "A", "tier": "T2"}) == "感謝 A T2"

    def test_unknown_placeholder_left_as_is(self):
        assert render_template("$(user) $(missing)", {"user": "A"}) == "A $(missing)"

    def test_substituted_value_is_not_rescanned(self):
        # A viewer typing "$(user)" into their resub note must not expand,
        # regardless of dict key order.
        assert (
            render_template("$(message) $(user)", {"message": "$(user)", "user": "X"})
            == "$(user) X"
        )

    def test_backslash_in_value_is_literal(self):
        # A regex string replacement would treat "\1" as a backref — the callable
        # repl must not.
        assert render_template("$(message)", {"message": r"win \1 \g<0>"}) == r"win \1 \g<0>"

    def test_no_placeholders(self):
        assert render_template("just text", {"user": "A"}) == "just text"
