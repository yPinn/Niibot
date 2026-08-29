"""Unit tests for api.services.event_config_service — options projection and
count_source-driven trigger counts."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.event_config_service import EventConfigService
from shared.models.event_config import EventConfig

CHANNEL_ID = "ch-1"


def _make_svc() -> tuple[EventConfigService, MagicMock]:
    repo = MagicMock()
    with patch("services.event_config_service.EventConfigRepository", return_value=repo):
        svc = EventConfigService(MagicMock())
    return svc, repo


def _cfg(event_type: str, options: dict | None = None) -> EventConfig:
    return EventConfig(
        id=1,
        channel_id=CHANNEL_ID,
        event_type=event_type,  # type: ignore[arg-type]
        message_template="hi",
        enabled=True,
        options=options or {},
    )


pytestmark = pytest.mark.asyncio


class TestTriggerCount:
    async def test_bits_count_reads_the_cheer_bucket(self):
        svc, repo = _make_svc()
        repo.ensure_defaults = AsyncMock(return_value=[_cfg("bits")])
        repo.get_stream_event_counts = AsyncMock(return_value={"cheer": 7})

        (row,) = await svc.list_configs_with_counts(CHANNEL_ID)

        assert row["trigger_count"] == 7

    async def test_resub_and_gift_sub_have_no_count(self):
        svc, repo = _make_svc()
        repo.ensure_defaults = AsyncMock(return_value=[_cfg("resub"), _cfg("gift_sub")])
        repo.get_stream_event_counts = AsyncMock(return_value={"subscribe": 3})

        rows = await svc.list_configs_with_counts(CHANNEL_ID)

        assert all(r["trigger_count"] is None for r in rows)

    async def test_follow_count_is_zero_when_bucket_empty(self):
        svc, repo = _make_svc()
        repo.ensure_defaults = AsyncMock(return_value=[_cfg("follow")])
        repo.get_stream_event_counts = AsyncMock(return_value={})

        (row,) = await svc.list_configs_with_counts(CHANNEL_ID)

        assert row["trigger_count"] == 0


class TestOptionsProjection:
    async def test_unknown_option_key_is_dropped_on_write(self):
        svc, repo = _make_svc()
        repo.upsert_config = AsyncMock(return_value=_cfg("raid", {"auto_shoutout": True}))
        repo.get_stream_event_counts = AsyncMock(return_value={})

        await svc.update_config(
            CHANNEL_ID, "raid", "hi", True, options={"auto_shoutout": True, "evil": {"x": 1}}
        )

        _, _, _, _, stored = repo.upsert_config.await_args.args
        assert stored == {"auto_shoutout": True}

    async def test_missing_option_falls_back_to_schema_default(self):
        svc, repo = _make_svc()
        repo.upsert_config = AsyncMock(return_value=_cfg("raid", {"auto_shoutout": True}))
        repo.get_stream_event_counts = AsyncMock(return_value={})

        await svc.update_config(CHANNEL_ID, "raid", "hi", True, options={})

        _, _, _, _, stored = repo.upsert_config.await_args.args
        assert stored == {"auto_shoutout": True}

    async def test_event_without_schema_stores_empty_options(self):
        svc, repo = _make_svc()
        repo.upsert_config = AsyncMock(return_value=_cfg("follow"))
        repo.get_stream_event_counts = AsyncMock(return_value={})

        await svc.update_config(CHANNEL_ID, "follow", "hi", True, options={"anything": 1})

        _, _, _, _, stored = repo.upsert_config.await_args.args
        assert stored == {}

    async def test_stale_tiers_option_is_projected_away_on_read(self):
        svc, repo = _make_svc()
        repo.ensure_defaults = AsyncMock(return_value=[_cfg("bits", {"tiers": []})])
        repo.get_stream_event_counts = AsyncMock(return_value={})

        (row,) = await svc.list_configs_with_counts(CHANNEL_ID)

        assert row["options"] == {}

    async def test_toggle_reprojects_stored_options(self):
        svc, repo = _make_svc()
        repo.get_config = AsyncMock(return_value=_cfg("raid", {"auto_shoutout": False, "junk": 9}))
        repo.upsert_config = AsyncMock(return_value=_cfg("raid", {"auto_shoutout": False}))
        repo.get_stream_event_counts = AsyncMock(return_value={})

        await svc.toggle_config(CHANNEL_ID, "raid", False)

        _, _, _, _, stored = repo.upsert_config.await_args.args
        assert stored == {"auto_shoutout": False}
