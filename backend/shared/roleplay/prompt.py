"""Map compiled Role-play data into the existing assistant authority model."""

from __future__ import annotations

import json

from shared.assistant.contracts import InputSection, InputSectionKind
from shared.roleplay.compiler import compile_roleplay_package
from shared.roleplay.contracts import CompiledRoleplay, RoleplayPackage
from shared.roleplay.retrieval import resolve_lore


def build_roleplay_context_sections(
    compiled: CompiledRoleplay,
    package: RoleplayPackage,
    query: str,
) -> tuple[InputSection, ...]:
    """Build only low-authority role and lore sections for one request."""

    expected = compile_roleplay_package(package)
    if compiled.schema_version != package.schema_version:
        raise ValueError("compiled role-play schema version does not match package")
    if compiled.content_digest != expected.content_digest:
        raise ValueError("compiled role-play digest does not match package")
    if compiled.capsule != expected.capsule:
        raise ValueError("compiled role-play capsule does not match package")

    sections: list[InputSection] = [
        InputSection(
            InputSectionKind.CHANNEL_PERSONA,
            json.dumps(
                {
                    "source": "roleplay_compiled_revision",
                    "schema_version": compiled.schema_version,
                    "content_digest": compiled.content_digest,
                    "performance_capsule": compiled.capsule,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    ]
    for entry in resolve_lore(package, query).entries:
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
