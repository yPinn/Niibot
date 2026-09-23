"""Typed preview and receipt records for check-in carry-over imports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class ImportRowStatus(StrEnum):
    READY = "ready"
    REVIEW = "review"
    INVALID = "invalid"
    UNRESOLVED = "unresolved"
    CONFLICT = "conflict"


class IdentityResolution(StrEnum):
    TWITCH_ID = "twitch_id"
    USERNAME = "username"
    DISPLAY_AS_LOGIN = "display_as_login"
    MANUAL = "manual"


class IdentityTargetType(StrEnum):
    USERNAME = "username"
    USER_ID = "user_id"


@dataclass(frozen=True, slots=True)
class IdentityRemap:
    row_key: str
    target_type: IdentityTargetType
    value: str


@dataclass(frozen=True, slots=True)
class ImportPreviewRow:
    key: str
    source_row: int
    user_id: str | None
    username: str | None
    display_name: str | None
    total_days: int | None
    last_checkin_date: date | None
    current_streak: int | None
    daily_order: int | None
    status: ImportRowStatus
    issues: tuple[str, ...] = ()
    source_user_id: str | None = None
    source_username: str | None = None
    source_display_name: str | None = None
    identity_resolution: IdentityResolution | None = None


@dataclass(frozen=True, slots=True)
class CheckinImportPreview:
    source: str
    source_format: str
    source_timezone: str
    through_date: date
    content_sha256: str
    column_mapping: tuple[tuple[str, int], ...]
    sheet_name: str | None
    rows: tuple[ImportPreviewRow, ...]


@dataclass(frozen=True, slots=True)
class CheckinImportResult:
    batch_id: str
    imported_rows: int
    already_applied: bool = False
