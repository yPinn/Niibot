"""Value objects for the command import preview.

One flat ``ImportItem`` covers all four sections rather than a class per kind:
the dashboard renders a single checklist grouped by section, and the apply
endpoint echoes the same shape back, so a common record keeps the API and the
UI honest about what the user actually selected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ImportSource(StrEnum):
    NIGHTBOT = "nightbot"
    STREAMELEMENTS = "streamelements"


class ImportSection(StrEnum):
    """Which part of the preview an item belongs to."""

    BUILTIN = "builtin"  # enable an existing Niibot builtin instead of creating anything
    CUSTOM = "custom"  # create a custom command
    TRIGGER = "trigger"  # create a keyword auto-response
    UNSUPPORTED = "unsupported"  # shown for transparency, cannot be imported


class ImportStatus(StrEnum):
    """How confident we are that the item will behave as it did before."""

    OK = "ok"  # nothing was lost in translation
    REVIEW = "review"  # imports, but something approximate happened
    CONFLICT = "conflict"  # name already taken by an existing command or alias
    UNSUPPORTED = "unsupported"  # needs a capability Niibot does not have


@dataclass
class ImportItem:
    """A single row in the import preview."""

    key: str
    """Stable identifier the client sends back in the apply request."""

    section: ImportSection
    status: ImportStatus
    source_name: str
    """The original trigger as the user knows it, e.g. "!discord"."""

    source_enabled: bool
    """Whether the command was enabled on the source platform."""

    notes: list[str] = field(default_factory=list)
    """Plain-language explanations shown next to the row."""

    # ── Command / trigger payload ────────────────────────────────────────
    command_name: str | None = None
    response: str | None = None
    original_response: str | None = None
    """Kept so the UI can show a before/after diff when variables were rewritten."""

    cooldown: int | None = None
    min_role: str = "everyone"
    aliases: list[str] = field(default_factory=list)

    # ── Trigger-only ─────────────────────────────────────────────────────
    pattern: str | None = None
    match_type: str = "contains"

    # ── Builtin-only ─────────────────────────────────────────────────────
    builtin_target: str | None = None
    """The Niibot builtin this source command maps onto."""


@dataclass
class ImportPreview:
    """Everything found for one channel on one source platform."""

    source: ImportSource
    source_channel: str
    items: list[ImportItem] = field(default_factory=list)


@dataclass
class ImportResult:
    """Outcome of applying a selection."""

    created: int = 0
    enabled: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
