"""Audit-log query helpers for the events cog."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

import discord


async def _find_audit_entry(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    *,
    match: Callable[[discord.AuditLogEntry], bool],
    max_age: float = 10.0,
    attempts: tuple[float, ...] = (1.0, 1.5),
) -> tuple[discord.AuditLogEntry | None, bool]:
    """Poll the audit log for a recent entry matching *match*.

    Returns ``(entry, audit_available)``. ``audit_available`` is False only when
    the bot lacks the View Audit Log permission, letting callers distinguish
    "no permission" (truly unknown) from "no matching entry" (e.g. a genuine
    self-action, which audit logs never record).

    Polls across *attempts* delays to tolerate audit-log propagation lag, which
    a single fixed sleep does not.

    Known limitation (not handled): Discord coalesces consecutive deletions by
    the same user in the same channel into one audit entry with an incrementing
    count, so the Nth rapid deletion cannot be attributed precisely; we match
    the most recent entry within the time window.
    """
    for delay in attempts:
        await asyncio.sleep(delay)
        try:
            async for entry in guild.audit_logs(limit=10, action=action):
                if (datetime.now(UTC) - entry.created_at).total_seconds() < max_age and match(
                    entry
                ):
                    return entry, True
        except discord.Forbidden:
            return None, False
    return None, True


async def _find_deleter(
    guild: discord.Guild,
    channel_id: int,
    author_id: int,
) -> tuple[discord.Member | discord.User | None, bool]:
    """Find who deleted a message via audit log.

    Returns ``(deleter, audit_available)``; ``deleter`` is None on a self-delete
    or when no matching audit entry exists. ``audit_available`` is False when the
    bot lacks the View Audit Log permission.
    """

    def _match(entry: discord.AuditLogEntry) -> bool:
        extra_channel = getattr(entry.extra, "channel", None)
        return bool(
            entry.target
            and entry.target.id == author_id
            and extra_channel is not None
            and getattr(extra_channel, "id", None) == channel_id
        )

    entry, available = await _find_audit_entry(
        guild, discord.AuditLogAction.message_delete, match=_match, max_age=15.0
    )
    return (entry.user if entry else None), available
