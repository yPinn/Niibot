"""Identity resolution, preview caching, and atomic check-in carry-over apply."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
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
    ImportPreviewRow,
    ImportRowStatus,
)

_SOURCE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
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
                row.username.casefold()
                for row in valid_rows
                if not row.platform_user_id and row.username
            )
        )
        try:
            users_by_id = await self._users_by_ids(ids)
            users_by_login = await self._users_by_logins(logins)
        except TwitchUsersLookupError as exc:
            raise CheckinIdentityLookupError() from exc

        resolved: list[tuple[SummaryRow, dict | None, list[str]]] = []
        for row in valid_rows:
            issues: list[str] = []
            if row.platform_user_id:
                user = users_by_id.get(row.platform_user_id)
                if (
                    user
                    and row.username
                    and str(user.get("login", "")).casefold() != row.username.casefold()
                ):
                    issues.append("Twitch User ID 與 Username 不一致")
            else:
                user = users_by_login.get((row.username or "").casefold())
            if user is None:
                issues.append("找不到可確認的 Twitch 帳號")
            resolved.append((row, user, issues))

        resolved_ids = [str(user["id"]) for _, user, _ in resolved if user and user.get("id")]
        conflicts = await self._existing_user_ids(channel_id, resolved_ids)
        duplicate_ids = {user_id for user_id in resolved_ids if resolved_ids.count(user_id) > 1}

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
        for row, user, issues in resolved:
            user_id = str(user["id"]) if user and user.get("id") else None
            if user_id in duplicate_ids:
                issues.append("多列資料解析到同一個 Twitch 帳號")
            if user_id in conflicts:
                issues.append("這位觀眾已有 Niibot 簽到或轉移資料")
            if user is None:
                status = ImportRowStatus.UNRESOLVED
            elif issues:
                status = ImportRowStatus.CONFLICT
            else:
                status = ImportRowStatus.READY
            preview_rows.append(
                ImportPreviewRow(
                    key=_row_key(row, user_id),
                    source_row=row.source_row,
                    user_id=user_id,
                    username=(
                        str(user.get("login")) if user and user.get("login") else row.username
                    ),
                    display_name=(
                        str(user.get("display_name"))
                        if user and user.get("display_name")
                        else row.display_name
                    ),
                    total_days=row.total_days,
                    last_checkin_date=row.last_checkin_date,
                    current_streak=row.current_streak,
                    daily_order=row.daily_order,
                    status=status,
                    issues=tuple(issues),
                )
            )
        preview_rows.sort(key=lambda row: row.source_row)

        return CheckinImportPreview(
            source=source,
            source_format=parsed.format,
            source_timezone=source_timezone,
            through_date=through_date,
            content_sha256=parsed.content_sha256,
            sheet_name=parsed.sheet_name,
            rows=tuple(preview_rows),
        )

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
            row.status is not ImportRowStatus.READY
            or not row.user_id
            or row.total_days is None
            or row.last_checkin_date is None
            for row in selected
        ):
            raise ValueError("only ready rows may be applied")

        idempotency_payload = {
            "content": preview.content_sha256,
            "keys": sorted(selected_set),
            "policy": "aggregate-block-existing-v1",
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
