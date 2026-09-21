"""Single admission pipeline for every Video Queue submission source.

Platform parsing/metadata is injected so the Twitch bot can reuse its aiohttp
session while API/webhook callers use the same policy and persistence gates.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from shared.models.video_queue import (
    VideoQueueBlocklistEntry,
    VideoQueueEntry,
    VideoQueueSettings,
)
from shared.repositories.video_queue import (
    SOURCE_PRIORITY,
    VideoQueueBlocklistRepository,
    VideoQueueRepository,
    VideoQueueSettingsRepository,
)
from shared.video_sources import (
    ResolvedVideo,
    VideoMetadata,
    metadata_gate_unverifiable,
)

AdmissionSource = Literal["chat", "redemption", "donation", "dashboard"]
ResolveVideo = Callable[[str], Awaitable[ResolvedVideo | None]]
FetchMetadata = Callable[[ResolvedVideo], Awaitable[VideoMetadata]]
ResolveRequester = Callable[[], Awaitable[str]]

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdmissionPolicy:
    enforce_queue_size: bool
    enforce_user_limits: bool
    enforce_min_views: bool
    enforce_replay_cooldown: bool
    require_redemption_enabled: bool = False
    source_duration_field: str | None = None
    atomic_limited_insert: bool = True
    resolve_before_settings: bool = False


ADMISSION_POLICIES: dict[AdmissionSource, AdmissionPolicy] = {
    "chat": AdmissionPolicy(True, True, True, True),
    "redemption": AdmissionPolicy(
        True,
        True,
        True,
        True,
        require_redemption_enabled=True,
        source_duration_field="max_duration_redemption",
    ),
    # Paid media share still obeys channel-wide safety/quality/capacity rules,
    # but has no stable viewer identity for per-user limits.
    "donation": AdmissionPolicy(True, False, True, True),
    # Broadcaster/mod manual adds intentionally bypass audience fairness gates.
    "dashboard": AdmissionPolicy(
        False,
        False,
        False,
        False,
        atomic_limited_insert=False,
        resolve_before_settings=True,
    ),
}


class AdmissionReason(StrEnum):
    DISABLED = "disabled"
    SOURCE_DISABLED = "source_disabled"
    INVALID_URL = "invalid_url"
    DUPLICATE = "duplicate"
    QUEUE_FULL = "queue_full"
    USER_LIMIT = "user_limit"
    USER_COOLDOWN = "user_cooldown"
    NOT_PLAYABLE = "not_playable"
    METADATA_UNVERIFIABLE = "metadata_unverifiable"
    MIN_VIEWS = "min_views"
    TOO_LONG = "too_long"
    REPLAY_COOLDOWN = "replay_cooldown"
    BLOCKED = "blocked"
    QUEUE_CHANGED = "queue_changed"


class AdmissionRejected(Exception):  # noqa: N818 - domain outcome, not an internal error
    def __init__(
        self,
        reason: AdmissionReason,
        *,
        details: dict[str, int | str] | None = None,
        blocked: VideoQueueBlocklistEntry | None = None,
    ) -> None:
        self.reason = reason
        self.details = details or {}
        self.blocked = blocked
        super().__init__(reason.value)


@dataclass(frozen=True)
class AdmissionResult:
    entry: VideoQueueEntry
    settings: VideoQueueSettings
    resolved: ResolvedVideo
    metadata: VideoMetadata
    position: int


class VideoQueueAdmissionService:
    def __init__(
        self,
        queue: VideoQueueRepository,
        settings: VideoQueueSettingsRepository,
        blocklist: VideoQueueBlocklistRepository,
    ) -> None:
        self.queue = queue
        self.settings = settings
        self.blocklist = blocklist

    async def admit(
        self,
        *,
        channel_id: str,
        url: str,
        requested_by: str | ResolveRequester,
        source: AdmissionSource,
        resolve: ResolveVideo,
        fetch_metadata: FetchMetadata,
        requested_by_id: str | None = None,
    ) -> AdmissionResult:
        """Run admission and emit one structured outcome without logging raw URLs."""
        try:
            result = await self._admit(
                channel_id=channel_id,
                url=url,
                requested_by=requested_by,
                source=source,
                resolve=resolve,
                fetch_metadata=fetch_metadata,
                requested_by_id=requested_by_id,
            )
        except AdmissionRejected as error:
            LOGGER.info(
                "video_queue_admission_rejected",
                extra={
                    "channel_id": channel_id,
                    "source": source,
                    "reason": error.reason.value,
                },
            )
            raise
        LOGGER.info(
            "video_queue_admission_accepted",
            extra={
                "channel_id": channel_id,
                "source": source,
                "video_type": result.resolved.video_type,
                "entry_id": result.entry.id,
            },
        )
        return result

    async def _admit(
        self,
        *,
        channel_id: str,
        url: str,
        requested_by: str | ResolveRequester,
        source: AdmissionSource,
        resolve: ResolveVideo,
        fetch_metadata: FetchMetadata,
        requested_by_id: str | None = None,
    ) -> AdmissionResult:
        policy = ADMISSION_POLICIES[source]
        requester_name: str | None = requested_by if isinstance(requested_by, str) else None
        requester_resolver: ResolveRequester | None = (
            requested_by if not isinstance(requested_by, str) else None
        )

        async def get_requester_name() -> str:
            nonlocal requester_name
            if requester_name is None:
                assert requester_resolver is not None
                requester_name = await requester_resolver()
            return requester_name

        resolved = await resolve(url) if policy.resolve_before_settings else None
        if policy.resolve_before_settings and resolved is None:
            raise AdmissionRejected(AdmissionReason.INVALID_URL)
        settings = await self.settings.get_or_create(channel_id)
        if not settings.enabled:
            raise AdmissionRejected(AdmissionReason.DISABLED)
        if policy.require_redemption_enabled and not settings.redemption_enabled:
            raise AdmissionRejected(AdmissionReason.SOURCE_DISABLED)
        if resolved is None:
            resolved = await resolve(url)
        if resolved is None:
            raise AdmissionRejected(AdmissionReason.INVALID_URL)
        if await self.queue.video_is_active(channel_id, resolved.video_id, resolved.video_type):
            raise AdmissionRejected(AdmissionReason.DUPLICATE)

        if policy.enforce_queue_size:
            queue_size = await self.queue.get_queue_size(channel_id)
            if queue_size >= settings.max_queue_size:
                raise AdmissionRejected(
                    AdmissionReason.QUEUE_FULL,
                    details={"queue_size": queue_size, "max_queue_size": settings.max_queue_size},
                )

        if policy.enforce_user_limits:
            requester = await get_requester_name()
            if settings.max_per_user > 0:
                active = await self.queue.count_active_by_user(
                    channel_id, requester, requested_by_id
                )
                if active >= settings.max_per_user:
                    raise AdmissionRejected(
                        AdmissionReason.USER_LIMIT,
                        details={"max_per_user": settings.max_per_user},
                    )
            if settings.user_cooldown_seconds > 0:
                last = await self.queue.find_last_entry_by_user(
                    channel_id, requester, requested_by_id
                )
                if last and last.created_at:
                    elapsed = (datetime.now(UTC) - last.created_at).total_seconds()
                    if elapsed < settings.user_cooldown_seconds:
                        raise AdmissionRejected(
                            AdmissionReason.USER_COOLDOWN,
                            details={
                                "remaining_seconds": max(
                                    0, int(settings.user_cooldown_seconds - elapsed)
                                )
                            },
                        )

        metadata = await fetch_metadata(resolved)
        if not metadata.playable:
            raise AdmissionRejected(
                AdmissionReason.NOT_PLAYABLE,
                details={"unplayable_reason": metadata.unplayable_reason or ""},
            )

        if policy.enforce_min_views and settings.min_view_count > 0:
            if metadata_gate_unverifiable(
                metadata.view_count, best_effort=metadata.metadata_best_effort
            ):
                raise AdmissionRejected(
                    AdmissionReason.METADATA_UNVERIFIABLE,
                    details={"field": "view_count"},
                )
            if metadata.view_count is not None and metadata.view_count < settings.min_view_count:
                raise AdmissionRejected(
                    AdmissionReason.MIN_VIEWS,
                    details={
                        "view_count": metadata.view_count,
                        "min_view_count": settings.min_view_count,
                    },
                )

        duration_limits = [settings.max_duration_seconds]
        if policy.source_duration_field:
            duration_limits.append(int(getattr(settings, policy.source_duration_field)))
        duration_limit = (
            min(limit for limit in duration_limits if limit > 0)
            if any(limit > 0 for limit in duration_limits)
            else 0
        )
        if duration_limit > 0:
            if metadata_gate_unverifiable(
                metadata.duration_seconds, best_effort=metadata.metadata_best_effort
            ):
                raise AdmissionRejected(
                    AdmissionReason.METADATA_UNVERIFIABLE,
                    details={"field": "duration_seconds"},
                )
            if metadata.duration_seconds is not None and metadata.duration_seconds > duration_limit:
                raise AdmissionRejected(
                    AdmissionReason.TOO_LONG,
                    details={
                        "duration_seconds": metadata.duration_seconds,
                        "limit_seconds": duration_limit,
                    },
                )

        if policy.enforce_replay_cooldown and settings.replay_cooldown_hours:
            if await self.queue.played_within(
                channel_id,
                resolved.video_id,
                settings.replay_cooldown_hours,
                resolved.video_type,
            ):
                raise AdmissionRejected(
                    AdmissionReason.REPLAY_COOLDOWN,
                    details={"hours": settings.replay_cooldown_hours},
                )

        blocklist_requester = await get_requester_name() if policy.enforce_user_limits else None
        blocked = await self.blocklist.check(
            channel_id,
            video_type=resolved.video_type,
            video_id=resolved.video_id,
            title=metadata.title,
            requested_by=blocklist_requester,
            requested_by_id=requested_by_id if policy.enforce_user_limits else None,
            creator_id=metadata.creator_id,
        )
        if blocked is not None:
            raise AdmissionRejected(AdmissionReason.BLOCKED, blocked=blocked)

        requester = await get_requester_name()
        if policy.atomic_limited_insert:
            entry = await self.queue.add_if_within_limits(
                channel_id=channel_id,
                video_id=resolved.video_id,
                requested_by=requester,
                source=source,
                max_queue_size=settings.max_queue_size,
                max_per_user=settings.max_per_user if policy.enforce_user_limits else 0,
                requested_by_id=requested_by_id,
                title=metadata.title,
                duration_seconds=metadata.duration_seconds,
                is_vertical=metadata.is_vertical,
                thumbnail_url=metadata.thumbnail_url,
                video_type=resolved.video_type,
                priority=SOURCE_PRIORITY[source],
                start_seconds=resolved.start_seconds,
                creator_id=metadata.creator_id,
                creator_name=metadata.creator_name,
            )
            if entry is None:
                raise AdmissionRejected(AdmissionReason.QUEUE_CHANGED)
        else:
            entry = await self.queue.add(
                channel_id=channel_id,
                video_id=resolved.video_id,
                requested_by=requester,
                source=source,
                requested_by_id=requested_by_id,
                title=metadata.title,
                duration_seconds=metadata.duration_seconds,
                is_vertical=metadata.is_vertical,
                thumbnail_url=metadata.thumbnail_url,
                video_type=resolved.video_type,
                priority=SOURCE_PRIORITY[source],
                start_seconds=resolved.start_seconds,
                creator_id=metadata.creator_id,
                creator_name=metadata.creator_name,
            )

        position = (
            await self.queue.get_queue_size(channel_id) if policy.atomic_limited_insert else -1
        )
        return AdmissionResult(entry, settings, resolved, metadata, position)
