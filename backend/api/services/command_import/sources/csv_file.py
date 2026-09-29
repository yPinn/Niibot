"""Bounded, portable CSV adapter for custom chat commands.

The two-column ``command,response`` form is the universal fallback. Niibot's
own export adds optional fields and a version marker so formula-neutralised
cells can be restored without changing command text on re-import.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass

from ..mapping import (
    check_length,
    classify,
    find_conflict,
    normalize_command_name,
    translate_variables,
)
from ..models import (
    ImportFieldAction,
    ImportFieldOutcome,
    ImportItem,
    ImportPreview,
    ImportSection,
    ImportSource,
    ImportStatus,
)

MAX_CSV_BYTES = 512 * 1024
MAX_CSV_ROWS = 500
MAX_COMMAND_NAME_LENGTH = 50
MAX_COOLDOWN_SECONDS = 86_400

_REQUIRED_HEADERS = frozenset({"command", "response"})
_OPTIONAL_HEADERS = frozenset({"niibot_version", "enabled", "min_role", "cooldown", "aliases"})
_KNOWN_HEADERS = _REQUIRED_HEADERS | _OPTIONAL_HEADERS
_VALID_ROLES = frozenset({"everyone", "subscriber", "vip", "moderator", "broadcaster"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", "disabled"})


class CommandCsvError(ValueError):
    """The uploaded CSV cannot be interpreted within the safe contract."""


@dataclass(frozen=True)
class CommandCsvExportRow:
    command: str
    response: str
    enabled: bool
    min_role: str
    cooldown: int | None
    aliases: str


def parse_command_csv(
    data: bytes,
    *,
    existing: set[str],
    source_channel: str,
) -> ImportPreview:
    """Parse an uploaded command CSV into a non-mutating import preview."""
    if not data:
        raise CommandCsvError("CSV 檔案是空的")
    if len(data) > MAX_CSV_BYTES:
        raise CommandCsvError("CSV 檔案超過 512 KiB 上限")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CommandCsvError("CSV 必須使用 UTF-8 編碼") from exc
    if "\x00" in text:
        raise CommandCsvError("CSV 含有無效字元")

    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        header_map = _normalise_headers(reader.fieldnames)
        missing = _REQUIRED_HEADERS - set(header_map)
        if missing:
            raise CommandCsvError(f"CSV 缺少必要欄位：{', '.join(sorted(missing))}")
        unknown_headers = sorted(set(header_map) - _KNOWN_HEADERS)

        items: list[ImportItem] = []
        taken = set(existing)
        row_count = 0
        for source_row in reader:
            if None in source_row:
                raise CommandCsvError(f"CSV 第 {reader.line_num} 列的欄位數量超過標題列")
            if _blank_row(source_row):
                continue
            row_count += 1
            if row_count > MAX_CSV_ROWS:
                raise CommandCsvError(f"CSV 最多可匯入 {MAX_CSV_ROWS} 筆指令")
            row = {name: source_row.get(original) for name, original in header_map.items()}
            item = _map_row(
                row,
                row_number=reader.line_num,
                taken=taken,
                unknown_headers=unknown_headers,
            )
            items.append(item)
            if item.section is ImportSection.CUSTOM and item.status in (
                ImportStatus.OK,
                ImportStatus.REVIEW,
            ):
                if item.command_name:
                    taken.add(item.command_name)
                taken.update(item.aliases)
    except CommandCsvError:
        raise
    except csv.Error as exc:
        raise CommandCsvError("CSV 格式無法解析") from exc

    if not items:
        raise CommandCsvError("CSV 沒有可預覽的指令列")
    return ImportPreview(source=ImportSource.CSV, source_channel=source_channel, items=items)


def encode_command_csv(rows: list[CommandCsvExportRow]) -> bytes:
    """Encode an importer-compatible, spreadsheet-safe UTF-8 BOM CSV."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(
        [
            "niibot_version",
            "command",
            "response",
            "enabled",
            "min_role",
            "cooldown",
            "aliases",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                "1",
                _spreadsheet_safe(row.command),
                _spreadsheet_safe(row.response),
                "true" if row.enabled else "false",
                row.min_role,
                row.cooldown if row.cooldown is not None else "",
                _spreadsheet_safe(row.aliases),
            ]
        )
    return b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")


def _map_row(
    row: dict[str, str | None],
    *,
    row_number: int,
    taken: set[str],
    unknown_headers: list[str],
) -> ImportItem:
    version = (row.get("niibot_version") or "").strip()
    if version not in ("", "1"):
        raise CommandCsvError(f"CSV 第 {row_number} 列使用不支援的 Niibot 版本：{version}")
    is_niibot_export = version == "1"
    raw_command = _restore_spreadsheet_safe(row.get("command") or "", is_niibot_export)
    response = _restore_spreadsheet_safe(row.get("response") or "", is_niibot_export)
    name = normalize_command_name(raw_command)

    notes: list[str] = []
    blockers: list[str] = []
    outcomes: list[ImportFieldOutcome] = []
    if unknown_headers:
        notes.append(f"未使用 CSV 欄位：{', '.join(unknown_headers)}")

    if not name:
        blockers.append("指令名稱無法轉換")
    elif len(name) > MAX_COMMAND_NAME_LENGTH:
        blockers.append(f"指令名稱超過 {MAX_COMMAND_NAME_LENGTH} 字")
    if row.get("response") is None or not response:
        blockers.append("回應內容不可為空")

    enabled, enabled_note = _parse_enabled(row.get("enabled"))
    if enabled_note:
        notes.append(enabled_note)
        outcomes.append(ImportFieldOutcome("enabled", ImportFieldAction.REVIEW, enabled_note))
    else:
        outcomes.append(
            ImportFieldOutcome(
                "enabled",
                ImportFieldAction.PRESERVED,
                f"保留 CSV 狀態：{'啟用' if enabled else '停用'}",
            )
        )

    role, role_note = _parse_role(row.get("min_role"))
    if role_note:
        notes.append(role_note)
        outcomes.append(ImportFieldOutcome("min_role", ImportFieldAction.REVIEW, role_note))
    else:
        outcomes.append(
            ImportFieldOutcome("min_role", ImportFieldAction.PRESERVED, f"保留最低身分：{role}")
        )

    cooldown, cooldown_note = _parse_cooldown(row.get("cooldown"))
    if cooldown_note:
        notes.append(cooldown_note)
        outcomes.append(ImportFieldOutcome("cooldown", ImportFieldAction.REVIEW, cooldown_note))
    elif row.get("cooldown") not in (None, ""):
        outcomes.append(
            ImportFieldOutcome(
                "cooldown",
                ImportFieldAction.PRESERVED,
                f"保留冷卻：{cooldown} 秒",
            )
        )

    translated, translate_notes, variable_blockers = translate_variables(response, "csv")
    notes.extend(translate_notes)
    blockers.extend(variable_blockers)
    blockers.extend(check_length(translated))

    aliases, alias_notes = _parse_aliases(
        _restore_spreadsheet_safe(row.get("aliases") or "", is_niibot_export),
        name=name,
        taken=taken,
    )
    notes.extend(alias_notes)

    # An invalid optional permission/state value never enables the command.
    if enabled_note or role_note or cooldown_note:
        enabled = False

    status, section, notes = classify(notes, blockers, find_conflict(name, taken))
    return ImportItem(
        key=f"csv:cmd:{row_number}:{name or 'invalid'}",
        section=section,
        status=status,
        source_name=raw_command if raw_command.startswith("!") else f"!{raw_command}",
        source_enabled=enabled,
        notes=notes,
        field_outcomes=outcomes,
        command_name=name or None,
        response=translated,
        original_response=response,
        cooldown=cooldown,
        min_role=role,
        aliases=aliases,
    )


def _normalise_headers(fieldnames: Sequence[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise CommandCsvError("CSV 缺少標題列")
    result: dict[str, str] = {}
    for original in fieldnames:
        normalised = (original or "").strip().lower()
        if not normalised:
            raise CommandCsvError("CSV 標題不可為空")
        if normalised in result:
            raise CommandCsvError(f"CSV 欄位重複：{normalised}")
        result[normalised] = original
    return result


def _blank_row(row: dict[str, str | None]) -> bool:
    return not any((value or "").strip() for value in row.values())


def _parse_enabled(raw: str | None) -> tuple[bool, str | None]:
    if raw is None or not raw.strip():
        return False, "CSV 未提供啟用狀態，安全預設為停用"
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True, None
    if value in _FALSE_VALUES:
        return False, None
    return False, f"無法辨識啟用狀態「{raw}」，安全預設為停用"


def _parse_role(raw: str | None) -> tuple[str, str | None]:
    if raw is None or not raw.strip():
        return "broadcaster", "CSV 未提供最低身分，安全預設為實況主限定"
    role = raw.strip().lower()
    if role in _VALID_ROLES:
        return role, None
    return "broadcaster", f"無法辨識最低身分「{raw}」，安全預設為實況主限定"


def _parse_cooldown(raw: str | None) -> tuple[int | None, str | None]:
    if raw is None or not raw.strip():
        return None, None
    try:
        cooldown = int(raw.strip())
    except ValueError:
        return None, f"無法辨識冷卻「{raw}」，改用頻道預設"
    if not 0 <= cooldown <= MAX_COOLDOWN_SECONDS:
        return None, f"冷卻必須介於 0 到 {MAX_COOLDOWN_SECONDS} 秒，改用頻道預設"
    return cooldown, None


def _parse_aliases(raw: str, *, name: str, taken: set[str]) -> tuple[list[str], list[str]]:
    aliases: list[str] = []
    notes: list[str] = []
    seen: set[str] = set()
    for candidate in raw.replace(";", "|").replace(",", "|").split("|"):
        alias = normalize_command_name(candidate)
        if not alias or alias == name or alias in seen:
            continue
        seen.add(alias)
        conflict = find_conflict(alias, taken)
        if conflict:
            notes.append(f"別名 !{alias} 與 !{conflict} 衝突，已略過")
            continue
        aliases.append(alias)
    return aliases, notes


def _spreadsheet_safe(value: str) -> str:
    if value.startswith("'") and _looks_like_spreadsheet_formula(value[1:]):
        return f"'{value}"
    if _looks_like_spreadsheet_formula(value):
        return f"'{value}"
    return value


def _restore_spreadsheet_safe(value: str, is_niibot_export: bool) -> str:
    if is_niibot_export and value.startswith("'"):
        candidate = value[1:]
        if candidate.startswith("'") and _looks_like_spreadsheet_formula(candidate[1:]):
            return candidate
        if _looks_like_spreadsheet_formula(candidate):
            return candidate
    return value


def _looks_like_spreadsheet_formula(value: str) -> bool:
    return value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n"))
