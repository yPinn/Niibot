"""Strict renderer for channel-owned daily check-in reply templates."""

from __future__ import annotations

import re
from datetime import date

_VARIABLE_PATTERN = re.compile(r"\$\(([^)]+)\)")
_SUPPORTED_VARIABLES = frozenset({"@user", "user", "count", "date"})
_TWITCH_MESSAGE_LIMIT = 500
_MAX_REPLACEMENT_LENGTHS = {
    "@user": 129,
    "user": 128,
    "count": 19,
    "date": 10,
}


def validate_checkin_template(template: str) -> None:
    """Reject unknown variables and templates whose valid output could overflow."""
    variables = set(_VARIABLE_PATTERN.findall(template))
    unsupported = variables.difference(_SUPPORTED_VARIABLES)
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise ValueError(f"Unsupported check-in template variable: {names}")

    worst_case_length = len(
        _VARIABLE_PATTERN.sub(
            lambda match: "x" * _MAX_REPLACEMENT_LENGTHS[match.group(1)],
            template,
        )
    )
    if worst_case_length > _TWITCH_MESSAGE_LIMIT:
        raise ValueError("Rendered check-in message exceeds 500 characters")


def render_checkin_template(
    template: str,
    *,
    username: str,
    display_name: str | None,
    total_days: int,
    checkin_date: date,
) -> str:
    """Render the small, explicit variable set accepted by check-in templates."""
    validate_checkin_template(template)

    user = display_name or username
    replacements = {
        "@user": f"@{user}",
        "user": user,
        "count": str(total_days),
        "date": checkin_date.isoformat(),
    }
    rendered = _VARIABLE_PATTERN.sub(lambda match: replacements[match.group(1)], template)
    return rendered
