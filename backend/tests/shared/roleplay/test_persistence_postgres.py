"""PostgreSQL integration contracts for Canon Role-play persistence."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from uuid import uuid4

import asyncpg
import pytest
from tests.shared.roleplay.factories import sample_roleplay_package

from shared.repositories.roleplay import (
    RoleplayRepository,
    RoleplayRevisionOwnershipError,
    RoleplaySetLimitError,
)

_DATABASE_URL = os.getenv("NIIBOT_TEST_DATABASE_URL")


async def _configure_json(conn: asyncpg.Connection) -> None:
    for type_name in ("jsonb", "json"):
        await conn.set_type_codec(
            type_name,
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_roleplay_publish_activate_and_database_invariants() -> None:
    assert _DATABASE_URL is not None
    pool = await asyncpg.create_pool(
        _DATABASE_URL,
        min_size=1,
        max_size=3,
        init=_configure_json,
    )
    channel_id = f"test-roleplay-{uuid4().hex}"
    other_channel_id = f"test-roleplay-other-{uuid4().hex}"
    try:
        async with pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
                [(channel_id,), (other_channel_id,)],
            )

        repository = RoleplayRepository(pool)
        package = sample_roleplay_package()
        roleplay_set = await repository.create_set(channel_id, "月港守望者", package)
        revision = await repository.publish(
            channel_id,
            roleplay_set.id,
            expected_draft_version=roleplay_set.draft_version,
        )
        activated = await repository.activate(channel_id, roleplay_set.id, revision.id)
        active = await repository.get_active_revision(channel_id)

        assert activated == revision
        assert active == revision

        with pytest.raises(RoleplayRevisionOwnershipError):
            await repository.activate(other_channel_id, roleplay_set.id, revision.id)

        async with pool.acquire() as conn:
            with pytest.raises(asyncpg.PostgresError):
                await conn.execute(
                    "UPDATE roleplay_revisions SET capsule = 'changed' WHERE id = $1",
                    revision.id,
                )
            settings = await conn.fetchrow(
                """
                SELECT assistant_mode, active_roleplay_revision_id
                FROM ai_settings
                WHERE channel_id = $1
                """,
                channel_id,
            )
        assert settings is not None
        assert settings["assistant_mode"] == "roleplay"
        assert settings["active_roleplay_revision_id"] == revision.id

        await repository.use_persona(channel_id)
        assert await repository.get_active_revision(channel_id) is None

        changed_package = replace(
            package,
            world=replace(package.world, story_stage="潮汐祭當日清晨。"),
        )
        updated = await repository.update_draft(
            channel_id,
            roleplay_set.id,
            changed_package,
            expected_draft_version=roleplay_set.draft_version,
        )
        second_revision = await repository.publish(
            channel_id,
            roleplay_set.id,
            expected_draft_version=updated.draft_version,
        )
        assert second_revision.revision_number == 2
        assert second_revision.compiled.content_digest != revision.compiled.content_digest

        for index in range(4):
            await repository.create_set(channel_id, f"備用設定 {index + 1}", package)
        with pytest.raises(RoleplaySetLimitError):
            await repository.create_set(channel_id, "超出上限", package)
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM channels WHERE channel_id = ANY($1::text[])",
                [channel_id, other_channel_id],
            )
        await pool.close()
