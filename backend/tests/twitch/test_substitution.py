"""Unit tests for twitch.utils.substitution.substitute_variables."""

from unittest.mock import patch

import pytest
from twitch.utils.substitution import substitute_variables

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_chatter(display_name: str | None = None, name: str | None = None):
    """Return a minimal chatter-like object."""

    class _Chatter:
        pass

    c = _Chatter()
    c.display_name = display_name
    c.name = name
    return c


# ---------------------------------------------------------------------------
# $(user)
# ---------------------------------------------------------------------------


class TestUserVariable:
    def test_uses_display_name_when_present(self):
        chatter = make_chatter(display_name="NiiStream", name="niistream")
        result = substitute_variables("Hello $(user)!", chatter, "ch", "")
        assert result == "Hello NiiStream!"

    def test_falls_back_to_name_when_no_display_name(self):
        chatter = make_chatter(display_name=None, name="niistream")
        result = substitute_variables("Hello $(user)!", chatter, "ch", "")
        assert result == "Hello niistream!"

    def test_empty_string_when_both_none(self):
        chatter = make_chatter(display_name=None, name=None)
        result = substitute_variables("Hello $(user)!", chatter, "ch", "")
        assert result == "Hello !"

    def test_empty_display_name_falls_back_to_name(self):
        chatter = make_chatter(display_name="", name="niistream")
        result = substitute_variables("$(user)", chatter, "ch", "")
        assert result == "niistream"


# ---------------------------------------------------------------------------
# $(query) and $(channel)
# ---------------------------------------------------------------------------


class TestQueryAndChannelVariables:
    def test_query_substitution(self):
        chatter = make_chatter(display_name="Nii")
        result = substitute_variables("!so $(query)", chatter, "ch", "streamername")
        assert result == "!so streamername"

    def test_empty_query(self):
        chatter = make_chatter(display_name="Nii")
        result = substitute_variables("say: $(query)", chatter, "ch", "")
        assert result == "say: "

    def test_channel_substitution(self):
        chatter = make_chatter(display_name="Nii")
        result = substitute_variables("Welcome to $(channel)!", chatter, "mystream", "")
        assert result == "Welcome to mystream!"

    def test_empty_channel_name(self):
        chatter = make_chatter(display_name="Nii")
        result = substitute_variables("$(channel)", chatter, "", "")
        assert result == ""


# ---------------------------------------------------------------------------
# $(random min,max)
# ---------------------------------------------------------------------------


class TestRandomVariable:
    def test_random_calls_randint_with_correct_bounds(self):
        chatter = make_chatter(display_name="Nii")
        with patch("twitch.utils.substitution.random.randint", return_value=42) as mock_rand:
            result = substitute_variables("$(random 1,100)", chatter, "ch", "")
            mock_rand.assert_called_once_with(1, 100)
            assert result == "42"

    def test_random_swaps_bounds_when_lo_greater_than_hi(self):
        chatter = make_chatter(display_name="Nii")
        with patch("twitch.utils.substitution.random.randint", return_value=5) as mock_rand:
            substitute_variables("$(random 100,1)", chatter, "ch", "")
            mock_rand.assert_called_once_with(1, 100)

    def test_random_same_bounds(self):
        chatter = make_chatter(display_name="Nii")
        with patch("twitch.utils.substitution.random.randint", return_value=7) as mock_rand:
            result = substitute_variables("$(random 7,7)", chatter, "ch", "")
            mock_rand.assert_called_once_with(7, 7)
            assert result == "7"

    def test_multiple_random_calls(self):
        chatter = make_chatter(display_name="Nii")
        with patch("twitch.utils.substitution.random.randint", side_effect=[3, 9]) as mock_rand:
            result = substitute_variables("$(random 1,5) and $(random 8,10)", chatter, "ch", "")
            assert mock_rand.call_count == 2
            assert result == "3 and 9"


# ---------------------------------------------------------------------------
# $(pick a,b,c)
# ---------------------------------------------------------------------------


class TestPickVariable:
    def test_pick_calls_choice_with_parsed_items(self):
        chatter = make_chatter(display_name="Nii")
        with patch("twitch.utils.substitution.random.choice", return_value="rock") as mock_choice:
            result = substitute_variables("$(pick rock,paper,scissors)", chatter, "ch", "")
            mock_choice.assert_called_once_with(["rock", "paper", "scissors"])
            assert result == "rock"

    def test_pick_strips_whitespace_from_items(self):
        chatter = make_chatter(display_name="Nii")
        with patch("twitch.utils.substitution.random.choice", return_value="a") as mock_choice:
            substitute_variables("$(pick a, b, c)", chatter, "ch", "")
            mock_choice.assert_called_once_with(["a", "b", "c"])

    def test_pick_empty_list_returns_empty_string(self):
        chatter = make_chatter(display_name="Nii")
        # "$(pick )" — no items after strip
        result = substitute_variables("$(pick  )", chatter, "ch", "")
        assert result == ""

    def test_pick_single_item(self):
        chatter = make_chatter(display_name="Nii")
        with patch("twitch.utils.substitution.random.choice", return_value="only"):
            result = substitute_variables("$(pick only)", chatter, "ch", "")
            assert result == "only"


# ---------------------------------------------------------------------------
# Combined / edge cases
# ---------------------------------------------------------------------------


class TestCombined:
    def test_multiple_different_variables(self):
        chatter = make_chatter(display_name="Nii")
        with patch("twitch.utils.substitution.random.randint", return_value=7):
            result = substitute_variables(
                "$(user) rolled $(random 1,10) in $(channel)", chatter, "testchan", ""
            )
        assert result == "Nii rolled 7 in testchan"

    def test_no_variables_unchanged(self):
        chatter = make_chatter(display_name="Nii")
        text = "This has no variables at all."
        assert substitute_variables(text, chatter, "ch", "") == text

    def test_count_placeholder_not_substituted(self):
        # $(count) is documented as a placeholder — should remain as-is
        chatter = make_chatter(display_name="Nii")
        result = substitute_variables("used $(count) times", chatter, "ch", "")
        assert result == "used $(count) times"

    def test_unknown_variable_preserved(self):
        chatter = make_chatter(display_name="Nii")
        result = substitute_variables("$(unknown)", chatter, "ch", "")
        assert result == "$(unknown)"

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("$(user) $(user)", "Nii Nii"),
            ("$(channel) $(channel)", "ch ch"),
            ("$(query) $(query)", "hello hello"),
        ],
    )
    def test_repeated_variables(self, text: str, expected: str):
        chatter = make_chatter(display_name="Nii")
        assert substitute_variables(text, chatter, "ch", "hello") == expected
