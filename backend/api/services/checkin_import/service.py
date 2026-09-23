"""Identity resolution, preview caching, and atomic check-in carry-over apply."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections import Counter
from dataclasses import replace
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import asyncpg

from services.twitch_api import TwitchAPIClient, TwitchUsersLookupError
from shared.cache import AsyncTTLCache
from shared.errors import ConflictError, UpstreamError

from .formats import InvalidSummaryRow, ParsedSummary, SummaryRow
from .models import (
    CheckinImportPreview,
    CheckinImportResult,
    IdentityRemap,
    IdentityResolution,
    IdentityTargetType,
    ImportPreviewRow,
    ImportRowStatus,
)

_SOURCE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TWITCH_LOGIN = re.compile(r"^[A-Za-z0-9_]{1,25}$")
_TWITCH_USER_ID = re.compile(r"^[0-9]{1,32}$")
_PREVIEW_CACHE: AsyncTTLCache = AsyncTTLCache(maxsize=64, ttl=600.0, name="checkin_import.preview")


class PreviewNotFoundError(Exception):
    """The preview expired or does not belong to this user and tenant."""


class CheckinImportConflictError(ConflictError):
    code = "CHECKIN_IMPORT.CONFLICT"
    user_message = "部分觀眾已有簽到資料，請重新預覽"


class CheckinIdentityLookupError(UpstreamError):
    code = "CHECKIN_IMPORT.IDENTITY_UNAVAILABLE"
    user_message = "Twitch 身份暫時無法確認，請稍後再試"


def stash_preview(user_id: str, channel_id: str, preview: CheckinImportPreview) -> str:
    import_id = secrets.token_urlsafe(16)
    _PREVIEW_CACHE.set(f"preview:{import_id}", (user_id, channel_id, preview))
    return import_id


def load_preview(user_id: str, channel_id: str, import_id: str) -> CheckinImportPreview:
    entry = _PREVIEW_CACHE.get(f"preview:{import_id}")
    if (
        not isinstance(entry, tuple)
        or len(entry) != 3
        or entry[0] != user_id
        or entry[1] != channel_id
    ):
        raise PreviewNotFoundError(import_id)
    return entry[2]


def _chunks(values: list[str], size: int = 100):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _row_key(row: SummaryRow, user_id: str | None) -> str:
    stable = user_id or row.source_key
    digest = hashlib.sha256(f"{row.source_row}:{stable}".encode()).hexdigest()[:24]
    return f"row-{digest}"


class CheckinImportService:
    def __init__(self, pool: asyncpg.Pool, twitch_api: TwitchAPIClient) -> None:
        self.pool = pool
        self.twitch_api = twitch_api

    async def preview(
        self,
        *,
        channel_id: str,
        source: str,
        source_timezone: str,
        through_date: date,
        parsed: ParsedSummary,
        today: date | None = None,
    ) -> CheckinImportPreview:
        if not _SOURCE_SLUG.fullmatch(source):
            raise ValueError("source must be a lowercase slug")
        try:
            ZoneInfo(source_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("invalid source timezone") from exc
        if today is not None and through_date > today:
            raise ValueError("through date cannot be in the future")

        valid_rows = [row for row in parsed.rows if isinstance(row, SummaryRow)]
        ids = list(
            dict.fromkeys(row.platform_user_id for row in valid_rows if row.platform_user_id)
        )
        logins = list(
            dict.fromkeys(
                login.casefold()
                for row in valid_rows
                for login in (
                    row.username,
                    (
                        row.display_name
                        if not row.platform_user_id
                        and not row.username
                        and row.display_name
                        and _TWITCH_LOGIN.fullmatch(row.display_name)
                        else None
                    ),
                )
                if login
            )
        )
        try:
            users_by_id = await self._users_by_ids(ids)
            users_by_login = await self._users_by_logins(logins)
        except TwitchUsersLookupError as exc:
            raise CheckinIdentityLookupError() from exc

        preview_rows: list[ImportPreviewRow] = [
            ImportPreviewRow(
                key=f"invalid-{row.source_row}",
                source_row=row.source_row,
                user_id=None,
                username=None,
                display_name=None,
                total_days=None,
                last_checkin_date=None,
                current_streak=None,
                daily_order=None,
                status=ImportRowStatus.INVALID,
                issues=(row.issue,),
            )
            for row in parsed.rows
            if isinstance(row, InvalidSummaryRow)
        ]
        preview_rows.extend(
            self._resolve_row(row, users_by_id=users_by_id, users_by_login=users_by_login)
            for row in valid_rows
        )
        preview_rows = await self._with_identity_conflicts(channel_id, preview_rows)
        preview_rows.sort(key=lambda row: row.source_row)

        return CheckinImportPreview(
            source=source,
            source_format=parsed.format,
            source_timezone=source_timezone,
            through_date=through_date,
            content_sha256=parsed.content_sha256,
            column_mapping=parsed.column_mapping,
            sheet_name=parsed.sheet_name,
            rows=tuple(preview_rows),
        )

    @staticmethod
    def _resolve_row(
        row: SummaryRow,
        *,
        users_by_id: dict[str, dict],
        users_by_login: dict[str, dict],
    ) -> ImportPreviewRow:
        user: dict | None = None
        status = ImportRowStatus.UNRESOLVED
        issues: list[str] = []
        resolution: IdentityResolution | None = None

        if row.platform_user_id:
            user = users_by_id.get(row.platform_user_id)
            resolution = IdentityResolution.TWITCH_ID
            if user is None:
                issues.append("找不到來源 Twitch ID")
                if row.username and users_by_login.get(row.username.casefold()):
                    issues.append("來源帳號指向其他有效帳號")
                    status = ImportRowStatus.CONFLICT
            else:
                status = ImportRowStatus.READY
                current_login = str(user.get("login", "")).casefold()
                if row.username and current_login != row.username.casefold():
                    login_user = users_by_login.get(row.username.casefold())
                    if login_user and str(login_user.get("id", "")) != str(user.get("id", "")):
                        status = ImportRowStatus.CONFLICT
                        issues.append("來源 Twitch ID 與帳號指向不同使用者")
                    else:
                        status = ImportRowStatus.REVIEW
                        issues.append("來源帳號已變更，將使用 Twitch 目前名稱")
        elif row.username:
            user = users_by_login.get(row.username.casefold())
            resolution = IdentityResolution.USERNAME
            if user is None:
                issues.append("找不到 Twitch 帳號，可指定目前帳號")
            else:
                status = ImportRowStatus.READY
        elif row.display_name and _TWITCH_LOGIN.fullmatch(row.display_name):
            user = users_by_login.get(row.display_name.casefold())
            resolution = IdentityResolution.DISPLAY_AS_LOGIN
            if user is None:
                issues.append("找不到 Twitch 帳號，可指定目前帳號")
            else:
                status = ImportRowStatus.REVIEW
                issues.append("顯示名稱已按 Twitch 帳號查證，請確認")
        else:
            issues.append("顯示名稱無法唯一查詢，請指定目前帳號")

        user_id = str(user["id"]) if user and user.get("id") else None
        return ImportPreviewRow(
            key=_row_key(row, user_id),
            source_row=row.source_row,
            user_id=user_id,
            username=str(user.get("login")) if user and user.get("login") else None,
            display_name=(
                str(user.get("display_name")) if user and user.get("display_name") else None
            ),
            total_days=row.total_days,
            last_checkin_date=row.last_checkin_date,
            current_streak=row.current_streak,
            daily_order=row.daily_order,
            status=status,
            issues=tuple(issues),
            source_user_id=row.platform_user_id,
            source_username=row.username,
            source_display_name=row.display_name,
            identity_resolution=resolution if user is not None else None,
        )

    async def _with_identity_conflicts(
        self,
        channel_id: str,
        rows: list[ImportPreviewRow],
    ) -> list[ImportPreviewRow]:
        resolved_ids = [row.user_id for row in rows if row.user_id]
        duplicate_ids = {user_id for user_id, count in Counter(resolved_ids).items() if count > 1}
        existing_ids = await self._existing_user_ids(channel_id, resolved_ids)
        result: list[ImportPreviewRow] = []
        for row in rows:
            issues = list(row.issues)
            status = row.status
            if row.user_id in duplicate_ids:
                status = ImportRowStatus.CONFLICT
                if "多列資料解析到同一個 Twitch 帳號" not in issues:
                    issues.append("多列資料解析到同一個 Twitch 帳號")
            if row.user_id in existing_ids:
                status = ImportRowStatus.CONFLICT
                if "這位觀眾已有 Niibot 簽到或轉移資料" not in issues:
                    issues.append("這位觀眾已有 Niibot 簽到或轉移資料")
            result.append(replace(row, status=status, issues=tuple(issues)))
        return result

    async def remap_identities(
        self,
        *,
        channel_id: str,
        preview: CheckinImportPreview,
        mappings: tuple[IdentityRemap, ...],
    ) -> CheckinImportPreview:
        if not mappings or len(mappings) > 100:
            raise ValueError("identity mappings must contain 1 to 100 rows")
        mapping_keys = [mapping.row_key for mapping in mappings]
        if len(mapping_keys) != len(set(mapping_keys)):
            raise ValueError("identity mapping row keys must be unique")

        rows_by_key = {row.key: row for row in preview.rows}
        for mapping in mappings:
            row = rows_by_key.get(mapping.row_key)
            if row is None or row.status is not ImportRowStatus.UNRESOLVED:
                raise ValueError("only unresolved rows may be remapped")
            if mapping.target_type is IdentityTargetType.USER_ID:
                if not _TWITCH_USER_ID.fullmatch(mapping.value):
                    raise ValueError("invalid Twitch user id")
            elif not _TWITCH_LOGIN.fullmatch(mapping.value):
                raise ValueError("invalid Twitch username")

        ids = list(
            dict.fromkeys(
                mapping.value
                for mapping in mappings
                if mapping.target_type is IdentityTargetType.USER_ID
            )
        )
        logins = list(
            dict.fromkeys(
                mapping.value.casefold()
                for mapping in mappings
                if mapping.target_type is IdentityTargetType.USERNAME
            )
        )
        try:
            users_by_id = await self._users_by_ids(ids)
            users_by_login = await self._users_by_logins(logins)
        except TwitchUsersLookupError as exc:
            raise CheckinIdentityLookupError() from exc

        targets = {mapping.row_key: mapping for mapping in mappings}
        remapped_rows: list[ImportPreviewRow] = []
        for row in preview.rows:
            target = targets.get(row.key)
            if target is None:
                remapped_rows.append(row)
                continue
            user = (
                users_by_id.get(target.value)
                if target.target_type is IdentityTargetType.USER_ID
                else users_by_login.get(target.value.casefold())
            )
            if user is None or not user.get("id") or not user.get("login"):
                remapped_rows.append(replace(row, issues=("找不到指定的 Twitch 帳號，請重新輸入",)))
                continue
            remapped_rows.append(
                replace(
                    row,
                    user_id=str(user["id"]),
                    username=str(user["login"]),
                    display_name=(str(user["display_name"]) if user.get("display_name") else None),
                    status=ImportRowStatus.REVIEW,
                    issues=("已配對目前帳號，請確認",),
                    identity_resolution=IdentityResolution.MANUAL,
                )
            )

        checked_rows = await self._with_identity_conflicts(channel_id, remapped_rows)
        return replace(preview, rows=tuple(checked_rows))

    async def _users_by_ids(self, user_ids: list[str]) -> dict[str, dict]:
        users: dict[str, dict] = {}
        for batch in _chunks(user_ids):
            for user in await self.twitch_api.get_users_by_ids_strict(batch):
                if user.get("id"):
                    users[str(user["id"])] = user
        return users

    async def _users_by_logins(self, logins: list[str]) -> dict[str, dict]:
        users: dict[str, dict] = {}
        for batch in _chunks(logins):
            for user in await self.twitch_api.get_users_by_logins_strict(batch):
                if user.get("login"):
                    users[str(user["login"]).casefold()] = user
        return users

    async def _existing_user_ids(self, channel_id: str, user_ids: list[str]) -> set[str]:
        if not user_ids:
            return set()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id FROM viewer_checkins
                WHERE channel_id = $1 AND user_id = ANY($2::text[])
                UNION
                SELECT user_id FROM viewer_checkin_carryovers
                WHERE channel_id = $1 AND user_id = ANY($2::text[])
                """,
                channel_id,
                user_ids,
            )
        return {str(row["user_id"]) for row in rows}

    async def apply(
        self,
        *,
        channel_id: str,
        actor_user_id: str,
        preview: CheckinImportPreview,
        selected_keys: list[str],
        old_source_disabled: bool,
    ) -> CheckinImportResult:
        if not old_source_disabled:
            raise ValueError("old source must be disabled")
        selected_set = set(selected_keys)
        if not selected_set or len(selected_set) != len(selected_keys):
            raise ValueError("selected row keys must be unique and non-empty")
        selected = [row for row in preview.rows if row.key in selected_set]
        if len(selected) != len(selected_set) or any(
            row.status not in {ImportRowStatus.READY, ImportRowStatus.REVIEW}
            or not row.user_id
            or row.total_days is None
            or row.last_checkin_date is None
            for row in selected
        ):
            raise ValueError("only ready rows may be applied")

        idempotency_payload = {
            "content": preview.content_sha256,
            "column_mapping": preview.column_mapping,
            "keys": sorted(selected_set),
            "identities": sorted((row.key, row.user_id) for row in selected),
            "policy": "aggregate-block-existing-v2",
            "source": preview.source,
            "source_format": preview.source_format,
            "source_timezone": preview.source_timezone,
            "through_date": preview.through_date.isoformat(),
        }
        idempotency_key = hashlib.sha256(
            json.dumps(idempotency_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        user_ids = [str(row.user_id) for row in selected]

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"checkin-import:{channel_id}",
                )
                existing_batch = await conn.fetchrow(
                    """
                    SELECT id, imported_rows FROM checkin_import_batches
                    WHERE channel_id = $1 AND idempotency_key = $2
                    """,
                    channel_id,
                    idempotency_key,
                )
                if existing_batch is not None:
                    return CheckinImportResult(
                        batch_id=str(existing_batch["id"]),
                        imported_rows=int(existing_batch["imported_rows"]),
                        already_applied=True,
                    )

                conflicts = await conn.fetch(
                    """
                    SELECT user_id FROM viewer_checkins
                    WHERE channel_id = $1 AND user_id = ANY($2::text[])
                    UNION
                    SELECT user_id FROM viewer_checkin_carryovers
                    WHERE channel_id = $1 AND user_id = ANY($2::text[])
                    """,
                    channel_id,
                    user_ids,
                )
                if conflicts:
                    raise CheckinImportConflictError(context={"conflict_count": len(conflicts)})

                batch = await conn.fetchrow(
                    """
                    INSERT INTO checkin_import_batches
                        (channel_id, source, source_format, source_timezone, through_date,
                         content_sha256, idempotency_key, applied_by_user_id,
                         selected_rows, imported_rows)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::uuid, $9, $9)
                    RETURNING id
                    """,
                    channel_id,
                    preview.source,
                    preview.source_format,
                    preview.source_timezone,
                    preview.through_date,
                    preview.content_sha256,
                    idempotency_key,
                    actor_user_id,
                    len(selected),
                )
                if batch is None:
                    raise RuntimeError("failed to create check-in import batch")
                batch_id = str(batch["id"])
                await conn.executemany(
                    """
                    INSERT INTO viewer_checkin_carryovers
                        (channel_id, user_id, import_batch_id, source_username,
                         source_display_name, carried_total_days, last_source_date,
                         source_current_streak, source_daily_order)
                    VALUES ($1, $2, $3::uuid, $4, $5, $6, $7, $8, $9)
                    """,
                    [
                        (
                            channel_id,
                            row.user_id,
                            batch_id,
                            row.username,
                            row.display_name,
                            row.total_days,
                            row.last_checkin_date,
                            row.current_streak,
                            row.daily_order,
                        )
                        for row in selected
                    ],
                )
                await conn.executemany(
                    """
                    INSERT INTO viewer_daily_checkin_streaks
                        (channel_id, user_id, current_streak, last_checkin_date)
                    VALUES ($1, $2, $3, $4)
                    """,
                    [
                        (
                            channel_id,
                            row.user_id,
                            row.current_streak or 0,
                            row.last_checkin_date,
                        )
                        for row in selected
                    ],
                )

        return CheckinImportResult(batch_id=batch_id, imported_rows=len(selected))
