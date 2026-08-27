"""Admin: global module configuration (knowledge packs) — owner-only."""

import json

from asyncpg import Pool
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.dependencies import get_db_pool, require_owner
from shared.repositories.module_config import ModuleConfigRepository

router = APIRouter()


class AiPacksPatch(BaseModel):
    enabled_packs: list[str]


@router.get("/modules/ai-packs", response_model=list[str])
async def get_module_ai_packs(
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> list[str]:
    """Return globally enabled knowledge pack IDs. Owner-only."""
    return await ModuleConfigRepository(pool).get_enabled_packs()


@router.patch("/modules/ai-packs", response_model=list[str])
async def set_module_ai_packs(
    body: AiPacksPatch,
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> list[str]:
    """Set globally enabled knowledge pack IDs and notify all bots to reload. Owner-only."""
    result = await ModuleConfigRepository(pool).set_enabled_packs(body.enabled_packs)
    payload = json.dumps({"table": "module_config"})
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_notify('config_change', $1)", payload)
    return result
