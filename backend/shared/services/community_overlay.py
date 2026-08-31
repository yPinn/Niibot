"""Community overlay delivery service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from shared.community_events import CHECKIN_RECORDED, validate_community_event
from shared.community_overlay_blocks import get_community_overlay_block
from shared.models.attendance import (
    CommunityOverlayAccess,
    CommunityOverlayFeed,
    CommunityOverlayThemePublished,
    CommunityOverlayThemeState,
)
from shared.repositories.community_overlay import CommunityOverlayRepository


class CommunityOverlayService:
    def __init__(self, repository: CommunityOverlayRepository) -> None:
        self.repository = repository

    async def get_or_create_channel(self, channel_id: str) -> CommunityOverlayAccess:
        return await self.repository.get_or_create_channel(channel_id)

    async def rotate_public_key(self, channel_id: str) -> CommunityOverlayAccess:
        return await self.repository.rotate_public_key(channel_id)

    async def set_enabled(self, channel_id: str, enabled: bool) -> CommunityOverlayAccess:
        return await self.repository.set_enabled(channel_id, enabled)

    async def get_theme_state(self, channel_id: str, block_type: str) -> CommunityOverlayThemeState:
        self._require_theme_block(block_type)
        return await self.repository.get_theme_state(channel_id, block_type)

    async def update_theme_draft(
        self,
        channel_id: str,
        block_type: str,
        theme: dict[str, object],
        expected_draft_version: int,
    ) -> CommunityOverlayThemeState:
        definition = get_community_overlay_block(block_type)
        return await self.repository.update_theme_draft(
            channel_id,
            block_type,
            definition.validate_theme(theme),
            expected_draft_version,
        )

    async def publish_theme(
        self, channel_id: str, block_type: str, expected_draft_version: int
    ) -> CommunityOverlayThemeState:
        self._require_theme_block(block_type)
        return await self.repository.publish_theme(channel_id, block_type, expected_draft_version)

    async def reset_theme_draft(
        self, channel_id: str, block_type: str, expected_draft_version: int
    ) -> CommunityOverlayThemeState:
        self._require_theme_block(block_type)
        return await self.repository.reset_theme_draft(
            channel_id, block_type, expected_draft_version
        )

    @staticmethod
    def _require_theme_block(block_type: str) -> None:
        get_community_overlay_block(block_type)

    async def get_public_theme(
        self, public_key: UUID, block_type: str
    ) -> CommunityOverlayThemePublished | None:
        self._require_theme_block(block_type)
        return await self.repository.get_public_theme(public_key, block_type)

    async def publish_preview(
        self,
        *,
        channel_id: str,
        actor_user_id: str,
        content_type: str,
        occurred_at: datetime | None = None,
    ) -> int:
        """Publish a registered synthetic event without touching feature state."""
        definition = get_community_overlay_block(content_type)
        now = occurred_at or datetime.now(UTC)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        payload = definition.build_preview_payload(now)
        validate_community_event(
            definition.preview_event_type,
            definition.preview_event_schema_version,
            payload,
        )
        await self.repository.get_or_create_channel(channel_id)
        return await self.repository.publish_event(
            channel_id=channel_id,
            event_type=definition.preview_event_type,
            schema_version=definition.preview_event_schema_version,
            source="system",
            actor_user_id=actor_user_id,
            actor_display_name=definition.preview_actor_display_name,
            payload=payload,
            occurred_at=now,
            expires_at=now + timedelta(minutes=10),
            idempotency_key=f"preview-{content_type}:{uuid4()}",
        )

    async def publish_checkin_preview(
        self,
        *,
        channel_id: str,
        actor_user_id: str,
        actor_display_name: str,
        total_days: int,
        occurred_at: datetime | None = None,
    ) -> int:
        if not 1 <= total_days <= 9999:
            raise ValueError("Preview count must be between 1 and 9999")
        now = occurred_at or datetime.now(UTC)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")

        payload = {
            "total_days": total_days,
            "checkin_date": now.date().isoformat(),
            "preview": True,
        }
        validate_community_event(
            CHECKIN_RECORDED.event_type,
            CHECKIN_RECORDED.schema_version,
            payload,
        )
        await self.repository.get_or_create_channel(channel_id)
        return await self.repository.publish_event(
            channel_id=channel_id,
            event_type=CHECKIN_RECORDED.event_type,
            schema_version=CHECKIN_RECORDED.schema_version,
            source="system",
            actor_user_id=actor_user_id,
            actor_display_name=actor_display_name,
            payload=payload,
            occurred_at=now,
            expires_at=now + timedelta(minutes=10),
            idempotency_key=f"preview-checkin:{uuid4()}",
        )

    async def get_feed(
        self,
        public_key: UUID,
        *,
        after_id: int | None,
        limit: int,
    ) -> CommunityOverlayFeed | None:
        return await self.repository.get_feed(
            public_key,
            after_id=after_id,
            limit=limit,
            now=datetime.now(UTC),
        )
