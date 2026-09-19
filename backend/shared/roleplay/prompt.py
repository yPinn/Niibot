"""Map compiled Role-play data into the existing assistant authority model."""

from __future__ import annotations

import json

from shared.assistant.contracts import InputSection, InputSectionKind
from shared.roleplay.compiler import compile_roleplay_package
from shared.roleplay.contracts import (
    CompiledRoleplay,
    RoleplayPackage,
    RoleplayRuntimeProfile,
)
from shared.roleplay.retrieval import resolve_lore


def build_roleplay_context_sections(
    compiled: CompiledRoleplay,
    package: RoleplayPackage,
    query: str,
    *,
    profile: RoleplayRuntimeProfile = RoleplayRuntimeProfile.COMPACT,
) -> tuple[InputSection, ...]:
    """Build only low-authority role and lore sections for one request."""

    expected = compile_roleplay_package(package)
    if compiled.schema_version != package.schema_version:
        raise ValueError("compiled role-play schema version does not match package")
    if compiled.compiler_version != expected.compiler_version:
        raise ValueError("compiled role-play compiler version does not match runtime")
    if compiled.content_digest != expected.content_digest:
        raise ValueError("compiled role-play digest does not match package")
    if compiled.capsule != expected.capsule:
        raise ValueError("compiled role-play capsule does not match package")
    if compiled.compact_capsule != expected.compact_capsule:
        raise ValueError("compiled role-play compact capsule does not match package")

    capsule = (
        compiled.compact_capsule if profile is RoleplayRuntimeProfile.COMPACT else compiled.capsule
    )
    lore_limits = (1, 600) if profile is RoleplayRuntimeProfile.COMPACT else (2, 1_500)

    sections: list[InputSection] = [
        InputSection(
            InputSectionKind.CHANNEL_PERSONA,
            json.dumps(
                {
                    "source": "roleplay_compiled_revision",
                    "schema_version": compiled.schema_version,
                    "compiler_version": compiled.compiler_version,
                    "content_digest": compiled.content_digest,
                    "profile": profile.value,
                    "performance_capsule": capsule,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    ]
    for entry in resolve_lore(
        package,
        query,
        max_entries=lore_limits[0],
        max_chars=lore_limits[1],
    ).entries:
        sections.append(
            InputSection(
                InputSectionKind.RETRIEVED_CONTEXT,
                json.dumps(
                    {
                        "source": "roleplay_lore",
                        "subject": entry.subject,
                        "content": entry.content,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        )
    return tuple(sections)
