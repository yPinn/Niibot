"""Versioned notification contract for assistant identity changes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

ASSISTANT_SCOPE_CHANGED_CHANNEL = "assistant_scope_changed"
ASSISTANT_SCOPE_CHANGE_VERSION = 1


class AssistantMode(StrEnum):
    PERSONA = "persona"
    ROLEPLAY = "roleplay"


@dataclass(frozen=True, slots=True)
class AssistantScope:
    """Validated identity for one assistant conversation namespace."""

    assistant_mode: AssistantMode
    active_roleplay_revision_id: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.assistant_mode, AssistantMode):
            raise ValueError("assistant mode is invalid")
        revision_id = self.active_roleplay_revision_id
        if self.assistant_mode is AssistantMode.PERSONA:
            if revision_id is not None:
                raise ValueError("persona mode cannot carry a role-play revision")
        elif type(revision_id) is not int or revision_id <= 0:
            raise ValueError("role-play mode requires a positive revision id")

    @property
    def memory_key(self) -> str:
        if self.assistant_mode is AssistantMode.PERSONA:
            return "persona"
        return f"roleplay:{self.active_roleplay_revision_id}"


@dataclass(frozen=True, slots=True)
class AssistantScopeChange:
    """The only state change that invalidates an assistant conversation scope."""

    channel_id: str
    assistant_mode: AssistantMode
    active_roleplay_revision_id: int | None

    def __post_init__(self) -> None:
        if not self.channel_id.strip():
            raise ValueError("channel_id must not be blank")
        AssistantScope(
            assistant_mode=self.assistant_mode,
            active_roleplay_revision_id=self.active_roleplay_revision_id,
        )

    @property
    def scope(self) -> AssistantScope:
        return AssistantScope(
            assistant_mode=self.assistant_mode,
            active_roleplay_revision_id=self.active_roleplay_revision_id,
        )

    def to_payload(self) -> str:
        return json.dumps(
            {
                "version": ASSISTANT_SCOPE_CHANGE_VERSION,
                "channel_id": self.channel_id,
                "assistant_mode": self.assistant_mode.value,
                "active_roleplay_revision_id": self.active_roleplay_revision_id,
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_payload(cls, payload: str) -> AssistantScopeChange:
        try:
            value = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("assistant scope payload must be valid JSON") from error
        if not isinstance(value, dict):
            raise ValueError("assistant scope payload must be an object")
        expected = {
            "version",
            "channel_id",
            "assistant_mode",
            "active_roleplay_revision_id",
        }
        if set(value) != expected:
            raise ValueError("assistant scope payload fields are invalid")
        if type(value["version"]) is not int or value["version"] != ASSISTANT_SCOPE_CHANGE_VERSION:
            raise ValueError("assistant scope payload version is unsupported")
        channel_id = value["channel_id"]
        mode = value["assistant_mode"]
        revision_id = value["active_roleplay_revision_id"]
        if not isinstance(channel_id, str) or not isinstance(mode, str):
            raise ValueError("assistant scope payload scalar types are invalid")
        if revision_id is not None and type(revision_id) is not int:
            raise ValueError("assistant scope revision type is invalid")
        try:
            assistant_mode = AssistantMode(mode)
        except ValueError as error:
            raise ValueError("assistant scope mode is invalid") from error
        return cls(
            channel_id=channel_id,
            assistant_mode=assistant_mode,
            active_roleplay_revision_id=revision_id,
        )
