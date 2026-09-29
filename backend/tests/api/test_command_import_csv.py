"""Portable command CSV import/export contract."""

from __future__ import annotations

import csv
import io

import pytest

from services.command_import.models import ImportSection, ImportStatus
from services.command_import.sources.csv_file import (
    MAX_CSV_BYTES,
    MAX_CSV_ROWS,
    CommandCsvError,
    CommandCsvExportRow,
    encode_command_csv,
    parse_command_csv,
)


def _csv(text: str) -> bytes:
    return text.encode("utf-8")


def test_minimal_csv_is_safe_by_default() -> None:
    preview = parse_command_csv(
        _csv("command,response\nhello,Hello chat\n"),
        existing=set(),
        source_channel="upload.csv",
    )

    (item,) = preview.items
    assert item.command_name == "hello"
    assert item.response == "Hello chat"
    assert item.source_enabled is False
    assert item.min_role == "broadcaster"
    assert item.status is ImportStatus.REVIEW
    assert any("停用" in note for note in item.notes)
    assert any("最低身分" in note for note in item.notes)


def test_extended_csv_preserves_supported_fields_and_zero_cooldown() -> None:
    preview = parse_command_csv(
        _csv(
            "command,response,enabled,min_role,cooldown,aliases\n"
            'hello,"Hello, chat",true,moderator,0,"hi|hey"\n'
        ),
        existing=set(),
        source_channel="upload.csv",
    )

    (item,) = preview.items
    assert item.source_enabled is True
    assert item.min_role == "moderator"
    assert item.cooldown == 0
    assert item.aliases == ["hi", "hey"]
    assert item.status is ImportStatus.OK


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("enabled", "maybe"),
        ("min_role", "regular"),
        ("cooldown", "-1"),
    ],
)
def test_unknown_or_unsafe_optional_value_is_disabled_for_review(column: str, value: str) -> None:
    headers = ["command", "response", column]
    preview = parse_command_csv(
        _csv(f"{','.join(headers)}\nhello,Hello,{value}\n"),
        existing=set(),
        source_channel="upload.csv",
    )

    (item,) = preview.items
    assert item.source_enabled is False
    assert item.status is ImportStatus.REVIEW
    assert item.notes


def test_reserved_name_and_cross_row_alias_collision_are_not_created() -> None:
    preview = parse_command_csv(
        _csv("command,response,aliases\ncmd,reserved,\nhello,one,hi|cmd\nother,two,hi\n"),
        existing=set(),
        source_channel="upload.csv",
    )

    reserved, hello, other = preview.items
    assert reserved.status is ImportStatus.CONFLICT
    assert hello.aliases == ["hi"]
    assert hello.status is ImportStatus.REVIEW
    assert other.aliases == []
    assert other.status is ImportStatus.REVIEW


def test_remote_or_eval_variables_remain_visible_but_never_importable() -> None:
    preview = parse_command_csv(
        _csv('command,response\npb,"$(customapi https://example.com)"\n'),
        existing=set(),
        source_channel="upload.csv",
    )

    (item,) = preview.items
    assert item.section is ImportSection.UNSUPPORTED
    assert item.status is ImportStatus.UNSUPPORTED
    assert item.source_enabled is False


def test_unknown_columns_are_reported_instead_of_silently_claimed() -> None:
    preview = parse_command_csv(
        _csv("command,response,cost\nhello,Hello,100\n"),
        existing=set(),
        source_channel="upload.csv",
    )

    (item,) = preview.items
    assert item.status is ImportStatus.REVIEW
    assert any("cost" in note for note in item.notes)


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff\xfe\x00",
        _csv("response\nmissing command\n"),
        b"x" * (MAX_CSV_BYTES + 1),
    ],
    ids=["invalid-utf8", "missing-header", "oversized"],
)
def test_malformed_or_oversized_csv_is_rejected(payload: bytes) -> None:
    with pytest.raises(CommandCsvError):
        parse_command_csv(payload, existing=set(), source_channel="upload.csv")


def test_extra_unheaded_column_is_rejected_without_crashing() -> None:
    with pytest.raises(CommandCsvError, match="欄位數量"):
        parse_command_csv(
            _csv("command,response\nhello,Hello,unexpected\n"),
            existing=set(),
            source_channel="upload.csv",
        )


def test_unknown_niibot_schema_version_is_rejected() -> None:
    with pytest.raises(CommandCsvError, match="版本"):
        parse_command_csv(
            _csv("niibot_version,command,response\n2,hello,Hello\n"),
            existing=set(),
            source_channel="upload.csv",
        )


def test_row_limit_is_bounded() -> None:
    rows = "".join(f"c{i},response\n" for i in range(MAX_CSV_ROWS + 1))
    with pytest.raises(CommandCsvError):
        parse_command_csv(
            _csv(f"command,response\n{rows}"),
            existing=set(),
            source_channel="upload.csv",
        )


def test_bad_row_is_reported_without_losing_valid_rows() -> None:
    preview = parse_command_csv(
        _csv("command,response\nhello\nworld,valid\n"),
        existing=set(),
        source_channel="upload.csv",
    )

    assert preview.items[0].section is ImportSection.UNSUPPORTED
    assert preview.items[1].section is ImportSection.CUSTOM


def test_export_is_formula_safe_and_round_trips_niibot_rows() -> None:
    original = CommandCsvExportRow(
        command="formula",
        response="=1+1",
        enabled=True,
        min_role="vip",
        cooldown=0,
        aliases="@alias|safe",
    )

    encoded = encode_command_csv([original])
    decoded = encoded.decode("utf-8-sig")
    exported = list(csv.DictReader(io.StringIO(decoded)))
    assert exported[0]["response"] == "'=1+1"
    assert exported[0]["aliases"].startswith("'")

    preview = parse_command_csv(encoded, existing=set(), source_channel="niibot.csv")
    (item,) = preview.items
    assert item.response == "=1+1"
    assert item.aliases == ["alias", "safe"]
    assert item.source_enabled is True
    assert item.min_role == "vip"
    assert item.cooldown == 0


def test_export_round_trip_restores_formula_with_leading_spaces() -> None:
    original = CommandCsvExportRow(
        command="formula",
        response="  =1+1",
        enabled=False,
        min_role="broadcaster",
        cooldown=None,
        aliases="",
    )

    encoded = encode_command_csv([original])
    exported = next(csv.DictReader(io.StringIO(encoded.decode("utf-8-sig"))))
    assert exported["response"] == "'  =1+1"

    preview = parse_command_csv(encoded, existing=set(), source_channel="niibot.csv")
    assert preview.items[0].response == "  =1+1"


def test_export_round_trip_preserves_literal_apostrophe_before_formula() -> None:
    original = CommandCsvExportRow(
        command="literal",
        response="'=1+1",
        enabled=False,
        min_role="broadcaster",
        cooldown=None,
        aliases="",
    )

    encoded = encode_command_csv([original])
    exported = next(csv.DictReader(io.StringIO(encoded.decode("utf-8-sig"))))
    assert exported["response"] == "''=1+1"

    preview = parse_command_csv(encoded, existing=set(), source_channel="niibot.csv")
    assert preview.items[0].response == "'=1+1"
