"""Repository for the quotes table."""

from __future__ import annotations

import asyncpg

from shared.models.quote import Quote

_COLUMNS = "id, channel_id, quote_number, quote_text, created_by, created_at"


class QuoteRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def add(self, channel_id: str, quote_text: str, created_by: str) -> Quote:
        """Insert a quote, assigning it the channel's next quote_number.

        The read (current max) and the write happen in one statement, so this
        is race-free without an explicit transaction.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO quotes (channel_id, quote_number, quote_text, created_by)
                SELECT $1, COALESCE(MAX(quote_number), 0) + 1, $2, $3
                FROM quotes WHERE channel_id = $1
                RETURNING {_COLUMNS}
                """,
                channel_id,
                quote_text,
                created_by,
            )
            return Quote(**dict(row))

    async def get_random(self, channel_id: str) -> Quote | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM quotes WHERE channel_id = $1 ORDER BY random() LIMIT 1",
                channel_id,
            )
            return Quote(**dict(row)) if row else None

    async def get_by_number(self, channel_id: str, quote_number: int) -> Quote | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM quotes WHERE channel_id = $1 AND quote_number = $2",
                channel_id,
                quote_number,
            )
            return Quote(**dict(row)) if row else None

    async def delete(self, channel_id: str, quote_number: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM quotes WHERE channel_id = $1 AND quote_number = $2",
                channel_id,
                quote_number,
            )
            return result != "DELETE 0"
