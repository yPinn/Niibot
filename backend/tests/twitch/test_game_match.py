"""Unit tests for twitch.utils.game_match — which category `!game <text>` means."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from utils.game_match import fallback_queries, pick_category


def _g(game_id: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(id=game_id, name=name)


JC = _g("1", "Just Chatting")
LOL = _g("2", "League of Legends")
VAL = _g("3", "VALORANT")
CS = _g("4", "Counter-Strike")
DBD = _g("5", "Dead by Daylight")
GTA = _g("6", "Grand Theft Auto V")
TOP = [JC, LOL, VAL, CS, DBD, GTA]


def test_fallback_queries_words_then_prefixes_down_to_one_char():
    assert fallback_queries("valrant") == ["valran", "valra", "valr", "val", "va", "v"]
    assert fallback_queries("Lgue Legends")[:2] == ["Legends", "Lgue"]
    assert fallback_queries("x") == []


@pytest.mark.parametrize(
    ("query", "searched", "expected"),
    [
        # popularity beats a text match that merely ranked first
        ("val", [_g("90", "Valkyrie Profile"), VAL], VAL),
        ("val", [_g("90", "Valkyrie Profile")], VAL),  # not even in the search result
        ("lol", [_g("91", "LOL"), LOL], LOL),  # exact-name obscure loses to abbreviation
        ("LoL", [_g("91", "LOL")], LOL),
        ("cs", [_g("92", "CS:GO Gunsmith")], CS),
        ("dbd", [], DBD),
        ("gta", [], GTA),  # prefix of the initials "gtav"
        ("valorant", [VAL], VAL),
        ("just chatting", [JC], JC),
        ("valrant", [_g("90", "Valkyrie Profile")], VAL),  # typo: similarity + popularity
    ],
)
def test_popular_category_wins(query, searched, expected):
    assert pick_category(query, searched, TOP) is expected


def test_exact_name_of_obscure_game_beats_text_match():
    knight, silksong = _g("8", "Hollow Knight"), _g("9", "Hollow Knight: Silksong")
    assert pick_category("hollow knight", [silksong, knight], TOP) is knight


def test_more_popular_of_two_equal_exact_names_wins():
    twin = _g("99", "Counter-Strike")
    assert pick_category("counter-strike", [twin, CS], TOP) is CS


def test_unrelated_popular_game_is_not_chosen():
    indie = _g("50", "Tiny Garden")
    assert pick_category("tiny garden", [indie], TOP) is indie


def test_without_popularity_data_it_is_plain_text_matching():
    first, second = _g("1", "League of Fun"), _g("2", "League of Legends")
    assert pick_category("league of", [first, second], []) is first  # Twitch order on ties
    assert pick_category("league of legends", [first, second], []) is second  # exact name


def test_nothing_to_choose_from():
    assert pick_category("zzzzzz", [], TOP) is None
    assert pick_category("zzzzzz", [], []) is None
