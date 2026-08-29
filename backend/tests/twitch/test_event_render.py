"""Unit tests for twitch.utils.event_render."""

from twitch.utils.event_render import (
    MESSAGE_VAR_LIMIT,
    clean_message_var,
    mention_vars,
    render_template,
)

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

    def test_at_var_resolves_its_own_key(self):
        out = render_template("感謝 $(@user)！", {"user": "小明", "@user": "@小明"})
        assert out == "感謝 @小明！"


class TestOptionalSegments:
    TMPL = "感謝 $(user) 訂閱滿 $(total) 個月[[，已連續 $(streak) 個月]][[（$(source)）]]！"

    def test_both_absent_collapse(self):
        out = render_template(self.TMPL, {"user": "A", "total": "14", "streak": "", "source": ""})
        assert out == "感謝 A 訂閱滿 14 個月！"

    def test_one_present_one_absent(self):
        out = render_template(self.TMPL, {"user": "A", "total": "14", "streak": "6", "source": ""})
        assert out == "感謝 A 訂閱滿 14 個月，已連續 6 個月！"

    def test_both_present(self):
        out = render_template(
            self.TMPL, {"user": "A", "total": "3", "streak": "3", "source": "贈訂"}
        )
        assert out == "感謝 A 訂閱滿 3 個月，已連續 3 個月（贈訂）！"

    def test_missing_key_counts_as_absent(self):
        assert render_template("x[[ $(y)]]", {}) == "x"

    def test_segment_markers_from_viewer_value_are_inert(self):
        # A viewer typing "[[" / "$(x)" in their message must not be processed.
        out = render_template("$(message)", {"message": "[[$(x)]]", "x": "boom"})
        assert out == "[[$(x)]]"


class TestMentionVars:
    def test_named_chatter(self):
        assert mention_vars("user", "小明") == {"user": "小明", "@user": "@小明"}

    def test_anonymous_stays_plain(self):
        assert mention_vars("user", "匿名用戶", anonymous=True) == {
            "user": "匿名用戶",
            "@user": "匿名用戶",
        }

    def test_empty_name_stays_plain(self):
        assert mention_vars("gifter", "") == {"gifter": "", "@gifter": ""}
