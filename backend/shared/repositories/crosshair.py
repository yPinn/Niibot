"""Repository for crosshairs table."""

from __future__ import annotations

import asyncpg

_COLUMNS = "id, channel_id, game, name, code, description, display_order, copy_count, created_at, updated_at"

_ALL_COLUMNS = (
    "c.id, c.channel_id, c.game, c.name, c.code, c.description, "
    "c.display_order, c.copy_count, c.created_at, c.updated_at, "
    "COALESCE(ch.display_name, ch.channel_name) AS channel_name"
)

VALID_GAMES = frozenset({"valorant"})


class CrosshairRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def list_by_channel(self, channel_id: str, game: str | None = None) -> list[dict]:
        if game and game in VALID_GAMES:
            query = (
                f"SELECT {_COLUMNS} FROM crosshairs "
                "WHERE channel_id = $1 AND game = $2 "
                "ORDER BY display_order, created_at"
            )
            params: tuple = (channel_id, game)
        else:
            query = (
                f"SELECT {_COLUMNS} FROM crosshairs "
                "WHERE channel_id = $1 "
                "ORDER BY display_order, created_at"
            )
            params = (channel_id,)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def list_all_public(self, game: str | None = None, limit: int = 100) -> list[dict]:
        """Return crosshairs from all channels, newest first, with channel_name."""
        if game and game in VALID_GAMES:
            query = (
                f"SELECT {_ALL_COLUMNS} FROM crosshairs c "
                "JOIN channels ch ON c.channel_id = ch.channel_id "
                "WHERE c.game = $2 "
                "ORDER BY c.created_at DESC LIMIT $1"
            )
            params: tuple = (limit, game)
        else:
            query = (
                f"SELECT {_ALL_COLUMNS} FROM crosshairs c "
                "JOIN channels ch ON c.channel_id = ch.channel_id "
                "ORDER BY c.created_at DESC LIMIT $1"
            )
            params = (limit,)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def create(
        self,
        channel_id: str,
        *,
        game: str,
        name: str,
        code: str,
        description: str | None = None,
        display_order: int = 0,
    ) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO crosshairs
                    (channel_id, game, name, code, description, display_order)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING {_COLUMNS}
                """,
                channel_id,
                game,
                name,
                code,
                description,
                display_order,
            )
            return dict(row)

    _ALLOWED_COLUMNS = frozenset({"game", "name", "code", "description", "display_order"})

    async def update(
        self,
        crosshair_id: str,
        channel_id: str,
        *,
        fields: dict,
    ) -> dict | None:
        safe = {k: v for k, v in fields.items() if k in self._ALLOWED_COLUMNS}
        if not safe:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"SELECT {_COLUMNS} FROM crosshairs WHERE id = $1::uuid AND channel_id = $2",
                    crosshair_id,
                    channel_id,
                )
                return dict(row) if row else None

        set_clause = ", ".join(f"{col} = ${i}" for i, col in enumerate(safe, start=3))
        params: list = [crosshair_id, channel_id, *safe.values()]
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"UPDATE crosshairs SET {set_clause}"
                f" WHERE id = $1::uuid AND channel_id = $2"
                f" RETURNING {_COLUMNS}",
                *params,
            )
            return dict(row) if row else None

    async def get_by_name(self, channel_id: str, name: str) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM crosshairs "
                "WHERE channel_id = $1 AND lower(name) = lower($2)",
                channel_id,
                name,
            )
            return dict(row) if row else None

    async def search_by_name(self, channel_id: str, name: str) -> dict | None:
        """Case-insensitive lookup with prefix then contains fallback."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM crosshairs "
                "WHERE channel_id = $1 AND ("
                "  lower(name) = lower($2)"
                "  OR lower(name) LIKE lower($2) || '%'"
                "  OR lower(name) LIKE '%' || lower($2) || '%'"
                ") "
                "ORDER BY "
                "  CASE WHEN lower(name) = lower($2) THEN 0 "
                "       WHEN lower(name) LIKE lower($2) || '%' THEN 1 "
                "       ELSE 2 END, "
                "  display_order, created_at "
                "LIMIT 1",
                channel_id,
                name,
            )
            return dict(row) if row else None

    async def increment_copy(self, crosshair_id: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE crosshairs SET copy_count = copy_count + 1 WHERE id = $1::uuid",
                crosshair_id,
            )

    async def delete(self, crosshair_id: str, channel_id: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM crosshairs WHERE id = $1::uuid AND channel_id = $2",
                crosshair_id,
                channel_id,
            )
            return result != "DELETE 0"
