"""Deterministic compatibility and content limits for Role-play packages."""

from __future__ import annotations

from collections.abc import Iterable

from shared.roleplay.contracts import (
    CanonMode,
    ChannelStage,
    RoleplayPackage,
    SourceKind,
    ValidationIssue,
)
from shared.roleplay.normalization import normalize_roleplay_text

SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})
SUPPORTED_SCHEMA_VERSION = 2
MAX_LORE_ENTRIES = 30
MAX_EXAMPLE_REPLIES = 3
MAX_SIGNATURE_PHRASES = 3


class RoleplayValidationError(ValueError):
    """Raised when an authoring package cannot become a published revision."""

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__(", ".join(issue.code for issue in issues))


def _issue(code: str, path: str, message: str) -> ValidationIssue:
    return ValidationIssue(code=code, path=path, message=message)


def _validate_text(
    issues: list[ValidationIssue],
    value: str,
    *,
    path: str,
    max_chars: int,
    required: bool = True,
) -> None:
    if required and not value.strip():
        issues.append(_issue(f"{path}.blank", path, "此欄位不能為空"))
        return
    if len(value) > max_chars:
        issues.append(
            _issue(
                f"{path}.too_long",
                path,
                f"此欄位最多 {max_chars} 字",
            )
        )


def _validate_text_items(
    issues: list[ValidationIssue],
    items: Iterable[str],
    *,
    path: str,
    max_items: int,
    max_chars: int,
    min_items: int = 0,
) -> None:
    values = tuple(items)
    if len(values) < min_items:
        issues.append(_issue(f"{path}.too_few", path, f"至少需要 {min_items} 項"))
    if len(values) > max_items:
        issues.append(_issue(f"{path}.too_many", path, f"最多只能有 {max_items} 項"))
    for index, value in enumerate(values):
        _validate_text(
            issues,
            value,
            path=f"{path}.{index}",
            max_chars=max_chars,
        )


def validate_roleplay_package(package: RoleplayPackage) -> tuple[ValidationIssue, ...]:
    """Return every deterministic validation issue in stable traversal order."""

    issues: list[ValidationIssue] = []
    if package.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        issues.append(
            _issue(
                "package.schema_version.unsupported",
                "package.schema_version",
                "不支援的角色設定集版本",
            )
        )
    _validate_text(issues, package.name, path="package.name", max_chars=80)

    world = package.world
    _validate_text(issues, world.title, path="world.title", max_chars=100)
    _validate_text(issues, world.canon_scope, path="world.canon_scope", max_chars=500)
    _validate_text(issues, world.world_anchor, path="world.world_anchor", max_chars=1_200)
    _validate_text(issues, world.story_stage, path="world.story_stage", max_chars=500)
    source_and_mode_match = (
        world.source_kind is SourceKind.ORIGINAL and world.canon_mode is CanonMode.ORIGINAL
    ) or (
        world.source_kind is SourceKind.EXISTING_WORK
        and world.canon_mode in {CanonMode.CANON, CanonMode.ALTERNATE_UNIVERSE}
    )
    if not source_and_mode_match:
        issues.append(
            _issue(
                "world.source_mode.incompatible",
                "world.canon_mode",
                "作品來源與 Canon 模式不相容",
            )
        )

    character = package.character
    _validate_text(issues, character.name, path="character.name", max_chars=80)
    _validate_text(issues, character.role, path="character.role", max_chars=500)
    _validate_text(issues, character.motivation, path="character.motivation", max_chars=500)
    _validate_text_items(
        issues,
        character.stable_traits,
        path="character.stable_traits",
        min_items=1,
        max_items=8,
        max_chars=120,
    )
    _validate_text_items(
        issues,
        character.boundaries,
        path="character.boundaries",
        min_items=1,
        max_items=10,
        max_chars=200,
    )
    _validate_text(issues, character.voice, path="character.voice", max_chars=800)
    if package.schema_version == 1 and character.signature_phrases:
        issues.append(
            _issue(
                "character.signature_phrases.unsupported",
                "character.signature_phrases",
                "舊版角色設定不支援招牌語句，請先升級設定集",
            )
        )
    if len(character.signature_phrases) > MAX_SIGNATURE_PHRASES:
        issues.append(
            _issue(
                "character.signature_phrases.too_many",
                "character.signature_phrases",
                f"角色招牌語句最多 {MAX_SIGNATURE_PHRASES} 句",
            )
        )
    for index, phrase in enumerate(character.signature_phrases):
        path = f"character.signature_phrases.{index}"
        _validate_text(issues, phrase.text, path=f"{path}.text", max_chars=40)
        _validate_text(issues, phrase.use_when, path=f"{path}.use_when", max_chars=100)

    if len(character.relationships) > 20:
        issues.append(
            _issue(
                "character.relationships.too_many",
                "character.relationships",
                "人物關係最多 20 項",
            )
        )
    relationship_states: dict[str, object] = {}
    for index, relationship in enumerate(character.relationships):
        path = f"character.relationships.{index}"
        _validate_text(issues, relationship.subject, path=f"{path}.subject", max_chars=80)
        _validate_text(issues, relationship.role, path=f"{path}.role", max_chars=160)
        _validate_text(
            issues,
            relationship.notes,
            path=f"{path}.notes",
            max_chars=400,
            required=False,
        )
        subject_key = normalize_roleplay_text(relationship.subject)
        existing_state = relationship_states.get(subject_key)
        if subject_key and existing_state is not None and existing_state != relationship.state:
            issues.append(
                _issue(
                    "character.relationships.conflict",
                    path,
                    "同一人物不能同時有互相衝突的關係狀態",
                )
            )
        relationship_states.setdefault(subject_key, relationship.state)

    knowledge = character.knowledge
    _validate_text_items(
        issues,
        knowledge.known,
        path="character.knowledge.known",
        max_items=30,
        max_chars=300,
    )
    _validate_text_items(
        issues,
        knowledge.unknown,
        path="character.knowledge.unknown",
        max_items=30,
        max_chars=300,
    )
    known = {normalize_roleplay_text(item) for item in knowledge.known if item.strip()}
    unknown = {normalize_roleplay_text(item) for item in knowledge.unknown if item.strip()}
    if known & unknown:
        issues.append(
            _issue(
                "character.knowledge.conflict",
                "character.knowledge",
                "同一件事不能同時標記為知道與不知道",
            )
        )

    scene = package.scene
    for field_name, value in (
        ("location", scene.location),
        ("current_activity", scene.current_activity),
        ("current_goal", scene.current_goal),
        ("emotional_baseline", scene.emotional_baseline),
        ("host_relationship", scene.host_relationship),
        ("audience_relationship", scene.audience_relationship),
    ):
        _validate_text(issues, value, path=f"scene.{field_name}", max_chars=500)
    if (
        scene.channel_stage is not ChannelStage.IN_WORLD_VISITORS
        and not scene.adaptation_note.strip()
    ):
        issues.append(
            _issue(
                "scene.adaptation_note.required",
                "scene.adaptation_note",
                "非世界內舞台必須說明如何適配聊天室",
            )
        )
    _validate_text(
        issues,
        scene.adaptation_note,
        path="scene.adaptation_note",
        max_chars=800,
        required=False,
    )
    if scene.audience_character_mapping is not None:
        issues.append(
            _issue(
                "scene.audience_mapping.forbidden",
                "scene.audience_character_mapping",
                "不能把所有聊天室觀眾映射成原作人物",
            )
        )
    if (
        scene.channel_stage is ChannelStage.CHAT_ADAPTED
        and scene.host_character_mapping is not None
    ):
        issues.append(
            _issue(
                "scene.host_mapping.incompatible",
                "scene.host_character_mapping",
                "聊天室適配模式不會把實況主映射成原作人物",
            )
        )

    if len(package.lore_entries) > MAX_LORE_ENTRIES:
        issues.append(
            _issue(
                "package.lore_entries.too_many",
                "package.lore_entries",
                f"背景條目最多 {MAX_LORE_ENTRIES} 項",
            )
        )
    for index, entry in enumerate(package.lore_entries):
        path = f"package.lore_entries.{index}"
        _validate_text(issues, entry.subject, path=f"{path}.subject", max_chars=80)
        _validate_text_items(
            issues,
            entry.aliases,
            path=f"{path}.aliases",
            max_items=8,
            max_chars=50,
        )
        _validate_text(issues, entry.content, path=f"{path}.content", max_chars=800)
        if not 0 <= entry.priority <= 100:
            issues.append(
                _issue(
                    "package.lore_entries.priority.out_of_range",
                    f"{path}.priority",
                    "背景條目優先度必須介於 0 與 100",
                )
            )

    _validate_text_items(
        issues,
        package.example_replies,
        path="package.examples",
        max_items=MAX_EXAMPLE_REPLIES,
        max_chars=120,
    )
    return tuple(issues)


def assert_valid_roleplay_package(package: RoleplayPackage) -> None:
    """Raise a stable aggregate error when a package cannot be compiled."""

    issues = validate_roleplay_package(package)
    if issues:
        raise RoleplayValidationError(issues)
