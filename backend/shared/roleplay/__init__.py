"""Deterministic Canon Role-play authoring and runtime preparation."""

from shared.roleplay.compiler import (
    MAX_CAPSULE_CHARS,
    canonical_roleplay_json,
    compile_roleplay_package,
    roleplay_content_digest,
)
from shared.roleplay.contracts import (
    CanonMode,
    ChannelStage,
    CharacterKnowledge,
    CharacterSheet,
    CompiledRoleplay,
    LoreEntry,
    Relationship,
    RelationshipState,
    ResolvedLore,
    RoleplayPackage,
    Scene,
    SourceKind,
    SpoilerPolicy,
    ValidationIssue,
    WorldSnapshot,
)
from shared.roleplay.prompt import build_roleplay_context_sections
from shared.roleplay.retrieval import resolve_lore
from shared.roleplay.validation import (
    MAX_EXAMPLE_REPLIES,
    MAX_LORE_ENTRIES,
    SUPPORTED_SCHEMA_VERSION,
    RoleplayValidationError,
    assert_valid_roleplay_package,
    validate_roleplay_package,
)

__all__ = [
    "MAX_CAPSULE_CHARS",
    "MAX_EXAMPLE_REPLIES",
    "MAX_LORE_ENTRIES",
    "SUPPORTED_SCHEMA_VERSION",
    "CanonMode",
    "ChannelStage",
    "CharacterKnowledge",
    "CharacterSheet",
    "CompiledRoleplay",
    "LoreEntry",
    "Relationship",
    "RelationshipState",
    "ResolvedLore",
    "RoleplayPackage",
    "RoleplayValidationError",
    "Scene",
    "SourceKind",
    "SpoilerPolicy",
    "ValidationIssue",
    "WorldSnapshot",
    "assert_valid_roleplay_package",
    "build_roleplay_context_sections",
    "canonical_roleplay_json",
    "compile_roleplay_package",
    "resolve_lore",
    "roleplay_content_digest",
    "validate_roleplay_package",
]
