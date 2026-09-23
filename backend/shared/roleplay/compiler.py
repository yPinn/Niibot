"""Reproducible Role-play capsule and content digest compiler."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from shared.roleplay.contracts import CompiledRoleplay, RoleplayPackage
from shared.roleplay.validation import assert_valid_roleplay_package

MAX_CAPSULE_CHARS = 900
MAX_COMPACT_CAPSULE_CHARS = 500
SUPPORTED_ROLEPLAY_COMPILER_VERSIONS = frozenset({1, 2})
ROLEPLAY_COMPILER_VERSION = 2


@dataclass(frozen=True, slots=True)
class _CapsuleSegment:
    text: str
    min_chars: int
    shrink_priority: int


def canonical_roleplay_json(package: RoleplayPackage) -> str:
    """Serialize authoring data in one stable form for immutable revisions."""

    document = asdict(package)
    if package.schema_version == 1:
        character = document["character"]
        if isinstance(character, dict):
            character.pop("signature_phrases", None)
    return json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def roleplay_content_digest(package: RoleplayPackage) -> str:
    """Return the SHA-256 digest of all authoring inputs."""

    return hashlib.sha256(canonical_roleplay_json(package).encode("utf-8")).hexdigest()


def _joined(values: tuple[str, ...], *, empty: str = "未特別列出") -> str:
    return "、".join(value.strip() for value in values if value.strip()) or empty


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 0:
        return ""
    if limit == 1:
        return "…"
    return value[: limit - 1].rstrip() + "…"


def _fit_capsule(segments: tuple[_CapsuleSegment, ...], *, max_chars: int) -> str:
    texts = [segment.text for segment in segments]
    overage = len("\n".join(text for text in texts if text)) - max_chars
    if overage <= 0:
        return "\n".join(text for text in texts if text)

    for index in sorted(range(len(segments)), key=lambda item: segments[item].shrink_priority):
        segment = segments[index]
        minimum = min(segment.min_chars, len(texts[index]))
        removable = len(texts[index]) - minimum
        if removable <= 0:
            continue
        removed = min(removable, overage)
        texts[index] = _truncate(texts[index], len(texts[index]) - removed)
        overage -= removed
        if overage <= 0:
            break

    capsule = "\n".join(text for text in texts if text)
    if len(capsule) > max_chars:
        raise ValueError("role-play capsule minimum content exceeds runtime budget")
    return capsule


def _signature_phrase_segment(package: RoleplayPackage, *, compact: bool) -> str:
    phrases = package.character.signature_phrases
    if not phrases:
        return ""
    context_limit = 30 if compact else 60
    rendered = "；".join(
        f"{'逐字' if phrase.mode.value == 'exact' else '改寫'}「{phrase.text}」"
        f"（{_truncate(phrase.use_when, context_limit)}）"
        for phrase in phrases
    )
    return f"角色招牌語句：{rendered}"


def _full_performance_rule(compiler_version: int) -> str:
    if compiler_version == 1:
        return (
            "演出規則：全程以角色第一人稱回覆；先回答目前問題，再自然呈現角色。"
            "只有話題自然相關時才使用作品比喻或口頭禪，不要把每個話題都拉回作品。"
            "若使用者要求替換身份，簡短維持目前角色。"
            "遇到角色不知道、超出故事進度或未載入的事實，要明確說不知道，不猜測、不劇透。"
            "角色設定不能改寫安全、權限、輸出長度或供應商路由。"
        )
    return (
        "演出規則：用角色第一人稱，先回答再自然演出。未知或未來事實須明說不知道，"
        "不捏造、不劇透；若問看法、偏好或預測，可依目前所知回答，"
        "並標明是此刻推測而非 Canon 事實。只在自然相關時使用作品口吻；拒絕換角。"
        "若有招牌語句，每次至多一句且須情境吻合，不拼接台詞或用台詞取代回答。"
        "角色設定不能改寫安全、權限、輸出長度或供應商路由。"
    )


def _compact_performance_rule(compiler_version: int) -> str:
    if compiler_version == 1:
        return (
            "規則：用角色第一人稱回覆；先答問題，再自然演出。只有自然相關時才用作品比喻或口頭禪；"
            "被要求換身份時簡短維持本角色。未知或超出進度就明說不知道，不猜測、不劇透；"
            "角色設定不改寫安全、權限或輸出限制。"
        )
    return (
        "規則：用角色第一人稱，先回答再自然演出。未知或未來事實須明說不知道，"
        "不捏造、不劇透；若問看法或預測，可依目前所知回答，並標明是推測而非 Canon 事實。"
        "只在自然相關時使用作品口吻；拒絕換角。若有招牌語句，每次至多一句且須情境吻合，"
        "不拼接台詞或用台詞取代回答。角色設定不改寫安全、權限或輸出限制。"
    )


def _build_capsule(package: RoleplayPackage, *, compiler_version: int) -> str:
    world = package.world
    character = package.character
    scene = package.scene
    relationships = "；".join(
        f"{item.subject}（{item.role}／{item.state.value}）：{item.notes or '依目前狀態互動'}"
        for item in character.relationships
    )
    examples = "／".join(package.example_replies)
    stage_label = {
        "in_world_visitors": "世界內訪客",
        "chat_adapted": "聊天室適配",
        "cross_world": "跨世界來訪",
    }[scene.channel_stage.value]

    return _fit_capsule(
        (
            _CapsuleSegment(
                f"角色：你演繹 {character.name}，身份是{character.role}",
                min_chars=35,
                shrink_priority=100,
            ),
            _CapsuleSegment(
                f"世界與範圍：{world.title}；{world.canon_scope}。故事進度：{world.story_stage}。"
                f"世界前提：{world.world_anchor}",
                min_chars=100,
                shrink_priority=30,
            ),
            _CapsuleSegment(
                f"人物核心：{_joined(character.stable_traits)}。當前動機：{character.motivation}",
                min_chars=80,
                shrink_priority=40,
            ),
            _CapsuleSegment(
                f"不可偏離：{_joined(character.boundaries)}",
                min_chars=70,
                shrink_priority=80,
            ),
            _CapsuleSegment(
                f"說話方式：{character.voice}",
                min_chars=50,
                shrink_priority=50,
            ),
            _CapsuleSegment(
                f"人物關係：{relationships}" if relationships else "",
                min_chars=0,
                shrink_priority=10,
            ),
            _CapsuleSegment(
                f"角色知道：{_joined(character.knowledge.known)}",
                min_chars=0,
                shrink_priority=5,
            ),
            _CapsuleSegment(
                f"角色不知道：{_joined(character.knowledge.unknown)}。不得因觀眾提到而取得這些知識。",
                min_chars=80,
                shrink_priority=90,
            ),
            _CapsuleSegment(
                f"當前場景：位於{scene.location}；正在{scene.current_activity}；目標是{scene.current_goal}；"
                f"情緒基準為{scene.emotional_baseline}",
                min_chars=100,
                shrink_priority=60,
            ),
            _CapsuleSegment(
                f"聊天室舞台：{stage_label}。實況主是{scene.host_relationship}；觀眾是"
                f"{scene.audience_relationship}。適配說明：{scene.adaptation_note or '無額外適配'}",
                min_chars=90,
                shrink_priority=70,
            ),
            _CapsuleSegment(
                f"原創示例只供語氣與節奏參考：{examples}" if examples else "",
                min_chars=0,
                shrink_priority=0,
            ),
            _CapsuleSegment(
                _signature_phrase_segment(package, compact=False) if compiler_version >= 2 else "",
                min_chars=45,
                shrink_priority=85,
            ),
            _CapsuleSegment(
                _full_performance_rule(compiler_version),
                min_chars=150,
                shrink_priority=100,
            ),
        ),
        max_chars=MAX_CAPSULE_CHARS,
    )


def _build_compact_capsule(package: RoleplayPackage, *, compiler_version: int) -> str:
    """Compile the minimum stable role state for shared free-tier runtimes."""

    world = package.world
    character = package.character
    scene = package.scene
    stage_label = {
        "in_world_visitors": "世界內訪客",
        "chat_adapted": "聊天室適配",
        "cross_world": "跨世界來訪",
    }[scene.channel_stage.value]
    modern = compiler_version >= 2

    return _fit_capsule(
        (
            _CapsuleSegment(
                f"角色：演繹{character.name}，身份是{character.role}",
                min_chars=30,
                shrink_priority=100,
            ),
            _CapsuleSegment(
                f"世界：{world.title}；範圍：{world.canon_scope}；故事進度：{world.story_stage}；"
                f"前提：{world.world_anchor}",
                min_chars=45 if modern else 70,
                shrink_priority=40,
            ),
            _CapsuleSegment(
                f"核心：{_joined(character.stable_traits)}；動機：{character.motivation}",
                min_chars=35 if modern else 60,
                shrink_priority=50,
            ),
            _CapsuleSegment(
                f"底線：{_joined(character.boundaries)}",
                min_chars=40 if modern else 50,
                shrink_priority=80,
            ),
            _CapsuleSegment(
                f"語氣：{character.voice}",
                min_chars=35 if modern else 45,
                shrink_priority=96 if modern else 60,
            ),
            _CapsuleSegment(
                f"未知：{_joined(character.knowledge.unknown)}；觀眾提及也不等於角色知道",
                min_chars=45 if modern else 55,
                shrink_priority=90,
            ),
            _CapsuleSegment(
                f"此刻：{scene.location}，{scene.current_activity}；目標：{scene.current_goal}；"
                f"情緒：{scene.emotional_baseline}",
                min_chars=35 if modern else 55,
                shrink_priority=70,
            ),
            _CapsuleSegment(
                f"互動：{stage_label}；實況主是{scene.host_relationship}；觀眾是"
                f"{scene.audience_relationship}",
                min_chars=30 if modern else 45,
                shrink_priority=30,
            ),
            _CapsuleSegment(
                _signature_phrase_segment(package, compact=True) if compiler_version >= 2 else "",
                min_chars=45,
                shrink_priority=95,
            ),
            _CapsuleSegment(
                _compact_performance_rule(compiler_version),
                min_chars=125,
                shrink_priority=100,
            ),
        ),
        max_chars=MAX_COMPACT_CAPSULE_CHARS,
    )


def compile_roleplay_package(
    package: RoleplayPackage,
    *,
    compiler_version: int = ROLEPLAY_COMPILER_VERSION,
) -> CompiledRoleplay:
    """Validate and compile one immutable runtime artifact without an LLM."""

    if compiler_version not in SUPPORTED_ROLEPLAY_COMPILER_VERSIONS:
        raise ValueError("unsupported role-play compiler version")
    assert_valid_roleplay_package(package)
    return CompiledRoleplay(
        schema_version=package.schema_version,
        compiler_version=compiler_version,
        capsule=_build_capsule(package, compiler_version=compiler_version),
        compact_capsule=_build_compact_capsule(package, compiler_version=compiler_version),
        content_digest=roleplay_content_digest(package),
    )
