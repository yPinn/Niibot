"""Strict JSON boundary for Role-play authoring documents."""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from typing import Never

from shared.roleplay.compiler import canonical_roleplay_json
from shared.roleplay.contracts import (
    CanonMode,
    ChannelStage,
    CharacterKnowledge,
    CharacterSheet,
    LoreEntry,
    Relationship,
    RelationshipState,
    RoleplayPackage,
    Scene,
    SignaturePhrase,
    SignaturePhraseMode,
    SourceKind,
    SpoilerPolicy,
    ValidationIssue,
    WorldSnapshot,
)


class RoleplayDocumentError(ValueError):
    """Raised when JSON cannot be decoded without coercion or ignored fields."""

    def __init__(self, issue: ValidationIssue) -> None:
        self.issues = (issue,)
        super().__init__(issue.code)


def _fail(code: str, path: str, message: str) -> Never:
    raise RoleplayDocumentError(ValidationIssue(code=code, path=path, message=message))


def _object(
    value: object,
    *,
    path: str,
    fields: tuple[str, ...],
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail("document.type.object", path, "此欄位必須是物件")
    for field in fields:
        if field not in value:
            field_path = f"{path}.{field}" if path else field
            _fail("document.field.missing", field_path, "缺少必要欄位")
    unknown = sorted(str(key) for key in value if not isinstance(key, str) or key not in fields)
    if unknown:
        field = str(unknown[0])
        field_path = f"{path}.{field}" if path else field
        _fail("document.field.unknown", field_path, "包含不支援的欄位")
    return value


def _string(value: object, *, path: str) -> str:
    if not isinstance(value, str):
        _fail("document.type.string", path, "此欄位必須是文字")
    return value


def _optional_string(value: object, *, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path=path)


def _integer(value: object, *, path: str) -> int:
    if type(value) is not int:
        _fail("document.type.integer", path, "此欄位必須是整數")
    return value


def _boolean(value: object, *, path: str) -> bool:
    if type(value) is not bool:
        _fail("document.type.boolean", path, "此欄位必須是布林值")
    return value


def _items(value: object, *, path: str) -> list[object]:
    if not isinstance(value, list):
        _fail("document.type.array", path, "此欄位必須是陣列")
    return value


def _strings(value: object, *, path: str) -> tuple[str, ...]:
    return tuple(
        _string(item, path=f"{path}.{index}") for index, item in enumerate(_items(value, path=path))
    )


def _enum[EnumT: StrEnum](value: object, enum_type: type[EnumT], *, path: str) -> EnumT:
    raw = _string(value, path=path)
    try:
        return enum_type(raw)
    except ValueError:
        _fail("document.enum.invalid", path, "此欄位不是支援的選項")


def _decode_world(value: object) -> WorldSnapshot:
    fields = (
        "title",
        "source_kind",
        "canon_mode",
        "canon_scope",
        "world_anchor",
        "story_stage",
        "spoiler_policy",
    )
    data = _object(value, path="world", fields=fields)
    return WorldSnapshot(
        title=_string(data["title"], path="world.title"),
        source_kind=_enum(data["source_kind"], SourceKind, path="world.source_kind"),
        canon_mode=_enum(data["canon_mode"], CanonMode, path="world.canon_mode"),
        canon_scope=_string(data["canon_scope"], path="world.canon_scope"),
        world_anchor=_string(data["world_anchor"], path="world.world_anchor"),
        story_stage=_string(data["story_stage"], path="world.story_stage"),
        spoiler_policy=_enum(data["spoiler_policy"], SpoilerPolicy, path="world.spoiler_policy"),
    )


def _decode_relationship(value: object, index: int) -> Relationship:
    path = f"character.relationships.{index}"
    data = _object(
        value,
        path=path,
        fields=("subject", "role", "state", "notes"),
    )
    return Relationship(
        subject=_string(data["subject"], path=f"{path}.subject"),
        role=_string(data["role"], path=f"{path}.role"),
        state=_enum(data["state"], RelationshipState, path=f"{path}.state"),
        notes=_string(data["notes"], path=f"{path}.notes"),
    )


def _decode_knowledge(value: object) -> CharacterKnowledge:
    data = _object(
        value,
        path="character.knowledge",
        fields=("known", "unknown"),
    )
    return CharacterKnowledge(
        known=_strings(data["known"], path="character.knowledge.known"),
        unknown=_strings(data["unknown"], path="character.knowledge.unknown"),
    )


def _decode_signature_phrase(value: object, index: int) -> SignaturePhrase:
    path = f"character.signature_phrases.{index}"
    data = _object(value, path=path, fields=("text", "use_when", "mode"))
    return SignaturePhrase(
        text=_string(data["text"], path=f"{path}.text"),
        use_when=_string(data["use_when"], path=f"{path}.use_when"),
        mode=_enum(data["mode"], SignaturePhraseMode, path=f"{path}.mode"),
    )


def _decode_character(value: object, *, schema_version: int) -> CharacterSheet:
    base_fields = (
        "name",
        "role",
        "motivation",
        "stable_traits",
        "boundaries",
        "voice",
        "relationships",
        "knowledge",
    )
    fields = (*base_fields, "signature_phrases") if schema_version >= 2 else base_fields
    data = _object(value, path="character", fields=fields)
    relationships = _items(data["relationships"], path="character.relationships")
    phrase_items = (
        _items(data["signature_phrases"], path="character.signature_phrases")
        if schema_version >= 2
        else []
    )
    return CharacterSheet(
        name=_string(data["name"], path="character.name"),
        role=_string(data["role"], path="character.role"),
        motivation=_string(data["motivation"], path="character.motivation"),
        stable_traits=_strings(data["stable_traits"], path="character.stable_traits"),
        boundaries=_strings(data["boundaries"], path="character.boundaries"),
        voice=_string(data["voice"], path="character.voice"),
        relationships=tuple(
            _decode_relationship(item, index) for index, item in enumerate(relationships)
        ),
        knowledge=_decode_knowledge(data["knowledge"]),
        signature_phrases=tuple(
            _decode_signature_phrase(item, index) for index, item in enumerate(phrase_items)
        ),
    )


def _decode_scene(value: object) -> Scene:
    fields = (
        "location",
        "current_activity",
        "current_goal",
        "emotional_baseline",
        "channel_stage",
        "host_relationship",
        "audience_relationship",
        "adaptation_note",
        "host_character_mapping",
        "audience_character_mapping",
    )
    data = _object(value, path="scene", fields=fields)
    return Scene(
        location=_string(data["location"], path="scene.location"),
        current_activity=_string(data["current_activity"], path="scene.current_activity"),
        current_goal=_string(data["current_goal"], path="scene.current_goal"),
        emotional_baseline=_string(data["emotional_baseline"], path="scene.emotional_baseline"),
        channel_stage=_enum(data["channel_stage"], ChannelStage, path="scene.channel_stage"),
        host_relationship=_string(data["host_relationship"], path="scene.host_relationship"),
        audience_relationship=_string(
            data["audience_relationship"], path="scene.audience_relationship"
        ),
        adaptation_note=_string(data["adaptation_note"], path="scene.adaptation_note"),
        host_character_mapping=_optional_string(
            data["host_character_mapping"], path="scene.host_character_mapping"
        ),
        audience_character_mapping=_optional_string(
            data["audience_character_mapping"], path="scene.audience_character_mapping"
        ),
    )


def _decode_lore(value: object, index: int) -> LoreEntry:
    path = f"lore_entries.{index}"
    data = _object(
        value,
        path=path,
        fields=(
            "subject",
            "aliases",
            "content",
            "known_at_stage",
            "contains_spoilers",
            "priority",
        ),
    )
    return LoreEntry(
        subject=_string(data["subject"], path=f"{path}.subject"),
        aliases=_strings(data["aliases"], path=f"{path}.aliases"),
        content=_string(data["content"], path=f"{path}.content"),
        known_at_stage=_boolean(data["known_at_stage"], path=f"{path}.known_at_stage"),
        contains_spoilers=_boolean(data["contains_spoilers"], path=f"{path}.contains_spoilers"),
        priority=_integer(data["priority"], path=f"{path}.priority"),
    )


def encode_roleplay_package(package: RoleplayPackage) -> dict[str, object]:
    """Return the canonical JSON object stored in draft and revision snapshots."""

    value = json.loads(canonical_roleplay_json(package))
    if not isinstance(value, dict):  # pragma: no cover - canonical serializer invariant
        raise TypeError("canonical role-play package must serialize to an object")
    return value


def decode_roleplay_package(value: object) -> RoleplayPackage:
    """Decode one exact schema without coercing types or dropping unknown fields."""

    fields = (
        "schema_version",
        "name",
        "world",
        "character",
        "scene",
        "lore_entries",
        "example_replies",
    )
    data = _object(value, path="", fields=fields)
    lore = _items(data["lore_entries"], path="lore_entries")
    schema_version = _integer(data["schema_version"], path="schema_version")
    return RoleplayPackage(
        schema_version=schema_version,
        name=_string(data["name"], path="name"),
        world=_decode_world(data["world"]),
        character=_decode_character(data["character"], schema_version=schema_version),
        scene=_decode_scene(data["scene"]),
        lore_entries=tuple(_decode_lore(item, index) for index, item in enumerate(lore)),
        example_replies=_strings(data["example_replies"], path="example_replies"),
    )
