"""PostgreSQL integration regressions for command catalog materialisation."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest

from shared.repositories.command_config import CommandConfigRepository

_DATABASE_URL = os.getenv("NIIBOT_TEST_DATABASE_URL")
_ROLE_MIGRATION = (
    Path(__file__).parents[2]
    / "shared"
    / "migrations"
    / "versions"
    / "147_repair_builtin_command_roles.sql"
)
_NAMESPACE_MIGRATION = (
    Path(__file__).parents[2]
    / "shared"
    / "migrations"
    / "versions"
    / "150_disable_reserved_custom_command_conflicts.sql"
)
_CONCISE_ALIAS_MIGRATION = (
    Path(__file__).parents[2]
    / "shared"
    / "migrations"
    / "versions"
    / "152_disable_concise_alias_conflicts.sql"
)


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_builtin_materialisation_preserves_catalog_defaults() -> None:
    assert _DATABASE_URL is not None
    pool = await asyncpg.create_pool(_DATABASE_URL, min_size=1, max_size=1)
    channel_id = f"test-command-config-{uuid4().hex}"
    repository = CommandConfigRepository(pool)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
                channel_id,
            )

        marker = await repository.upsert_config(channel_id, "marker", enabled=True)
        assert marker.enabled is True
        assert marker.min_role == "moderator"
        assert marker.cooldown == 10

        await repository.increment_usage_count(channel_id, "condemn")
        condemn = await repository.get_config(channel_id, "condemn")
        assert condemn is not None
        assert condemn.enabled is False
        assert condemn.min_role == "moderator"
        assert condemn.cooldown == 5
        assert condemn.usage_count == 1
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id)
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_concurrent_custom_insert_claims_name_or_alias_only_once() -> None:
    assert _DATABASE_URL is not None
    pool = await asyncpg.create_pool(_DATABASE_URL, min_size=1, max_size=2)
    channel_id = f"test-command-namespace-race-{uuid4().hex}"
    repository = CommandConfigRepository(pool)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
                channel_id,
            )

        first, second = await asyncio.gather(
            repository.try_insert_config(
                channel_id,
                "first",
                custom_response="first",
                aliases="shared",
            ),
            repository.try_insert_config(
                channel_id,
                "shared",
                custom_response="second",
            ),
        )

        assert sum(result is not None for result in (first, second)) == 1
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id)
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_role_repair_migration_tightens_only_unsafe_builtin_rows() -> None:
    """Execute the real SQL in a rollback-only transaction.

    The migration updates the shared table, so rollback also guarantees this
    integration test cannot alter any pre-existing development rows.
    """
    assert _DATABASE_URL is not None
    conn = await asyncpg.connect(_DATABASE_URL)
    transaction = conn.transaction()
    await transaction.start()
    suffix = uuid4().hex
    channel_id = f"test-command-migration-{suffix}"
    try:
        await conn.execute(
            "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
            channel_id,
        )
        await conn.executemany(
            """
            INSERT INTO command_configs
                (channel_id, command_name, command_type, enabled, min_role)
            VALUES ($1, $2, $3, TRUE, $4)
            """,
            [
                (channel_id, "subcount", "builtin", "everyone"),
                (channel_id, "marker", "builtin", "everyone"),
                (channel_id, "winner", "builtin", "vip"),
                (channel_id, "custom-marker", "custom", "everyone"),
            ],
        )

        await conn.execute(_ROLE_MIGRATION.read_text(encoding="utf-8"))
        rows = await conn.fetch(
            """
            SELECT command_name, min_role
            FROM command_configs
            WHERE channel_id = $1
            ORDER BY command_name
            """,
            channel_id,
        )

        assert {row["command_name"]: row["min_role"] for row in rows} == {
            "custom-marker": "everyone",
            "marker": "moderator",
            "subcount": "broadcaster",
            "winner": "vip",
        }
    finally:
        await transaction.rollback()
        await conn.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_namespace_repair_disables_conflicts_without_deleting_data() -> None:
    assert _DATABASE_URL is not None
    conn = await asyncpg.connect(_DATABASE_URL)
    transaction = conn.transaction()
    await transaction.start()
    channel_id = f"test-command-namespace-{uuid4().hex}"
    try:
        await conn.execute(
            "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
            channel_id,
        )
        rows = await conn.fetch(
            """
            INSERT INTO command_configs
                (channel_id, command_name, command_type, enabled, custom_response)
            VALUES
                ($1, 'help', 'custom', TRUE, 'legacy builtin collision'),
                ($1, 'cmd', 'custom', TRUE, 'legacy canonical'),
                ($1, 'safe-with-alias', 'custom', TRUE, 'legacy alias'),
                ($1, '抽', 'custom', TRUE, 'concise alias as command'),
                ($1, 'safe-with-concise-alias', 'custom', TRUE, 'concise alias'),
                ($1, 'safe', 'custom', TRUE, 'still works')
            RETURNING id, command_name
            """,
            channel_id,
        )
        ids = {row["command_name"]: row["id"] for row in rows}
        builtin_rows = await conn.fetch(
            """
            INSERT INTO command_configs
                (channel_id, command_name, command_type, enabled)
            VALUES
                ($1, 'title', 'builtin', FALSE),
                ($1, 'winner', 'builtin', FALSE),
                ($1, 'choose', 'builtin', TRUE),
                ($1, 'del', 'builtin', FALSE)
            RETURNING id, command_name
            """,
            channel_id,
        )
        builtin_ids = {row["command_name"]: row["id"] for row in builtin_rows}
        await conn.execute(
            "INSERT INTO command_aliases (command_id, alias) VALUES ($1, 'ai')",
            ids["safe-with-alias"],
        )
        await conn.execute(
            "INSERT INTO command_aliases (command_id, alias) VALUES ($1, '標題')",
            ids["safe-with-concise-alias"],
        )
        await conn.executemany(
            "INSERT INTO command_aliases (command_id, alias) VALUES ($1, $2)",
            [
                (builtin_ids["title"], "台標"),
                (builtin_ids["winner"], "幸運兒"),
                (builtin_ids["choose"], "選擇"),
                (builtin_ids["choose"], "選"),
                (builtin_ids["del"], "刪除"),
                (builtin_ids["del"], "vanish"),
            ],
        )

        await conn.execute(_NAMESPACE_MIGRATION.read_text(encoding="utf-8"))
        await conn.execute(_CONCISE_ALIAS_MIGRATION.read_text(encoding="utf-8"))
        repaired = await conn.fetch(
            """
            SELECT command_name, enabled, custom_response
            FROM command_configs
            WHERE channel_id = $1
              AND command_type = 'custom'
            ORDER BY command_name
            """,
            channel_id,
        )

        by_name = {
            row["command_name"]: (row["enabled"], row["custom_response"]) for row in repaired
        }
        legacy_help = next(name for name in by_name if name.startswith("__legacy_help_"))
        assert by_name.pop(legacy_help) == (False, "legacy builtin collision")
        assert by_name == {
            "cmd": (False, "legacy canonical"),
            "safe": (True, "still works"),
            "safe-with-concise-alias": (False, "concise alias"),
            "safe-with-alias": (False, "legacy alias"),
            "抽": (False, "concise alias as command"),
        }

        persisted_aliases = await conn.fetch(
            """
            SELECT command.command_name, alias.alias
            FROM command_configs AS command
            JOIN command_aliases AS alias ON alias.command_id = command.id
            WHERE command.channel_id = $1
              AND command.command_type = 'builtin'
            """,
            channel_id,
        )
        assert {(row["command_name"], row["alias"]) for row in persisted_aliases} == {
            ("title", "標題"),
            ("winner", "抽"),
            ("choose", "選"),
            ("del", "刪"),
            ("del", "vanish"),
        }

        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        repository = CommandConfigRepository(pool)
        help_config = await repository.get_config(channel_id, "help")
        configs = await repository.list_configs(channel_id)

        assert help_config is not None
        assert help_config.command_name == "help"
        assert help_config.command_type == "builtin"
        assert sum(cfg.command_name == "help" for cfg in configs) == 1
        archived = next(cfg for cfg in configs if cfg.command_name == legacy_help)
        assert archived.command_type == "custom"
        assert archived.custom_response == "legacy builtin collision"
    finally:
        await transaction.rollback()
        await conn.close()
