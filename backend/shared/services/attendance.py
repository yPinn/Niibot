"""Daily check-in domain orchestration shared by chat adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.checkin_templates import render_checkin_template, validate_checkin_template
from shared.models.attendance import (
    CheckinLeaderboardEntry,
    CheckinRank,
    CheckinReply,
    CheckinResult,
    CheckinSettings,
    CheckinStatus,
)
from shared.repositories.attendance import AttendanceRepository


class AttendanceService:
    def __init__(self, repository: AttendanceRepository) -> None:
        self.repository = repository

    async def get_settings(self, channel_id: str) -> CheckinSettings:
        return await self.repository.get_or_create_settings(channel_id)

    async def get_leaderboard(self, channel_id: str) -> tuple[CheckinLeaderboardEntry, ...]:
        return await self.repository.list_leaderboard(channel_id)

    async def get_rank(self, channel_id: str, user_id: str) -> CheckinRank | None:
        return await self.repository.get_checkin_rank(channel_id, user_id)

    async def update_settings(
        self,
        channel_id: str,
        *,
        timezone: str | None = None,
        success_template: str | None = None,
        duplicate_template: str | None = None,
        reply_delay_seconds: int | None = None,
    ) -> CheckinSettings:
        current = await self.repository.get_or_create_settings(channel_id)
        next_timezone = timezone if timezone is not None else current.timezone
        next_success = (
            success_template if success_template is not None else current.success_template
        )
        next_duplicate = (
            duplicate_template if duplicate_template is not None else current.duplicate_template
        )
        next_delay = (
            reply_delay_seconds if reply_delay_seconds is not None else current.reply_delay_seconds
        )

        self._validate_settings(next_timezone, next_success, next_duplicate)
        return await self.repository.update_settings(
            channel_id=channel_id,
            timezone=next_timezone,
            success_template=next_success,
            duplicate_template=next_duplicate,
            reply_delay_seconds=next_delay,
        )

    @staticmethod
    def _validate_settings(
        timezone: str,
        success_template: str,
        duplicate_template: str,
    ) -> ZoneInfo:
        try:
            resolved_timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid check-in timezone: {timezone}") from exc
        validate_checkin_template(success_template)
        validate_checkin_template(duplicate_template)
        return resolved_timezone

    async def check_in(
        self,
        *,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        occurred_at: datetime | None = None,
        session_id: int | None = None,
    ) -> CheckinResult:
        _, result = await self._perform_check_in(
            channel_id=channel_id,
            user_id=user_id,
            username=username,
            display_name=display_name,
            occurred_at=occurred_at,
            session_id=session_id,
        )
        return result

    async def check_in_with_reply(
        self,
        *,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        occurred_at: datetime | None = None,
        session_id: int | None = None,
    ) -> CheckinReply:
        settings, result = await self._perform_check_in(
            channel_id=channel_id,
            user_id=user_id,
            username=username,
            display_name=display_name,
            occurred_at=occurred_at,
            session_id=session_id,
        )
        template = (
            settings.success_template
            if result.status is CheckinStatus.RECORDED
            else settings.duplicate_template
        )
        message = render_checkin_template(
            template,
            username=result.username,
            display_name=result.display_name,
            total_days=result.total_days,
            checkin_date=result.checkin_date,
        )
        return CheckinReply(
            result=result, message=message, delay_seconds=settings.reply_delay_seconds
        )

    async def _perform_check_in(
        self,
        *,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        occurred_at: datetime | None,
        session_id: int | None,
    ) -> tuple[CheckinSettings, CheckinResult]:
        now = occurred_at or datetime.now(UTC)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")

        settings = await self.repository.get_or_create_settings(channel_id)
        # Validate presentation config before the repository opens its write
        # transaction, so a broken template can never commit a check-in/event
        # that the chat adapter then reports as failed.
        timezone = self._validate_settings(
            settings.timezone,
            settings.success_template,
            settings.duplicate_template,
        )

        result = await self.repository.record_checkin(
            channel_id=channel_id,
            user_id=user_id,
            username=username,
            display_name=display_name,
            checkin_date=now.astimezone(timezone).date(),
            occurred_at=now,
            session_id=session_id,
        )
        return settings, result
