"""Security boundary tests for user-supplied ChiwaBots backup archives."""

from __future__ import annotations

import stat
from io import BytesIO
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

import pytest

from services.command_import.sources.chiwabots_backup import (
    DEFAULT_BACKUP_LIMITS,
    BackupErrorCode,
    BackupLimits,
    ChiwaBotsBackupError,
    inspect_chiwabots_backup,
    read_chiwabots_backup_entry,
)


def _archive(
    files: dict[str, bytes],
    *,
    compression: int = ZIP_STORED,
    extra_entries: tuple[ZipInfo, ...] = (),
) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=compression) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        for info in extra_entries:
            archive.writestr(info, b"target")
    return output.getvalue()


def _assert_error(
    code: BackupErrorCode,
    operation,
) -> ChiwaBotsBackupError:
    with pytest.raises(ChiwaBotsBackupError) as caught:
        operation()
    assert caught.value.code is code
    return caught.value


def _encrypted_archive() -> bytes:
    """Set the encryption flag in both headers without needing a ZIP password writer."""
    data = bytearray(_archive({"manifest.json": b"{}"}))
    local_header = data.index(b"PK\x03\x04")
    central_header = data.index(b"PK\x01\x02")
    for flag_offset in (local_header + 6, central_header + 8):
        flags = int.from_bytes(data[flag_offset : flag_offset + 2], "little") | 0x1
        data[flag_offset : flag_offset + 2] = flags.to_bytes(2, "little")
    return bytes(data)


def test_default_archive_limits_are_part_of_the_import_contract() -> None:
    assert DEFAULT_BACKUP_LIMITS == BackupLimits(
        max_upload_bytes=5 * 1024 * 1024,
        max_entries=100,
        max_expanded_bytes=20 * 1024 * 1024,
        max_compression_ratio=50.0,
        max_path_length=1024,
    )


def test_inspect_accepts_a_small_archive_and_returns_only_regular_files() -> None:
    data = _archive(
        {
            "commands/": b"",
            "manifest.json": b'{"version":1}',
            r"commands\custom.json": b"[]",
        }
    )

    manifest = inspect_chiwabots_backup(data)

    assert len(manifest.files) == 2
    assert [entry.name for entry in manifest.files] == [
        "manifest.json",
        "commands/custom.json",
    ]
    assert [entry.uncompressed_size for entry in manifest.files] == [13, 2]
    assert manifest.total_uncompressed_size == 15


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"", BackupErrorCode.EMPTY_UPLOAD),
        (b"not a zip", BackupErrorCode.NOT_ZIP),
        (_archive({}), BackupErrorCode.EMPTY_ARCHIVE),
    ],
)
def test_inspect_rejects_empty_or_non_archive_input(
    data: bytes,
    expected: BackupErrorCode,
) -> None:
    _assert_error(expected, lambda: inspect_chiwabots_backup(data))


def test_inspect_rejects_an_oversized_upload_before_parsing() -> None:
    limits = BackupLimits(max_upload_bytes=8)

    _assert_error(
        BackupErrorCode.UPLOAD_TOO_LARGE,
        lambda: inspect_chiwabots_backup(b"PK\x03\x04" + b"x" * 5, limits=limits),
    )


def test_inspect_rejects_too_many_entries() -> None:
    data = _archive({"one.json": b"1", "two.json": b"2"})

    _assert_error(
        BackupErrorCode.TOO_MANY_ENTRIES,
        lambda: inspect_chiwabots_backup(data, limits=BackupLimits(max_entries=1)),
    )


def test_inspect_rejects_excessive_declared_expanded_size() -> None:
    data = _archive({"one.json": b"123456", "two.json": b"abcdef"})

    _assert_error(
        BackupErrorCode.EXPANDED_TOO_LARGE,
        lambda: inspect_chiwabots_backup(
            data,
            limits=BackupLimits(max_expanded_bytes=10),
        ),
    )


def test_inspect_rejects_a_suspicious_compression_ratio() -> None:
    data = _archive({"commands.json": b"A" * 256}, compression=ZIP_DEFLATED)

    _assert_error(
        BackupErrorCode.SUSPICIOUS_COMPRESSION,
        lambda: inspect_chiwabots_backup(
            data,
            limits=BackupLimits(max_compression_ratio=2),
        ),
    )


@pytest.mark.parametrize(
    "name",
    [
        "/commands.json",
        r"C:\commands.json",
        "../commands.json",
        r"commands\..\secrets.json",
        r"\\server\share\commands.json",
    ],
)
def test_inspect_rejects_absolute_drive_and_parent_paths(name: str) -> None:
    _assert_error(
        BackupErrorCode.UNSAFE_PATH,
        lambda: inspect_chiwabots_backup(_archive({name: b"[]"})),
    )


@pytest.mark.parametrize(
    "files",
    [
        {"Commands.json": b"1", "commands.json": b"2"},
        {"commands/./custom.json": b"1", "commands/custom.json": b"2"},
    ],
)
def test_inspect_rejects_duplicate_normalized_paths(files: dict[str, bytes]) -> None:
    _assert_error(
        BackupErrorCode.DUPLICATE_PATH,
        lambda: inspect_chiwabots_backup(_archive(files)),
    )


def test_inspect_rejects_symlinks_and_other_special_files() -> None:
    symlink = ZipInfo("commands-link")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    fifo = ZipInfo("commands-pipe")
    fifo.create_system = 3
    fifo.external_attr = (stat.S_IFIFO | 0o600) << 16

    _assert_error(
        BackupErrorCode.UNSUPPORTED_ENTRY_TYPE,
        lambda: inspect_chiwabots_backup(_archive({}, extra_entries=(symlink,))),
    )
    _assert_error(
        BackupErrorCode.UNSUPPORTED_ENTRY_TYPE,
        lambda: inspect_chiwabots_backup(_archive({}, extra_entries=(fifo,))),
    )


def test_inspect_rejects_encrypted_entries() -> None:
    _assert_error(
        BackupErrorCode.ENCRYPTED_ENTRY,
        lambda: inspect_chiwabots_backup(_encrypted_archive()),
    )


def test_inspect_rejects_non_deflate_compression() -> None:
    data = _archive({"commands.json": b"[]"}, compression=ZIP_BZIP2)

    _assert_error(
        BackupErrorCode.UNSUPPORTED_COMPRESSION,
        lambda: inspect_chiwabots_backup(data),
    )


def test_read_entry_is_memory_only_case_insensitive_and_size_limited() -> None:
    data = _archive({"Commands/Custom.json": b"12345"})

    assert (
        read_chiwabots_backup_entry(
            data,
            "commands/custom.json",
            max_bytes=5,
        )
        == b"12345"
    )
    _assert_error(
        BackupErrorCode.ENTRY_TOO_LARGE,
        lambda: read_chiwabots_backup_entry(
            data,
            "commands/custom.json",
            max_bytes=4,
        ),
    )


def test_read_entry_rejects_unknown_or_unsafe_names() -> None:
    data = _archive({"commands.json": b"[]"})

    _assert_error(
        BackupErrorCode.ENTRY_NOT_FOUND,
        lambda: read_chiwabots_backup_entry(data, "missing.json", max_bytes=10),
    )
    _assert_error(
        BackupErrorCode.UNSAFE_PATH,
        lambda: read_chiwabots_backup_entry(data, "../commands.json", max_bytes=10),
    )


def test_read_entry_wraps_crc_failures_in_a_safe_error() -> None:
    data = bytearray(_archive({"commands.json": b"payload"}))
    payload_offset = data.index(b"payload")
    data[payload_offset : payload_offset + 7] = b"PAYLOAD"

    error = _assert_error(
        BackupErrorCode.CORRUPT_ARCHIVE,
        lambda: read_chiwabots_backup_entry(
            bytes(data),
            "commands.json",
            max_bytes=10,
        ),
    )
    assert "commands.json" not in str(error)
