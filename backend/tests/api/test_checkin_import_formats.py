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


@pytest.mark.parametrize(
    "url",
    [
        "http://docs.google.com/spreadsheets/d/abc123/edit",
        "https://evil.example/spreadsheets/d/abc123/edit",
        "https://docs.google.com/other/d/abc123/edit",
        "https://docs.google.com/spreadsheets/d/abc123/edit?gid=not-a-number",
        "https://docs.google.com/spreadsheets/d/../../metadata/edit",
    ],
)
def test_google_sheets_url_rejects_ssrf_and_ambiguous_inputs(url: str) -> None:
    with pytest.raises(CheckinImportValidationError):
        build_google_sheets_export_url(url)


def test_google_sheets_url_builds_a_controlled_export_url() -> None:
    result = build_google_sheets_export_url(
        "https://docs.google.com/spreadsheets/d/abcDEF_123-xyz/edit?usp=sharing&gid=42"
    )

    assert result == (
        "https://docs.google.com/spreadsheets/d/abcDEF_123-xyz/export?format=csv&gid=42"
    )
    assert "usp" not in result


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
