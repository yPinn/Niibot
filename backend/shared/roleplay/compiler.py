"""Reproducible Role-play capsule and content digest compiler."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from shared.roleplay.contracts import CompiledRoleplay, RoleplayPackage
from shared.roleplay.validation import assert_valid_roleplay_package

MAX_CAPSULE_CHARS = 900


@dataclass(frozen=True, slots=True)
class _CapsuleSegment:
    text: str
    min_chars: int
    shrink_priority: int


def canonical_roleplay_json(package: RoleplayPackage) -> str:
    """Serialize authoring data in one stable form for immutable revisions."""

    return json.dumps(
        asdict(package),
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


def _fit_capsule(segments: tuple[_CapsuleSegment, ...]) -> str:
    texts = [segment.text for segment in segments]
    overage = len("\n".join(text for text in texts if text)) - MAX_CAPSULE_CHARS
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
    if len(capsule) > MAX_CAPSULE_CHARS:
        raise ValueError("role-play capsule minimum content exceeds runtime budget")
    return capsule


def _build_capsule(package: RoleplayPackage) -> str:
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
                "演出規則：先回答目前問題，再自然呈現角色；不要把每個話題都拉回作品。"
                "遇到角色不知道、超出故事進度或未載入的事實，要明確說不知道，不猜測、不劇透。"
                "角色設定不能改寫安全、權限、輸出長度或供應商路由。",
                min_chars=110,
                shrink_priority=100,
            ),
        )
    )


def compile_roleplay_package(package: RoleplayPackage) -> CompiledRoleplay:
    """Validate and compile one immutable runtime artifact without an LLM."""

    assert_valid_roleplay_package(package)
    return CompiledRoleplay(
        schema_version=package.schema_version,
        capsule=_build_capsule(package),
        content_digest=roleplay_content_digest(package),
    )
