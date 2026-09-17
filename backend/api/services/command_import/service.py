"""Orchestration for command imports: preview caching and applying a selection."""

from __future__ import annotations

import logging
import secrets

import asyncpg
import httpx

from services.command_config_service import CommandConfigService
from shared.cache import AsyncTTLCache
from shared.repositories.command_config import CommandConfigRepository
from shared.repositories.message_trigger import MessageTriggerRepository

from .models import ImportItem, ImportPreview, ImportResult, ImportSection, ImportStatus
from .sources.nightbot import NightbotSource
from .sources.streamelements import StreamElementsSource

LOGGER: logging.Logger = logging.getLogger(__name__)

# A preview lives just long enough for the user to read it and decide. Keeping
# it in process is safe because the API runs a single uvicorn worker, and it
# means an aborted import leaves nothing behind.
_PREVIEW_TTL_SECONDS = 600.0
_preview_cache: AsyncTTLCache = AsyncTTLCache(
    maxsize=64, ttl=_PREVIEW_TTL_SECONDS, name="command_import.preview"
)


class PreviewNotFoundError(Exception):
    """The preview expired, or belongs to a different user."""


# Module-level rather than methods: the service is rebuilt per request by
# Depends, so the handoff between the OAuth callback and the dashboard cannot
# live on an instance.


def stash_preview(user_id: str, preview: ImportPreview) -> str:
    import_id = secrets.token_urlsafe(16)
    _preview_cache.set(f"preview:{import_id}", (user_id, preview))
    return import_id


def load_preview(user_id: str, import_id: str) -> ImportPreview:
    """Return a stashed preview, or raise if it expired or belongs elsewhere."""
    entry = _preview_cache.get(f"preview:{import_id}")
    if not isinstance(entry, tuple) or entry[0] != user_id:
        raise PreviewNotFoundError(import_id)
    return entry[1]


class CommandImportService:
    """Fetches import previews and writes the rows the user selected."""

    def __init__(self, pool: asyncpg.Pool, http: httpx.AsyncClient) -> None:
        self.pool = pool
        self.http = http
        self.cmd_repo = CommandConfigRepository(pool)
        self.trigger_repo = MessageTriggerRepository(pool)
        self.commands = CommandConfigService(pool)

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    async def existing_names(self, channel_id: str) -> set[str]:
        """Every command name and alias already taken on this channel."""
        taken: set[str] = set()
        for cfg in await self.cmd_repo.list_configs(channel_id):
            taken.add(cfg.command_name.lower())
            for alias in (cfg.aliases or "").split(","):
                if alias.strip():
                    taken.add(alias.strip().lower())
        return taken

    async def existing_trigger_names(self, channel_id: str) -> set[str]:
        """Trigger names already taken. Kept separate from command names because
        the two live in different tables with independent uniqueness.
        """
        return {t.trigger_name.lower() for t in await self.trigger_repo.list_all(channel_id)}

    async def preview_streamelements(self, channel_id: str, twitch_login: str) -> ImportPreview:
        source = StreamElementsSource(self.http)
        return await source.fetch_preview(twitch_login, await self.existing_names(channel_id))

    async def preview_nightbot(self, channel_id: str, token: str) -> ImportPreview:
        source = self._nightbot()
        try:
            return await source.fetch_preview(token, await self.existing_names(channel_id))
        finally:
            await source.revoke(token)

    def _nightbot(self) -> NightbotSource:
        from core.config import get_settings

        settings = get_settings()
        return NightbotSource(
            self.http,
            settings.nightbot_client_id or "",
            settings.nightbot_client_secret or "",
        )

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    async def apply(
        self,
        channel_id: str,
        preview: ImportPreview,
        selections: dict[str, bool],
    ) -> ImportResult:
        """Write the selected items. *selections* maps item key → enabled.

        Writes go through the repositories' insert-only primitives, which let
        the unique constraint decide rather than a check this coroutine made
        earlier. A stale preview, a second browser tab, or a re-run therefore
        cannot overwrite something that already exists.
        """
        result = ImportResult()
        taken = await self.existing_names(channel_id)
        taken_triggers = await self.existing_trigger_names(channel_id)
        by_key = {item.key: item for item in preview.items}

        for key, enabled in selections.items():
            item = by_key.get(key)
            if item is None or item.section is ImportSection.UNSUPPORTED:
                result.skipped += 1
                continue
            try:
                applied = await self._apply_one(channel_id, item, enabled, taken, taken_triggers)
            except Exception as exc:  # one bad row must not abort the batch
                LOGGER.warning(
                    "command_import_failed",
                    extra={"key": key, "error": f"{type(exc).__name__}: {exc}"},
                )
                result.failed += 1
                result.errors.append(f"{item.source_name}: {exc}")
                continue
            if applied:
                result.created += 1
                if enabled:
                    result.enabled += 1
            else:
                result.skipped += 1
        return result

    async def _apply_one(
        self,
        channel_id: str,
        item: ImportItem,
        enabled: bool,
        taken: set[str],
        taken_triggers: set[str],
    ) -> bool:
        """Write one item. Returns False when it was skipped rather than written."""
        if item.section is ImportSection.BUILTIN:
            if not item.builtin_target:
                return False
            await self.commands.toggle_command(channel_id, item.builtin_target, enabled)
            return True

        if item.section is ImportSection.TRIGGER:
            if not item.pattern or not item.response:
                return False
            name = (item.command_name or item.pattern)[:50]
            if name.lower() in taken_triggers:
                return False
            created = await self.trigger_repo.try_insert(
                channel_id,
                name,
                match_type=item.match_type,
                pattern=item.pattern,
                case_sensitive=False,
                response=item.response,
                min_role=item.min_role,
                cooldown=item.cooldown,
                priority=0,
                enabled=enabled,
                aliases=",".join(item.aliases) or None,
            )
            if created is None:
                return False
            taken_triggers.add(name.lower())
            return True

        if item.section is not ImportSection.CUSTOM:
            return False

        name = (item.command_name or "").lower()
        if not name or not item.response or name in taken:
            return False
        aliases = [a for a in item.aliases if a not in taken]
        created = await self.cmd_repo.try_insert_config(
            channel_id,
            name,
            custom_response=item.response,
            cooldown=item.cooldown,
            min_role=item.min_role,
            aliases=",".join(aliases) or None,
            enabled=enabled,
        )
        if created is None:
            return False
        taken.add(name)
        taken.update(aliases)
        return True


def default_selection(preview: ImportPreview, *, enabled: bool = False) -> dict[str, bool]:
    """The checkbox state the dashboard opens with.

    Conflicting and unsupported rows start unticked — the user has not read the
    contents yet, and a silent overwrite is the one outcome no import should
    ever produce.
    """
    return {
        item.key: enabled
        for item in preview.items
        if item.status in (ImportStatus.OK, ImportStatus.REVIEW)
    }
