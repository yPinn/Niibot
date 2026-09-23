"""Immutable, provider-neutral contracts for Canon Role-play content."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SourceKind(StrEnum):
    """Origin of a role-play world."""

    ORIGINAL = "original"
    EXISTING_WORK = "existing_work"


class CanonMode(StrEnum):
    """Relationship between a package and its declared source."""

    ORIGINAL = "original"
    CANON = "canon"
    ALTERNATE_UNIVERSE = "alternate_universe"


class SpoilerPolicy(StrEnum):
    """Whether known, in-scope lore marked as a spoiler may be retrieved."""

    FORBID = "forbid"
    ALLOW_WITHIN_SCOPE = "allow_within_scope"


class ChannelStage(StrEnum):
    """How chat participants enter the role-play scene."""

    IN_WORLD_VISITORS = "in_world_visitors"
    CHAT_ADAPTED = "chat_adapted"
    CROSS_WORLD = "cross_world"


class RelationshipState(StrEnum):
    """One current trust stance toward a named subject."""

    UNFAMILIAR = "unfamiliar"
    GUARDED = "guarded"
    FAMILIAR = "familiar"
    TRUSTED = "trusted"
    HOSTILE = "hostile"
    INTIMATE = "intimate"


class RoleplayRuntimeProfile(StrEnum):
    """Compiled context shape selected for a runtime or evaluation path."""

    COMPACT = "compact"
    FULL = "full"


class SignaturePhraseMode(StrEnum):
    """Whether a short signature phrase may be quoted or should be adapted."""

    EXACT = "exact"
    ADAPTED = "adapted"


@dataclass(frozen=True, slots=True)
class WorldSnapshot:
    """Versioned world, canon scope, and timeline state used by a character."""

    title: str
    source_kind: SourceKind
    canon_mode: CanonMode
    canon_scope: str
    world_anchor: str
    story_stage: str
    spoiler_policy: SpoilerPolicy


@dataclass(frozen=True, slots=True)
class Relationship:
    """A character's current relationship with one canonical subject."""

    subject: str
    role: str
    state: RelationshipState
    notes: str = ""


@dataclass(frozen=True, slots=True)
class CharacterKnowledge:
    """Facts explicitly known and unknown at the selected story stage."""

    known: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SignaturePhrase:
    """One short, contextual phrase that may occasionally color a reply."""

    text: str
    use_when: str
    mode: SignaturePhraseMode


@dataclass(frozen=True, slots=True)
class CharacterSheet:
    """Stable character core interpreted within one world snapshot."""

    name: str
    role: str
    motivation: str
    stable_traits: tuple[str, ...]
    boundaries: tuple[str, ...]
    voice: str
    relationships: tuple[Relationship, ...]
    knowledge: CharacterKnowledge
    signature_phrases: tuple[SignaturePhrase, ...] = ()


@dataclass(frozen=True, slots=True)
class Scene:
    """Current situation plus the explicit bridge into a chat platform."""

    location: str
    current_activity: str
    current_goal: str
    emotional_baseline: str
    channel_stage: ChannelStage
    host_relationship: str
    audience_relationship: str
    adaptation_note: str = ""
    host_character_mapping: str | None = None
    audience_character_mapping: str | None = None


@dataclass(frozen=True, slots=True)
class LoreEntry:
    """One bounded fact that is retrieved only when a query matches."""

    subject: str
    aliases: tuple[str, ...]
    content: str
    known_at_stage: bool
    contains_spoilers: bool
    priority: int = 0


@dataclass(frozen=True, slots=True)
class RoleplayPackage:
    """Complete authoring snapshot for one playable character revision."""

    schema_version: int
    name: str
    world: WorldSnapshot
    character: CharacterSheet
    scene: Scene
    lore_entries: tuple[LoreEntry, ...] = ()
    example_replies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """Stable validation result suitable for a future API field mapping."""

    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class CompiledRoleplay:
    """Reproducible runtime artifact stored with an immutable revision."""

    schema_version: int
    compiler_version: int
    capsule: str
    compact_capsule: str
    content_digest: str


@dataclass(frozen=True, slots=True)
class ResolvedLore:
    """Complete eligible lore entries selected within request-time budgets."""

    entries: tuple[LoreEntry, ...]
    total_chars: int
