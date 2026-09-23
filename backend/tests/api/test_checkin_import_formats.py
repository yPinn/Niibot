"""Contract tests for check-in summary tabular adapters."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import pytest

from services.checkin_import.formats import (
    CheckinImportValidationError,
    InvalidSummaryRow,
    build_google_sheets_export_url,
    fetch_google_sheet_csv,
    inspect_summary_bytes,
    parse_summary_bytes,
)


def _xlsx(rows: list[list[str]], *, formula_cell: str | None = None) -> bytes:
    """Build the smallest XLSX fixture needed by the read-only adapter."""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
      <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
    </Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
    </Relationships>"""
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <sheets><sheet name="Checkins" sheetId="1" state="visible" r:id="rId1"/></sheets>
    </workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
    </Relationships>"""

    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            column = chr(64 + col_index)
            coordinate = f"{column}{row_index}"
            if coordinate == formula_cell:
                cells.append(f'<c r="{coordinate}"><f>1+1</f><v>2</v></c>')
            else:
                escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                cells.append(f'<c r="{coordinate}" t="inlineStr"><is><t>{escaped}</t></is></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    worksheet = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData>{"".join(xml_rows)}</sheetData>
    </worksheet>"""

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return output.getvalue()


@pytest.mark.parametrize(
    ("filename", "payload"),
    [
        (
            "checkins.csv",
            b"\xef\xbb\xbfUsername,Count,LastDate,Streak,TodayOrder\r\nalice,15,2026-09-10,3,5\r\n",
        ),
        (
            "checkins.tsv",
            b"Username\tCount\tLastDate\tStreak\tTodayOrder\nalice\t15\t2026-09-10\t3\t5\n",
        ),
    ],
)
def test_text_adapters_share_the_same_canonical_result(filename: str, payload: bytes) -> None:
    parsed = parse_summary_bytes(filename, payload, through_date=date(2026, 9, 10))

    assert len(parsed.rows) == 1
    assert parsed.rows[0].username == "alice"
    assert parsed.rows[0].total_days == 15
    assert parsed.rows[0].last_checkin_date == date(2026, 9, 10)
    assert parsed.rows[0].current_streak == 3
    assert parsed.rows[0].daily_order == 5


def test_xlsx_adapter_uses_the_same_canonical_result() -> None:
    payload = _xlsx(
        [
            ["Username", "Count", "LastDate", "Streak", "TodayOrder"],
            ["alice", "15", "2026-09-10", "3", "5"],
        ]
    )

    parsed = parse_summary_bytes("checkins.xlsx", payload, through_date=date(2026, 9, 10))

    assert parsed.format == "xlsx"
    assert parsed.sheet_name == "Checkins"
    assert parsed.rows[0].username == "alice"
    assert parsed.rows[0].total_days == 15


def test_xlsx_rejects_formula_in_a_mapped_column() -> None:
    payload = _xlsx(
        [["Username", "Count", "LastDate"], ["alice", "2", "2026-09-10"]],
        formula_cell="B2",
    )

    with pytest.raises(CheckinImportValidationError, match="公式"):
        parse_summary_bytes("checkins.xlsx", payload, through_date=date(2026, 9, 10))


def test_ambiguous_header_fails_the_whole_file() -> None:
    with pytest.raises(CheckinImportValidationError):
        parse_summary_bytes(
            "checkins.csv",
            b"Username,User Name,Count,LastDate\nalice,Alice,2,2026-09-10\n",
            through_date=date(2026, 9, 10),
        )


@pytest.mark.parametrize(
    "payload",
    [
        b"Username,Count,LastDate\nalice,0,2026-09-10\n",
        b"Username,Count,LastDate,Streak\nalice,2,2026-09-10,3\n",
        b"Username,Count,LastDate\nalice,2,2026-09-11\n",
        b"Username,Count,LastDate\nalice,2,09/10/2026\n",
    ],
)
def test_invalid_data_row_is_preserved_for_preview(payload: bytes) -> None:
    parsed = parse_summary_bytes("checkins.csv", payload, through_date=date(2026, 9, 10))

    assert isinstance(parsed.rows[0], InvalidSummaryRow)
    assert parsed.rows[0].source_row == 2
    assert parsed.rows[0].issue


def test_platform_user_id_can_replace_username() -> None:
    parsed = parse_summary_bytes(
        "checkins.csv",
        b"Twitch User ID,Count,LastDate\n123456,8,2026-09-09\n",
        through_date=date(2026, 9, 10),
    )

    assert parsed.rows[0].platform_user_id == "123456"
    assert parsed.rows[0].username is None


def test_display_name_can_be_the_only_source_identity() -> None:
    parsed = parse_summary_bytes(
        "checkins.csv",
        "DisplayName,Count,LastDate\n愛麗絲,8,2026-09-09\n".encode(),
        through_date=date(2026, 9, 10),
    )

    assert parsed.rows[0].platform_user_id is None
    assert parsed.rows[0].username is None
    assert parsed.rows[0].display_name == "愛麗絲"


@pytest.mark.parametrize(
    "display_name",
    ["", "x" * 129],
    ids=["empty", "too-long"],
)
def test_display_name_only_identity_must_be_present_and_bounded(display_name: str) -> None:
    parsed = parse_summary_bytes(
        "checkins.csv",
        f"DisplayName,Count,LastDate\n{display_name},8,2026-09-09\n".encode(),
        through_date=date(2026, 9, 10),
    )

    assert isinstance(parsed.rows[0], InvalidSummaryRow)
    assert parsed.rows[0].issue


def test_manual_column_mapping_accepts_unknown_source_headers() -> None:
    parsed = parse_summary_bytes(
        "checkins.csv",
        "觀眾帳戶,累計簽到,最近一次,連續紀錄\nalice,8,2026-09-09,3\n".encode(),
        through_date=date(2026, 9, 10),
        column_mapping={
            "username": 0,
            "total_days": 1,
            "last_checkin_date": 2,
            "current_streak": 3,
        },
    )

    assert parsed.rows[0].username == "alice"
    assert parsed.rows[0].total_days == 8
    assert parsed.rows[0].last_checkin_date == date(2026, 9, 9)
    assert parsed.rows[0].current_streak == 3


def test_column_inspection_returns_headers_and_safe_alias_suggestions() -> None:
    inspected = inspect_summary_bytes(
        "checkins.csv",
        b"user name,COUNT,custom date\nalice,8,2026-09-09\n",
    )

    assert inspected.headers == ("user name", "COUNT", "custom date")
    assert inspected.suggested_mapping == {"username": 0, "total_days": 1}


def test_column_inspection_enforces_row_limit_before_returning_headers() -> None:
    payload = b"Username,Count,LastDate\n" + b"alice,1,2026-09-10\n" * 10_001

    with pytest.raises(CheckinImportValidationError, match="資料列數"):
        inspect_summary_bytes("checkins.csv", payload)


@pytest.mark.parametrize(
    "column_mapping",
    [
        {"username": 0, "total_days": 1, "last_checkin_date": 9},
        {"username": 0, "total_days": 1, "last_checkin_date": 1},
        {"unknown": 0, "total_days": 1, "last_checkin_date": 2},
    ],
)
def test_manual_column_mapping_rejects_out_of_range_duplicate_and_unknown_fields(
    column_mapping: dict[str, int],
) -> None:
    with pytest.raises(CheckinImportValidationError):
        parse_summary_bytes(
            "checkins.csv",
            b"viewer,total,last\nalice,8,2026-09-09\n",
            through_date=date(2026, 9, 10),
            column_mapping=column_mapping,
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://docs.google.com/spreadsheets/d/abc123/edit",
        "https://evil.example/spreadsheets/d/abc123/edit",
        "https://docs.google.com/other/d/abc123/edit",
        "https://docs.google.com/spreadsheets/d/abc123/edit?gid=not-a-number",
        "https://docs.google.com/spreadsheets/d/abc123/edit?gid=0#gid=1",
        "https://docs.google.com:bad/spreadsheets/d/abc123/edit?gid=0",
        "https://docs.google.com/spreadsheets/d/../../metadata/edit",
    ],
)
def test_google_sheets_url_rejects_ssrf_and_ambiguous_inputs(url: str) -> None:
    with pytest.raises(CheckinImportValidationError):
        build_google_sheets_export_url(url)


def test_google_sheets_url_builds_a_controlled_export_url() -> None:
    result = build_google_sheets_export_url(
        "https://docs.google.com/spreadsheets/d/abcDEF_123-xyz/edit?usp=sharing&gid=42#gid=42"
    )

    assert result == (
        "https://docs.google.com/spreadsheets/d/abcDEF_123-xyz/export?format=csv&gid=42"
    )
    assert "usp" not in result


@pytest.mark.asyncio
async def test_google_sheets_fetch_follows_one_allowlisted_export_redirect() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "docs.google.com":
            return httpx.Response(
                307,
                headers={
                    "location": (
                        "https://doc-0k-6o-sheets.googleusercontent.com/export/token/"
                        "abc123?format=csv&gid=0"
                    )
                },
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/csv"},
            content=b"Username,Count,LastDate\nalice,2,2026-09-10\n",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        payload = await fetch_google_sheet_csv(
            "https://docs.google.com/spreadsheets/d/abc123/edit?gid=0#gid=0", client
        )

    assert payload.startswith(b"Username")
    assert len(seen) == 2
    assert seen[1].startswith("https://doc-0k-6o-sheets.googleusercontent.com/")


@pytest.mark.asyncio
async def test_google_sheets_fetch_rejects_a_second_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            307,
            headers={
                "location": (
                    "https://doc-0k-6o-sheets.googleusercontent.com/export/token/"
                    "abc123?format=csv&gid=0"
                )
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CheckinImportValidationError, match="多次重新導向"):
            await fetch_google_sheet_csv(
                "https://docs.google.com/spreadsheets/d/abc123/edit?gid=0", client
            )


@pytest.mark.asyncio
async def test_google_sheets_fetch_rejects_redirects_and_large_responses() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(302, headers={"location": "https://evil.example/data"})
        return httpx.Response(
            200,
            headers={"content-type": "text/csv"},
            content=b"x" * (2 * 1024 * 1024 + 1),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CheckinImportValidationError, match="重新導向"):
            await fetch_google_sheet_csv(
                "https://docs.google.com/spreadsheets/d/abc123/edit?gid=0", client
            )
        with pytest.raises(CheckinImportValidationError, match="大小"):
            await fetch_google_sheet_csv(
                "https://docs.google.com/spreadsheets/d/abc123/edit?gid=0", client
            )


@pytest.mark.asyncio
async def test_google_sheets_fetch_returns_csv_without_following_user_url() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200,
            headers={"content-type": "text/csv; charset=utf-8"},
            content=b"Username,Count,LastDate\nalice,2,2026-09-10\n",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        payload = await fetch_google_sheet_csv(
            "https://docs.google.com/spreadsheets/d/abc123/edit?usp=sharing&gid=7", client
        )

    assert payload.startswith(b"Username")
    assert seen == ["https://docs.google.com/spreadsheets/d/abc123/export?format=csv&gid=7"]
