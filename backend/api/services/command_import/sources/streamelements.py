"""StreamElements import source.

Everything needed is public: the channel lookup, the custom command list, and
the per-channel enabled state of the default commands. No OAuth, no token, no
stored credentials — the Twitch login the user already signed in with is enough.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from urllib.parse import quote

import httpx

from ..mapping import (
    check_length,
    classify,
    default_command_item,
    find_conflict,
    normalize_command_name,
    streamelements_role,
    translate_variables,
)
from ..models import ImportItem, ImportPreview, ImportSection, ImportSource, ImportStatus
from ._http import get_json

API_BASE = "https://api.streamelements.com/kappa/v2"

_SOURCE = ImportSource.STREAMELEMENTS.value


class ChannelNotOnStreamElementsError(Exception):
    """The Twitch login has no StreamElements channel."""


class StreamElementsSource:
    """Builds an ImportPreview from a channel's public StreamElements data."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def fetch_preview(self, twitch_login: str, existing: set[str]) -> ImportPreview:
        channel_id = await self._resolve_channel(twitch_login)
        # The two command lists are independent; one round trip instead of two.
        custom, defaults = await asyncio.gather(
            self._get(f"/bot/commands/{channel_id}"),
            self._get(f"/bot/commands/{channel_id}/default"),
        )

        items: list[ImportItem] = []
        for raw in defaults or []:
            item = self._map_default(raw)
            if item:
                items.append(item)
        for raw in custom or []:
            items.extend(self._map_custom(raw, existing))

        return ImportPreview(
            source=ImportSource.STREAMELEMENTS,
            source_channel=twitch_login,
            items=items,
        )

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def _resolve_channel(self, twitch_login: str) -> str:
        data = await self._get(f"/channels/{quote(twitch_login, safe='')}")
        if not isinstance(data, dict) or not data.get("_id"):
            raise ChannelNotOnStreamElementsError(twitch_login)
        return str(data["_id"])

    async def _get(self, path: str):
        return await get_json(self._http, f"{API_BASE}{path}", label="StreamElements")

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_default(raw: dict) -> ImportItem | None:
        """Map an enabled StreamElements default command onto a Niibot builtin.

        Defaults the channel never turned on are skipped entirely — listing
        every one of the 72 would bury the rows that matter.
        """
        if not raw.get("enabled"):
            return None
        command = str(raw.get("command") or "")
        if not command:
            return None
        return default_command_item(command, key_prefix="se", platform="StreamElements")

    @staticmethod
    def _map_custom(raw: dict, existing: set[str]) -> list[ImportItem]:
        """Map one custom command, fanning out its keywords into a trigger."""
        command = str(raw.get("command") or "")
        name = normalize_command_name(command)
        if not name:
            return []

        reply = str(raw.get("reply") or "")
        response, notes, blockers = translate_variables(reply, _SOURCE)
        role, role_notes = streamelements_role(raw.get("accessLevel"))
        notes = [*role_notes, *notes]

        # A "mention" or "reply" command addresses the chatter by name; our
        # responses always reply, so only the explicit @ needs recreating.
        if raw.get("type") in ("mention", "reply") and "$(user)" not in response:
            response = f"$(user) {response}".strip()
            notes.append("原本會 @ 發話者，已在回應前面加上 $(user)")
        if raw.get("type") == "whisper":
            blockers.append("原本是私訊回覆，Niibot 只會在聊天室回應")

        cooldown, cooldown_notes = _merge_cooldown(raw.get("cooldown") or {})
        notes += cooldown_notes
        if raw.get("cost"):
            blockers.append("需要消耗忠誠點數，Niibot 沒有點數系統")
        blockers += check_length(response)

        aliases = [normalize_command_name(a) for a in raw.get("aliases") or []]
        aliases = [a for a in aliases if a and a != name]

        status, section, notes = classify(notes, blockers, find_conflict(name, existing))
        command_item = ImportItem(
            key=f"se:cmd:{name}",
            section=section,
            status=status,
            source_name=f"!{command}",
            source_enabled=bool(raw.get("enabled")),
            notes=notes,
            command_name=name,
            response=response,
            original_response=reply,
            cooldown=cooldown or None,
            min_role=role,
            aliases=aliases,
        )

        keywords = [str(k).strip() for k in raw.get("keywords") or [] if str(k).strip()]
        if not keywords or blockers:
            return [command_item]

        extra = f"，另外 {len(keywords) - 1} 組關鍵字放進別名" if len(keywords) > 1 else ""
        trigger_item = replace(
            command_item,
            key=f"se:kw:{name}",
            section=ImportSection.TRIGGER,
            status=ImportStatus.REVIEW if notes else ImportStatus.OK,
            source_name=keywords[0],
            notes=[*notes, f"從 !{command} 的關鍵字建立自動回應{extra}"],
            aliases=keywords[1:],
            pattern=keywords[0],
            match_type="contains",
        )
        return [command_item, trigger_item]


def _merge_cooldown(cooldown: dict) -> tuple[int, list[str]]:
    """Fold StreamElements' separate per-user and global cooldowns into our one.

    Takes the larger of the two, matching migration 009's GREATEST when the two
    columns were merged here as well.
    """
    per_user, glob = int(cooldown.get("user") or 0), int(cooldown.get("global") or 0)
    merged = max(per_user, glob)
    if per_user == glob:
        return merged, []
    return merged, [f"原本分開設定的冷卻（個人 {per_user}s / 全域 {glob}s）合併為 {merged}s"]
