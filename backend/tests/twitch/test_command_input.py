"""Unit tests for twitch.utils.command_input — chat argument normalisation."""

from __future__ import annotations

import pytest

from utils.command_input import (
    clean_text,
    parse_login,
    parse_number,
    parse_riot_id,
    split_tags,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("League of Legends", "League of Legends"),
        (";League of Legends'", "League of Legends"),
        ("  `lol` ;", "lol"),
        ("，英雄聯盟。", "英雄聯盟"),
        ("「Valorant」", "Valorant"),
        ("Dead   by    Daylight", "Dead by Daylight"),
        ("Fall Guys: Ultimate Knockout", "Fall Guys: Ultimate Knockout"),
        ("Marvel's Spider-Man", "Marvel's Spider-Man"),
        ("Jeopardy!", "Jeopardy!"),
        (";';", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_clean_text(raw, expected):
    assert clean_text(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("somechannel", "somechannel"),
        ("@SomeChannel", "somechannel"),
        ("＠SomeChannel", "somechannel"),
        (";@some_channel'", "some_channel"),
        ("https://www.twitch.tv/SomeChannel", "somechannel"),
        ("twitch.tv/somechannel?sr=a", "somechannel"),
        ("; somechannel extra words", "somechannel"),
        ("ＳｏｍｅＣｈａｎｎｅｌ", "somechannel"),
    ],
)
def test_parse_login_accepts(raw, expected):
    assert parse_login(raw) == expected


@pytest.mark.parametrize("raw", ["", None, ";'", "小明", "小明_abc", "名稱 @"])
def test_parse_login_rejects(raw):
    assert parse_login(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Foo#TW2", ("Foo", "TW2")),
        ("Foo Bar#TW2", ("Foo Bar", "TW2")),
        ("Foo Bar #TW2", ("Foo Bar", "TW2")),
        ("Foo＃TW2", ("Foo", "TW2")),
        ("Foo# TW2", ("Foo", "TW2")),
        (";Foo#TW2'", ("Foo", "TW2")),
        ("Foo  Bar#TW2;", ("Foo Bar", "TW2")),
        ("玩家#1234", ("玩家", "1234")),
    ],
)
def test_parse_riot_id_accepts(raw, expected):
    assert parse_riot_id(raw) == expected


@pytest.mark.parametrize("raw", ["Foo", "#TW2", "Foo#", "Foo# ;", "", None])
def test_parse_riot_id_rejects(raw):
    assert parse_riot_id(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("中文,聊天,New", ["中文", "聊天", "New"]),
        (" 中文 , 聊天 ,New", ["中文", "聊天", "New"]),
        ("中文 聊天 New", ["中文", "聊天", "New"]),
        ("中文，聊天、New；Chill", ["中文", "聊天", "New", "Chill"]),
        ("#中文 #聊天", ["中文", "聊天"]),
        ("English english ENGLISH", ["English"]),
        (";中文';", ["中文"]),
        (",;", []),
        ("", []),
        (None, []),
    ],
)
def test_split_tags(raw, expected):
    assert split_tags(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3", 3),
        ("#3", 3),
        ("３", 3),
        ("3;", 3),
        (" '12' ", 12),
        ("abc", None),
        ("3 4", None),
        ("", None),
    ],
)
def test_parse_number(raw, expected):
    assert parse_number(raw) == expected
