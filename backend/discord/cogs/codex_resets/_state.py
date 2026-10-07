"""Persistent state for the Codex Resets cog (atomic JSON on disk)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LOGGER: logging.Logger = logging.getLogger(__name__)

SEEN_IDS_CAP = 200
DEFAULT_REMINDER_MINUTES = 30


@dataclass
class GuildConfig:
    channel_id: int
    watch: bool = False
    # IANA name (e.g. "Asia/Taipei"); None = Discord timestamps in each viewer's zone.
    timezone: str | None = None
    # Minutes before an announced scheduled reset to remind; None = off.
    reminder_minutes: int | None = DEFAULT_REMINDER_MINUTES

    @property
    def zone(self) -> ZoneInfo | None:
        if not self.timezone:
            return None
        try:
            return ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            return None


@dataclass
class TrackedPost:
    """A notification that may be edited later (scheduled reset / watch)."""

    key: str
    payload: dict[str, Any]
    messages: list[tuple[int, int]] = field(default_factory=list)  # (channel_id, message_id)
    # Guild ids already reminded about this post (scheduled resets only).
    reminded: list[int] = field(default_factory=list)


@dataclass
class CodexState:
    guilds: dict[int, GuildConfig] = field(default_factory=dict)
    # None until the first successful poll, which seeds silently instead of
    # announcing whatever happens to be current.
    seen_ids: list[str] | None = None
    scheduled: TrackedPost | None = None
    watch: TrackedPost | None = None

    def mark_seen(self, ids: list[str]) -> None:
        merged = list(dict.fromkeys([*ids, *(self.seen_ids or [])]))
        self.seen_ids = merged[:SEEN_IDS_CAP]


def _tracked_to_dict(post: TrackedPost | None) -> dict[str, Any] | None:
    if post is None:
        return None
    return {
        "key": post.key,
        "payload": post.payload,
        "messages": post.messages,
        "reminded": post.reminded,
    }


def _tracked_from_dict(raw: Any) -> TrackedPost | None:
    if not isinstance(raw, dict):
        return None
    return TrackedPost(
        key=str(raw["key"]),
        payload=dict(raw["payload"]),
        messages=[(int(c), int(m)) for c, m in raw.get("messages", [])],
        reminded=[int(g) for g in raw.get("reminded", [])],
    )


class StateStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> CodexState:
        try:
            with open(self._path, encoding="utf-8") as f:
                raw = json.load(f)
            return CodexState(
                guilds={
                    int(gid): GuildConfig(
                        int(cfg["channel_id"]),
                        bool(cfg.get("watch", False)),
                        cfg.get("timezone") or None,
                        cfg.get("reminder_minutes", DEFAULT_REMINDER_MINUTES),
                    )
                    for gid, cfg in raw.get("guilds", {}).items()
                },
                seen_ids=raw.get("seen_ids"),
                scheduled=_tracked_from_dict(raw.get("scheduled")),
                watch=_tracked_from_dict(raw.get("watch")),
            )
        except FileNotFoundError:
            return CodexState()
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            LOGGER.warning("CodexResets: state file unreadable, starting fresh", exc_info=True)
            return CodexState()

    def save(self, state: CodexState) -> None:
        payload = json.dumps(
            {
                "guilds": {
                    str(gid): {
                        "channel_id": cfg.channel_id,
                        "watch": cfg.watch,
                        "timezone": cfg.timezone,
                        "reminder_minutes": cfg.reminder_minutes,
                    }
                    for gid, cfg in state.guilds.items()
                },
                "seen_ids": state.seen_ids,
                "scheduled": _tracked_to_dict(state.scheduled),
                "watch": _tracked_to_dict(state.watch),
            },
            ensure_ascii=False,
            indent=2,
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", dir=self._path.parent, encoding="utf-8", delete=False, suffix=".tmp"
        ) as tmp:
            tmp.write(payload)
            tmp_path = tmp.name
        os.replace(tmp_path, self._path)
