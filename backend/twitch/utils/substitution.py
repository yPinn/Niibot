"""Variable substitution for custom Twitch command responses.

Supported variables:
    $(user)             Chatter display name (falls back to name)
    $(sender)           Alias of $(user) — the spelling StreamElements uses
    $(touser)           First argument, falling back to the chatter when absent
    $(query)            User input after the command trigger
    $(1) … $(9)         Single positional argument, split from the query
    $(channel)          Channel / broadcaster name
    $(count)            How many times this command has been used
    $(random min,max)   Random integer in range [min, max] (inclusive)
    $(pick a,b,c)       Random pick from comma-separated items

$(touser), $(sender) and the positional arguments exist because Nightbot and
StreamElements responses lean on them heavily — they are the difference between
a command importing cleanly and needing a manual rewrite.
"""

import random
import re
from typing import Protocol

from shared.command_variables import VARIABLE_PATTERN


class ChatterLike(Protocol):
    """Minimal chatter interface required by substitute_variables."""

    display_name: str | None
    name: str | None


def substitute_variables(
    text: str,
    chatter: ChatterLike,
    channel_name: str,
    query: str,
    *,
    count: int = 0,
) -> str:
    """Replace response variables in custom command / trigger text."""
    user = chatter.display_name or chatter.name or ""
    args = query.split()
    simple = {
        "user": user,
        "sender": user,
        # Nightbot semantics: the first argument, or the caller when none was given.
        "touser": args[0] if args else user,
        "query": query,
        "channel": channel_name or "",
        "count": str(count),
    }

    def _replace(m: re.Match) -> str:  # type: ignore[type-arg]
        if name := m.group("simple"):
            return simple[name]
        if position := m.group("position"):
            # Out-of-range positions collapse to "" rather than leaking the variable.
            index = int(position) - 1
            return args[index] if index < len(args) else ""
        if items := m.group("items"):
            choices = [i.strip() for i in items.split(",") if i.strip()]
            return random.choice(choices) if choices else ""
        lo, hi = int(m.group("lo")), int(m.group("hi"))
        return str(random.randint(*sorted((lo, hi))))

    # A single pass matters: whatever the chatter typed is inserted as literal
    # text instead of being rescanned, so $(pick …) in a viewer's message
    # cannot expand.
    return VARIABLE_PATTERN.sub(_replace, text)
