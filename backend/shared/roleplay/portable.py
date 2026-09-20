"""Strict, provider-neutral private-file format for Role-play revisions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Never

from shared.roleplay.codec import (
    RoleplayDocumentError,
    decode_roleplay_package,
    encode_roleplay_package,
)
from shared.roleplay.compiler import ROLEPLAY_COMPILER_VERSION, compile_roleplay_package
from shared.roleplay.contracts import CompiledRoleplay, RoleplayPackage, ValidationIssue
from shared.roleplay.validation import SUPPORTED_SCHEMA_VERSION, RoleplayValidationError

PORTABLE_ROLEPLAY_FORMAT = "niibot.roleplay-character"
PORTABLE_ROLEPLAY_FORMAT_VERSION = 1
MAX_PORTABLE_ROLEPLAY_BYTES = 128 * 1024

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class PortableRoleplayCharacter:
    """Validated portable content with all derived data recomputed locally."""

    display_name: str
    package: RoleplayPackage
    compiled: CompiledRoleplay
    exported_at: datetime


class RoleplayPortableError(ValueError):
    """Raised when a private export cannot be safely imported."""

    def __init__(self, issue: ValidationIssue) -> None:
        self.issue = issue
        super().__init__(issue.code)


def _fail(code: str, path: str, message: str) -> Never:
    raise RoleplayPortableError(ValidationIssue(code=code, path=path, message=message))


def _object(value: object, *, path: str, fields: tuple[str, ...]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail("portable.type.object", path, "設定集格式不正確")
    for field in fields:
        if field not in value:
            field_path = f"{path}.{field}" if path else field
            _fail("portable.field.missing", field_path, "設定集缺少必要內容")
    unknown = sorted(str(key) for key in value if not isinstance(key, str) or key not in fields)
    if unknown:
        field_path = f"{path}.{unknown[0]}" if path else unknown[0]
        _fail("portable.field.unknown", field_path, "設定集包含不支援的內容")
    return value


def _string(value: object, *, path: str) -> str:
    if not isinstance(value, str):
        _fail("portable.type.string", path, "設定集格式不正確")
    return value


def _integer(value: object, *, path: str) -> int:
    if type(value) is not int:
        _fail("portable.type.integer", path, "設定集格式不正確")
    return value


def _display_name(value: object) -> str:
    name = _string(value, path="manifest.name").strip()
    if not 1 <= len(name) <= 100:
        _fail("portable.name.invalid", "manifest.name", "角色設定名稱必須介於 1 到 100 字")
    return name


def _exported_at(value: object) -> datetime:
    raw = _string(value, path="manifest.exported_at")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        _fail("portable.exported_at.invalid", "manifest.exported_at", "匯出時間格式不正確")
    if parsed.tzinfo is None:
        _fail("portable.exported_at.invalid", "manifest.exported_at", "匯出時間格式不正確")
    return parsed.astimezone(UTC)


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("exported_at must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_roleplay_character_export(
    *,
    display_name: str,
    package: RoleplayPackage,
    compiled: CompiledRoleplay,
    exported_at: datetime,
) -> dict[str, object]:
    """Build one exact export from a verified immutable revision."""

    name = _display_name(display_name)
    expected = compile_roleplay_package(package)
    if compiled != expected:
        _fail(
            "portable.revision.inconsistent",
            "compiled_preview",
            "角色設定版本無法驗證，請重新完成設定後再試",
        )
    return {
        "format": PORTABLE_ROLEPLAY_FORMAT,
        "format_version": PORTABLE_ROLEPLAY_FORMAT_VERSION,
        "manifest": {
            "name": name,
            "exported_at": _isoformat(exported_at),
            "schema_version": compiled.schema_version,
            "compiler_version": compiled.compiler_version,
            "content_digest": compiled.content_digest,
        },
        "package": encode_roleplay_package(package),
        "compiled_preview": {
            "capsule": compiled.capsule,
            "compact_capsule": compiled.compact_capsule,
        },
    }


def decode_roleplay_character_export(value: object) -> PortableRoleplayCharacter:
    """Validate one private export without trusting any derived prompt text."""

    document = _object(
        value,
        path="",
        fields=("format", "format_version", "manifest", "package", "compiled_preview"),
    )
    if _string(document["format"], path="format") != PORTABLE_ROLEPLAY_FORMAT:
        _fail("portable.format.unsupported", "format", "這不是支援的 Niibot 角色設定集")
    if (
        _integer(document["format_version"], path="format_version")
        != PORTABLE_ROLEPLAY_FORMAT_VERSION
    ):
        _fail(
            "portable.format_version.unsupported",
            "format_version",
            "這份角色設定集版本目前不支援",
        )

    manifest = _object(
        document["manifest"],
        path="manifest",
        fields=(
            "name",
            "exported_at",
            "schema_version",
            "compiler_version",
            "content_digest",
        ),
    )
    display_name = _display_name(manifest["name"])
    exported_at = _exported_at(manifest["exported_at"])
    schema_version = _integer(manifest["schema_version"], path="manifest.schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        _fail(
            "portable.schema_version.unsupported",
            "manifest.schema_version",
            "這份角色內容版本目前不支援",
        )
    compiler_version = _integer(manifest["compiler_version"], path="manifest.compiler_version")
    if compiler_version != ROLEPLAY_COMPILER_VERSION:
        _fail(
            "portable.compiler_version.unsupported",
            "manifest.compiler_version",
            "這份角色設定需要其他版本，無法直接匯入",
        )
    digest = _string(manifest["content_digest"], path="manifest.content_digest")
    if not _DIGEST_RE.fullmatch(digest):
        _fail("portable.digest.invalid", "manifest.content_digest", "角色設定驗證碼格式不正確")

    try:
        package = decode_roleplay_package(document["package"])
        compiled = compile_roleplay_package(package)
    except RoleplayDocumentError as error:
        issue = error.issues[0]
        path = f"package.{issue.path}" if issue.path else "package"
        _fail("portable.package.invalid", path, issue.message)
    except RoleplayValidationError as error:
        issue = error.issues[0]
        _fail("portable.package.invalid", issue.path, issue.message)

    if package.schema_version != schema_version or compiled.schema_version != schema_version:
        _fail(
            "portable.schema_version.mismatch",
            "manifest.schema_version",
            "角色設定內容版本不一致",
        )
    if compiled.compiler_version != compiler_version:
        _fail(
            "portable.compiler_version.mismatch",
            "manifest.compiler_version",
            "角色設定編譯版本不一致",
        )
    if compiled.content_digest != digest:
        _fail("portable.digest.mismatch", "manifest.content_digest", "角色設定內容驗證失敗")

    preview = _object(
        document["compiled_preview"],
        path="compiled_preview",
        fields=("capsule", "compact_capsule"),
    )
    capsule = _string(preview["capsule"], path="compiled_preview.capsule")
    compact_capsule = _string(preview["compact_capsule"], path="compiled_preview.compact_capsule")
    if capsule != compiled.capsule or compact_capsule != compiled.compact_capsule:
        _fail(
            "portable.preview.mismatch",
            "compiled_preview",
            "角色設定摘要驗證失敗",
        )

    return PortableRoleplayCharacter(
        display_name=display_name,
        package=package,
        compiled=compiled,
        exported_at=exported_at,
    )
