"""Event config service — business-logic layer for event configurations."""

from dataclasses import asdict

import asyncpg

from shared.events import EVENT_CATALOG, EventDef
from shared.models.event_config import EventConfig
from shared.repositories.event_config import DEFAULT_TEMPLATES, EVENT_TYPES, EventConfigRepository

_BY_KEY: dict[str, EventDef] = {e.key: e for e in EVENT_CATALOG}


def _project_options(event_type: str, raw: dict | None) -> dict:
    """Keep only the options this event's schema declares, coerced to bool.

    Unknown keys are dropped and missing keys fall back to their schema default,
    so the stored ``options`` blob can never drift from the catalog. Policy:
    removing an option from the schema deletes it from stored config on the next
    write. Applied on both read and write in this service — the bot's
    ``EventConfigRepository.get_config`` path is deliberately left untouched.
    """
    defn = _BY_KEY.get(event_type)
    if defn is None:
        return {}
    raw = raw or {}
    return {opt.key: bool(raw.get(opt.key, opt.default)) for opt in defn.options_schema}


def _trigger_count(event_type: str, counts: dict[str, int]) -> int | None:
    """Trigger count from the event's ``stream_events`` bucket, or ``None`` when
    the event writes no such row (dashboard renders "—", not a misleading 0)."""
    defn = _BY_KEY.get(event_type)
    if defn is None or defn.count_source is None:
        return None
    return counts.get(defn.count_source, 0)


class EventConfigService:
    """API-facing event config operations."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.repo = EventConfigRepository(pool)

    def _shape(self, cfg: EventConfig, counts: dict[str, int]) -> dict:
        d = asdict(cfg)
        d["options"] = _project_options(cfg.event_type, d.get("options"))
        d["trigger_count"] = _trigger_count(cfg.event_type, counts)
        return d

    async def list_configs_with_counts(self, channel_id: str) -> list[dict]:
        """Get configs with trigger counts from stream_events."""
        configs = await self.repo.ensure_defaults(channel_id)
        counts = await self._get_trigger_counts(channel_id)
        return [self._shape(cfg, counts) for cfg in configs]

    async def update_config(
        self,
        channel_id: str,
        event_type: str,
        message_template: str,
        enabled: bool,
        options: dict | None = None,
    ) -> dict:
        """Update an event config and return it with trigger count.

        ``options`` is projected onto the event's schema before it is stored —
        see ``_project_options``.
        """
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Invalid event_type: {event_type}")
        projected = _project_options(event_type, options)
        cfg = await self.repo.upsert_config(
            channel_id, event_type, message_template, enabled, projected
        )
        counts = await self._get_trigger_counts(channel_id)
        return self._shape(cfg, counts)

    async def toggle_config(self, channel_id: str, event_type: str, enabled: bool) -> dict:
        """Toggle an event config's enabled state."""
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Invalid event_type: {event_type}")
        # Get existing config first to preserve template
        existing = await self.repo.get_config(channel_id, event_type)
        if existing is None:
            # Ensure defaults exist
            await self.repo.ensure_defaults(channel_id)
            existing = await self.repo.get_config(channel_id, event_type)
        template = existing.message_template if existing else DEFAULT_TEMPLATES.get(event_type, "")
        projected = _project_options(event_type, existing.options if existing else None)
        cfg = await self.repo.upsert_config(channel_id, event_type, template, enabled, projected)
        counts = await self._get_trigger_counts(channel_id)
        return self._shape(cfg, counts)

    async def _get_trigger_counts(self, channel_id: str) -> dict[str, int]:
        return await self.repo.get_stream_event_counts(channel_id)
