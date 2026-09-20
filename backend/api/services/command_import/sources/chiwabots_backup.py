"""Bounded, schema-independent access to user-supplied ChiwaBots backups.

ChiwaBots documents its backup as an archive, but does not publish the command
section's file schema.  This module deliberately stops at the archive security
boundary: it validates a ZIP in memory and exposes bounded reads without ever
extracting files to disk.  Schema parsing belongs in a later layer backed by a
real, sanitised export fixture.
"""

from __future__ import annotations

import math
import stat
import unicodedata
import zlib
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from pathlib import PureWindowsPath
from zipfile import (
    ZIP_DEFLATED,
    ZIP_STORED,
    BadZipFile,
    LargeZipFile,
    ZipFile,
    ZipInfo,
    is_zipfile,
)

_MIB = 1024 * 1024
_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_SUPPORTED_COMPRESSION = frozenset((ZIP_STORED, ZIP_DEFLATED))


class BackupErrorCode(StrEnum):
    """Stable reasons suitable for mapping to localized API errors."""

    EMPTY_UPLOAD = "empty_upload"
    UPLOAD_TOO_LARGE = "upload_too_large"
    NOT_ZIP = "not_zip"
    EMPTY_ARCHIVE = "empty_archive"
    TOO_MANY_ENTRIES = "too_many_entries"
    EXPANDED_TOO_LARGE = "expanded_too_large"
    SUSPICIOUS_COMPRESSION = "suspicious_compression"
    UNSAFE_PATH = "unsafe_path"
    DUPLICATE_PATH = "duplicate_path"
    UNSUPPORTED_ENTRY_TYPE = "unsupported_entry_type"
    ENCRYPTED_ENTRY = "encrypted_entry"
    UNSUPPORTED_COMPRESSION = "unsupported_compression"
    ENTRY_NOT_FOUND = "entry_not_found"
    ENTRY_TOO_LARGE = "entry_too_large"
    CORRUPT_ARCHIVE = "corrupt_archive"


_ERROR_MESSAGES: dict[BackupErrorCode, str] = {
    BackupErrorCode.EMPTY_UPLOAD: "The backup upload is empty.",
    BackupErrorCode.UPLOAD_TOO_LARGE: "The backup upload exceeds the size limit.",
    BackupErrorCode.NOT_ZIP: "The backup is not a valid ZIP archive.",
    BackupErrorCode.EMPTY_ARCHIVE: "The backup archive contains no files.",
    BackupErrorCode.TOO_MANY_ENTRIES: "The backup archive contains too many entries.",
    BackupErrorCode.EXPANDED_TOO_LARGE: "The expanded backup exceeds the size limit.",
    BackupErrorCode.SUSPICIOUS_COMPRESSION: (
        "The backup contains an entry with a suspicious compression ratio."
    ),
    BackupErrorCode.UNSAFE_PATH: "The backup contains an unsafe entry path.",
    BackupErrorCode.DUPLICATE_PATH: "The backup contains duplicate entry paths.",
    BackupErrorCode.UNSUPPORTED_ENTRY_TYPE: ("The backup contains an unsupported entry type."),
    BackupErrorCode.ENCRYPTED_ENTRY: "Encrypted backup entries are not supported.",
    BackupErrorCode.UNSUPPORTED_COMPRESSION: ("The backup uses an unsupported compression method."),
    BackupErrorCode.ENTRY_NOT_FOUND: "The requested backup entry was not found.",
    BackupErrorCode.ENTRY_TOO_LARGE: "The requested backup entry exceeds the read limit.",
    BackupErrorCode.CORRUPT_ARCHIVE: "The backup archive is corrupt.",
}


class ChiwaBotsBackupError(ValueError):
    """Safe archive validation error without raw ZIP exception details."""

    def __init__(self, code: BackupErrorCode) -> None:
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])


@dataclass(frozen=True, slots=True)
class BackupLimits:
    """Resource ceilings applied before any backup content is parsed."""

    max_upload_bytes: int = 5 * _MIB
    max_entries: int = 100
    max_expanded_bytes: int = 20 * _MIB
    max_compression_ratio: float = 50.0
    max_path_length: int = 1024

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_upload_bytes,
            self.max_entries,
            self.max_expanded_bytes,
            self.max_path_length,
        )
        if any(value <= 0 for value in integer_limits):
            raise ValueError("backup limits must be positive")
        if not math.isfinite(self.max_compression_ratio) or self.max_compression_ratio <= 0:
            raise ValueError("compression ratio limit must be finite and positive")


DEFAULT_BACKUP_LIMITS = BackupLimits()


@dataclass(frozen=True, slots=True)
class BackupEntry:
    """A validated regular file inside a backup."""

    name: str
    compressed_size: int
    uncompressed_size: int


@dataclass(frozen=True, slots=True)
class BackupManifest:
    """Immutable, content-free result of inspecting a backup archive."""

    files: tuple[BackupEntry, ...]
    total_uncompressed_size: int


def inspect_chiwabots_backup(
    data: bytes,
    *,
    limits: BackupLimits = DEFAULT_BACKUP_LIMITS,
) -> BackupManifest:
    """Validate *data* as a bounded ZIP and return its regular-file manifest."""
    _validate_upload(data, limits)
    try:
        with ZipFile(BytesIO(data), "r") as archive:
            return _inspect_infos(archive.infolist(), limits)
    except ChiwaBotsBackupError:
        raise
    except (BadZipFile, LargeZipFile, EOFError, OSError, ValueError) as exc:
        raise ChiwaBotsBackupError(BackupErrorCode.CORRUPT_ARCHIVE) from exc


def read_chiwabots_backup_entry(
    data: bytes,
    entry_name: str,
    *,
    max_bytes: int,
    limits: BackupLimits = DEFAULT_BACKUP_LIMITS,
) -> bytes:
    """Read one validated regular file without extraction or unbounded allocation."""
    if max_bytes < 0:
        raise ValueError("max_bytes cannot be negative")

    manifest = inspect_chiwabots_backup(data, limits=limits)
    requested_path = _normalize_path(entry_name, limits)
    requested_key = requested_path.casefold()
    matched_entry = next(
        (entry for entry in manifest.files if entry.name.casefold() == requested_key),
        None,
    )
    if matched_entry is None:
        raise ChiwaBotsBackupError(BackupErrorCode.ENTRY_NOT_FOUND)
    if matched_entry.uncompressed_size > max_bytes:
        raise ChiwaBotsBackupError(BackupErrorCode.ENTRY_TOO_LARGE)

    try:
        with ZipFile(BytesIO(data), "r") as archive:
            info = _find_info(archive.infolist(), requested_key, limits)
            with archive.open(info, "r") as source:
                content = source.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise ChiwaBotsBackupError(BackupErrorCode.ENTRY_TOO_LARGE)
            if len(content) != matched_entry.uncompressed_size:
                raise ChiwaBotsBackupError(BackupErrorCode.CORRUPT_ARCHIVE)
            return content
    except ChiwaBotsBackupError:
        raise
    except (
        BadZipFile,
        LargeZipFile,
        EOFError,
        NotImplementedError,
        OSError,
        RuntimeError,
        zlib.error,
    ) as exc:
        raise ChiwaBotsBackupError(BackupErrorCode.CORRUPT_ARCHIVE) from exc


def _validate_upload(data: bytes, limits: BackupLimits) -> None:
    if not data:
        raise ChiwaBotsBackupError(BackupErrorCode.EMPTY_UPLOAD)
    if len(data) > limits.max_upload_bytes:
        raise ChiwaBotsBackupError(BackupErrorCode.UPLOAD_TOO_LARGE)
    if not data.startswith(_ZIP_SIGNATURES) or not is_zipfile(BytesIO(data)):
        raise ChiwaBotsBackupError(BackupErrorCode.NOT_ZIP)


def _inspect_infos(infos: list[ZipInfo], limits: BackupLimits) -> BackupManifest:
    if not infos:
        raise ChiwaBotsBackupError(BackupErrorCode.EMPTY_ARCHIVE)
    if len(infos) > limits.max_entries:
        raise ChiwaBotsBackupError(BackupErrorCode.TOO_MANY_ENTRIES)

    seen_paths: set[str] = set()
    files: list[BackupEntry] = []
    total_uncompressed_size = 0

    for info in infos:
        normalized_path = _normalize_path(info.orig_filename, limits)
        path_key = normalized_path.casefold()
        if path_key in seen_paths:
            raise ChiwaBotsBackupError(BackupErrorCode.DUPLICATE_PATH)
        seen_paths.add(path_key)

        if info.flag_bits & 0x1:
            raise ChiwaBotsBackupError(BackupErrorCode.ENCRYPTED_ENTRY)
        if info.compress_type not in _SUPPORTED_COMPRESSION:
            raise ChiwaBotsBackupError(BackupErrorCode.UNSUPPORTED_COMPRESSION)
        _validate_entry_type(info)

        if info.is_dir():
            continue
        if info.file_size < 0 or info.compress_size < 0:
            raise ChiwaBotsBackupError(BackupErrorCode.CORRUPT_ARCHIVE)

        total_uncompressed_size += info.file_size
        if total_uncompressed_size > limits.max_expanded_bytes:
            raise ChiwaBotsBackupError(BackupErrorCode.EXPANDED_TOO_LARGE)
        if info.file_size:
            if info.compress_size == 0:
                raise ChiwaBotsBackupError(BackupErrorCode.SUSPICIOUS_COMPRESSION)
            ratio = info.file_size / info.compress_size
            if ratio > limits.max_compression_ratio:
                raise ChiwaBotsBackupError(BackupErrorCode.SUSPICIOUS_COMPRESSION)

        files.append(
            BackupEntry(
                name=normalized_path,
                compressed_size=info.compress_size,
                uncompressed_size=info.file_size,
            )
        )

    if not files:
        raise ChiwaBotsBackupError(BackupErrorCode.EMPTY_ARCHIVE)
    return BackupManifest(
        files=tuple(files),
        total_uncompressed_size=total_uncompressed_size,
    )


def _normalize_path(name: str, limits: BackupLimits) -> str:
    if not name or "\x00" in name or len(name) > limits.max_path_length:
        raise ChiwaBotsBackupError(BackupErrorCode.UNSAFE_PATH)

    windows_path = PureWindowsPath(name)
    path = name.replace("\\", "/")
    if windows_path.drive or path.startswith("/"):
        raise ChiwaBotsBackupError(BackupErrorCode.UNSAFE_PATH)

    raw_parts = path.split("/")
    if ".." in raw_parts:
        raise ChiwaBotsBackupError(BackupErrorCode.UNSAFE_PATH)
    parts = [part for part in raw_parts if part not in ("", ".")]
    if not parts:
        raise ChiwaBotsBackupError(BackupErrorCode.UNSAFE_PATH)

    normalized = unicodedata.normalize("NFC", "/".join(parts))
    if len(normalized) > limits.max_path_length:
        raise ChiwaBotsBackupError(BackupErrorCode.UNSAFE_PATH)
    return normalized


def _validate_entry_type(info: ZipInfo) -> None:
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(unix_mode)
    expected_type = stat.S_IFDIR if info.is_dir() else stat.S_IFREG
    if file_type not in (0, expected_type):
        raise ChiwaBotsBackupError(BackupErrorCode.UNSUPPORTED_ENTRY_TYPE)


def _find_info(infos: list[ZipInfo], requested_key: str, limits: BackupLimits) -> ZipInfo:
    for info in infos:
        if info.is_dir():
            continue
        if _normalize_path(info.orig_filename, limits).casefold() == requested_key:
            return info
    raise ChiwaBotsBackupError(BackupErrorCode.ENTRY_NOT_FOUND)
