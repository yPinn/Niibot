"""Built-in timer definitions — fire automatically for all channels without per-channel DB setup.

To add a new built-in timer:
  1. Append a BuiltinTimerDef to BUILTIN_TIMERS below.

If a channel has a DB timer with the same timer_name, the DB entry takes precedence
(the builtin is silently skipped for that channel), allowing per-channel customisation
or explicit disabling via the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuiltinTimerDef:
    timer_name: str
    interval_seconds: int
    min_lines: int
    message_template: str
    announce: bool = False


BUILTIN_TIMERS: list[BuiltinTimerDef] = [
    BuiltinTimerDef(
        timer_name="condemn",
        interval_seconds=1800,
        min_lines=20,
        message_template=(
            "本頻道實況主不認可並嚴厲斥責聊天室與斗內的任何惡意言論，"
            "包含且不限於種族歧視、性騷擾、色情暴力、涉及親屬等不當內容。"
        ),
        announce=True,
    ),
]
