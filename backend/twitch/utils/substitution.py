"""Variable substitution for custom Twitch command responses.

Supported variables:
    $(user)             Chatter display name (falls back to name)
    $(query)            User input after the command trigger
    $(channel)          Channel / broadcaster name
    $(random min,max)   Random integer in range [min, max] (inclusive)
    $(pick a,b,c)       Random pick from comma-separated items
    $(count)            Command usage count (placeholder — not yet implemented)
"""

import random
import re
from typing import Protocol

_RANDOM_PATTERN = re.compile(r"\$\(random\s+(\d+)\s*,\s*(\d+)\)")
_PICK_PATTERN = re.compile(r"\$\(pick\s+(.+?)\)")


class ChatterLike(Protocol):
    """Minimal chatter interface required by substitute_variables."""

    display_name: str | None
    name: str | None


def substitute_variables(
    text: str,
    chatter: ChatterLike,
    channel_name: str,
    query: str,
) -> str:
    """Replace response variables in custom command / trigger text."""
    text = text.replace("$(user)", chatter.display_name or chatter.name or "")
    text = text.replace("$(query)", query)
    text = text.replace("$(channel)", channel_name or "")

    def _random_replace(m: re.Match) -> str:  # type: ignore[type-arg]
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            lo, hi = hi, lo
        return str(random.randint(lo, hi))

    text = _RANDOM_PATTERN.sub(_random_replace, text)

    def _pick_replace(m: re.Match) -> str:  # type: ignore[type-arg]
        items = [i.strip() for i in m.group(1).split(",") if i.strip()]
        return random.choice(items) if items else ""

    text = _PICK_PATTERN.sub(_pick_replace, text)

    return text
