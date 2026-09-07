"""Tests for durable community overlay cursor delivery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from shared.community_overlay_themes import (
    DEFAULT_OVERLAY_THEME,
    CommunityOverlayThemeVersionConflictError,
)
from shared.repositories.community_overlay import CommunityOverlayRepository

_KEY = UUID("11111111-1111-4111-8111-111111111111")
_NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)


def _pool() -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    transaction = MagicMock()
    transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = transaction
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _access(latest_id: int = 12) -> dict:
    return {
        "channel_id": "ch1",
        "public_key": _KEY,
        "enabled": True,
        "latest_id": latest_id,
        "created_at": _NOW,
        "updated_at": _NOW,
    }


def _event(event_id: int) -> dict:
    return {
        "id": event_id,
        "channel_id": "ch1",
        "event_type": "checkin.recorded",
        "schema_version": 1,
        "source": "twitch",
        "actor_user_id": "u1",
        "actor_display_name": "Alice",
        "payload": {"total_days": 3, "checkin_date": "2026-08-30"},
        "occurred_at": _NOW,
        "expires_at": _NOW + timedelta(minutes=10),
    }


def _theme_state(
    *,
    draft: dict[str, object] | None = None,
    published: dict[str, object] | None = None,
    revision_id: int | None = 41,
    draft_version: int = 1,
) -> dict:
    return {
        "channel_id": "ch1",
        "block_type": "checkin",
        "renderer": "checkin-card",
        "schema_version": 1,
        "draft_theme": draft or DEFAULT_OVERLAY_THEME,
        "draft_version": draft_version,
        "published_revision_id": revision_id,
        "published_renderer": "checkin-card" if revision_id is not None else None,
        "published_schema_version": 1 if revision_id is not None else None,
        "published_theme": published
        or (DEFAULT_OVERLAY_THEME if revision_id is not None else None),
        "published_created_at": _NOW if revision_id is not None else None,
        "updated_at": _NOW,
    }


@pytest.mark.asyncio
class TestCommunityOverlayFeed:
    async def test_initial_handshake_returns_latest_cursor_without_replay(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = _access(latest_id=12)
        repo = CommunityOverlayRepository(pool)

        feed = await repo.get_feed(_KEY, after_id=None, limit=50, now=_NOW)

        assert feed is not None
        assert feed.cursor == 12
        assert feed.events == ()
        conn.fetch.assert_not_awaited()

    async def test_incremental_feed_is_ordered_scoped_and_expiry_filtered(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = _access(latest_id=15)
        conn.fetch.return_value = [_event(13), _event(14)]
        repo = CommunityOverlayRepository(pool)

        feed = await repo.get_feed(_KEY, after_id=12, limit=50, now=_NOW)

        assert feed is not None
        assert feed.cursor == 14
        assert [event.id for event in feed.events] == [13, 14]
        sql = conn.fetch.await_args.args[0]
        assert "channel_id = $1" in sql
        assert "id > $2" in sql
        assert "expires_at IS NULL OR expires_at > $3" in sql
        assert "ORDER BY id ASC" in sql
        assert "LIMIT $4" in sql

    async def test_empty_incremental_page_advances_over_expired_events(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = _access(latest_id=20)
        conn.fetch.return_value = []
        repo = CommunityOverlayRepository(pool)

        feed = await repo.get_feed(_KEY, after_id=12, limit=50, now=_NOW)

        assert feed is not None
        assert feed.cursor == 20

    async def test_unknown_or_disabled_key_is_not_exposed(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = None
        repo = CommunityOverlayRepository(pool)

        assert await repo.get_feed(_KEY, after_id=0, limit=50, now=_NOW) is None
        conn.fetch.assert_not_awaited()

    async def test_rejects_out_of_range_limit(self):
        pool, _ = _pool()
        repo = CommunityOverlayRepository(pool)

        with pytest.raises(ValueError, match="between 1 and 100"):
            await repo.get_feed(_KEY, after_id=0, limit=101, now=_NOW)

    async def test_rejects_negative_cursor(self):
        pool, _ = _pool()
        repo = CommunityOverlayRepository(pool)

        with pytest.raises(ValueError, match="non-negative"):
            await repo.get_feed(_KEY, after_id=-1, limit=50, now=_NOW)


@pytest.mark.asyncio
class TestCommunityOverlayAccess:
    async def test_resolves_only_an_enabled_public_capability(self):
        pool, conn = _pool()
        conn.fetchval.return_value = "ch1"
        repo = CommunityOverlayRepository(pool)

        assert await repo.resolve_public_channel(_KEY) == "ch1"
        sql = conn.fetchval.await_args.args[0]
        assert "public_key = $1" in sql
        assert "enabled = TRUE" in sql

    async def test_get_or_create_is_channel_scoped(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = _access()
        repo = CommunityOverlayRepository(pool)

        access = await repo.get_or_create_channel("ch1")

        assert access.channel_id == "ch1"
        assert access.public_key == _KEY
        assert "ON CONFLICT" in conn.execute.await_args.args[0]
        assert conn.fetchrow.await_args.args[1] == "ch1"

    async def test_rotate_key_uses_database_uuid_and_channel_filter(self):
        pool, conn = _pool()
        rotated = {**_access(), "public_key": UUID("22222222-2222-4222-8222-222222222222")}
        conn.fetchrow.return_value = rotated
        repo = CommunityOverlayRepository(pool)

        access = await repo.rotate_public_key("ch1")

        assert access.public_key == rotated["public_key"]
        sql = conn.fetchrow.await_args.args[0]
        assert "public_key = gen_random_uuid()" in sql
        assert "WHERE channel_id = $1" in sql

    async def test_set_enabled_updates_only_requested_channel(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = {**_access(), "enabled": False}
        repo = CommunityOverlayRepository(pool)

        access = await repo.set_enabled("ch1", False)

        assert access.enabled is False
        sql = conn.fetchrow.await_args.args[0]
        assert "WHERE channel_id = $1" in sql
        assert conn.fetchrow.await_args.args[1:] == ("ch1", False)


@pytest.mark.asyncio
class TestCommunityOverlayThemes:
    async def test_get_theme_state_creates_initial_immutable_revision(self):
        pool, conn = _pool()
        conn.fetchrow.side_effect = [
            _theme_state(revision_id=None),
            _theme_state(),
        ]
        conn.fetchval.return_value = 41
        repo = CommunityOverlayRepository(pool)

        state = await repo.get_theme_state("ch1", "checkin")

        assert state.channel_id == "ch1"
        assert state.block_type == "checkin"
        assert state.published.revision_id == 41
        assert state.has_unpublished_changes is False
        assert "community_overlay_profiles" in conn.execute.await_args_list[0].args[0]
        assert "community_overlay_revisions" in conn.fetchval.await_args.args[0]
        assert conn.fetchval.await_args.args[1] == "ch1"
        pointer_sql = conn.execute.await_args_list[-1].args[0]
        assert "published_revision_id = $3" in pointer_sql
        assert "WHERE channel_id = $1" in pointer_sql
        assert "block_type = $2" in pointer_sql

    async def test_update_draft_is_scoped_to_requested_channel(self):
        pool, conn = _pool()
        next_theme = {**DEFAULT_OVERLAY_THEME, "placement": "top-left"}
        conn.fetchrow.side_effect = [
            _theme_state(),
            _theme_state(draft=next_theme, draft_version=2),
        ]
        repo = CommunityOverlayRepository(pool)

        state = await repo.update_theme_draft("ch1", "checkin", next_theme, 1)

        assert state.draft_theme == next_theme
        assert state.draft_version == 2
        sql, channel_id, block_type, theme = conn.fetchrow.await_args.args
        assert "UPDATE community_overlay_profiles" in sql
        assert "WHERE channel_id = $1" in sql
        assert "block_type = $2" in sql
        assert channel_id == "ch1"
        assert block_type == "checkin"
        assert theme == next_theme

    async def test_publish_inserts_snapshot_and_switches_pointer_in_one_transaction(self):
        pool, conn = _pool()
        draft = {**DEFAULT_OVERLAY_THEME, "placement": "top-left"}
        conn.fetchrow.side_effect = [
            _theme_state(draft=draft),
            _theme_state(draft=draft, published=draft, revision_id=42),
        ]
        conn.fetchval.return_value = 42
        repo = CommunityOverlayRepository(pool)

        state = await repo.publish_theme("ch1", "checkin", 1)

        assert state.published.revision_id == 42
        assert state.published.theme == draft
        assert state.has_unpublished_changes is False
        insert_sql = conn.fetchval.await_args.args[0]
        assert "INSERT INTO community_overlay_revisions" in insert_sql
        assert conn.fetchval.await_args.args[1:4] == ("ch1", "checkin", draft)
        assert "WHERE channel_id = $1" in conn.execute.await_args_list[-1].args[0]

    async def test_publish_without_changes_reuses_current_revision(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = _theme_state()
        repo = CommunityOverlayRepository(pool)

        state = await repo.publish_theme("ch1", "checkin", 1)

        assert state.published.revision_id == 41
        conn.fetchval.assert_not_awaited()

    async def test_reset_draft_copies_only_its_published_snapshot(self):
        pool, conn = _pool()
        draft = {**DEFAULT_OVERLAY_THEME, "radius_px": 8}
        conn.fetchrow.side_effect = [
            _theme_state(draft=draft),
            _theme_state(draft_version=2),
        ]
        repo = CommunityOverlayRepository(pool)

        state = await repo.reset_theme_draft("ch1", "checkin", 1)

        assert state.has_unpublished_changes is False
        assert state.draft_version == 2
        sql, channel_id, block_type = conn.fetchrow.await_args.args
        assert "published_revision_id" in sql
        assert "revision.channel_id = profile.channel_id" in sql
        assert "WHERE profile.channel_id = $1" in sql
        assert channel_id == "ch1"
        assert block_type == "checkin"

    async def test_stale_draft_version_cannot_overwrite_newer_state(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = _theme_state(draft_version=3)
        repo = CommunityOverlayRepository(pool)

        with pytest.raises(CommunityOverlayThemeVersionConflictError):
            await repo.update_theme_draft("ch1", "checkin", dict(DEFAULT_OVERLAY_THEME), 2)

        assert conn.fetchrow.await_count == 1

    async def test_public_theme_requires_enabled_capability_and_never_reads_draft(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = {
            "revision_id": 41,
            "renderer": "checkin-card",
            "schema_version": 1,
            "theme": DEFAULT_OVERLAY_THEME,
            "created_at": _NOW,
        }
        repo = CommunityOverlayRepository(pool)

        published = await repo.get_public_theme(_KEY, "checkin")

        assert published is not None
        assert published.theme == DEFAULT_OVERLAY_THEME
        sql = conn.fetchrow.await_args.args[0]
        assert "access.public_key = $1" in sql
        assert "access.enabled = TRUE" in sql
        assert conn.fetchrow.await_args.args[5] == "checkin"
        assert "draft_theme" not in sql

    async def test_unknown_public_key_returns_none(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = None
        repo = CommunityOverlayRepository(pool)

        assert await repo.get_public_theme(_KEY, "checkin") is None


@pytest.mark.asyncio
class TestCommunityOverlayPublishing:
    async def test_publish_event_is_channel_scoped_and_returns_cursor_id(self):
        pool, conn = _pool()
        conn.fetchval.return_value = 91
        repo = CommunityOverlayRepository(pool)

        event_id = await repo.publish_event(
            channel_id="ch1",
            event_type="checkin.recorded",
            schema_version=1,
            source="system",
            actor_user_id="owner1",
            actor_display_name="Streamer",
            payload={"total_days": 8, "checkin_date": "2026-08-31", "preview": True},
            occurred_at=_NOW,
            expires_at=_NOW + timedelta(minutes=10),
            idempotency_key="dev-checkin:abc",
        )

        assert event_id == 91
        sql = conn.fetchval.await_args.args[0]
        assert "INSERT INTO community_overlay_events" in sql
        assert "RETURNING id" in sql
        assert conn.fetchval.await_args.args[1] == "ch1"

    async def test_publish_failure_is_not_reported_as_success(self):
        pool, conn = _pool()
        conn.fetchval.return_value = None
        repo = CommunityOverlayRepository(pool)

        with pytest.raises(RuntimeError, match="Failed to publish"):
            await repo.publish_event(
                channel_id="ch1",
                event_type="checkin.recorded",
                schema_version=1,
                source="system",
                actor_user_id="owner1",
                actor_display_name="Streamer",
                payload={"total_days": 8, "checkin_date": "2026-08-31"},
                occurred_at=_NOW,
                expires_at=_NOW + timedelta(minutes=10),
                idempotency_key="dev-checkin:failed",
            )


@pytest.mark.asyncio
class TestCommunityOverlayRetention:
    async def test_prune_expired_uses_explicit_cutoff(self):
        pool, conn = _pool()
        conn.execute.return_value = "DELETE 3"
        repo = CommunityOverlayRepository(pool)

        removed = await repo.prune_expired(_NOW)

        assert removed == 3
        sql, cutoff = conn.execute.await_args.args
        assert "expires_at <= $1" in sql
        assert cutoff == _NOW
