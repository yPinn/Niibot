"""The single definition of Niibot's chat response variable grammar.

Two very different places need to agree on this list: the Twitch bot, which
expands the variables at send time, and the command importer, which has to tell
a streamer whether a command brought over from Nightbot or StreamElements will
still work. When those two drifted apart the importer silently marked a
supported variable as unsupported and dropped the command, so the pattern lives
here in ``shared`` where both services can reach it.

``backend/twitch/utils/substitution.py`` performs the expansion;
``frontend/.../CommandSheet.tsx`` lists the same names for the dashboard's
insert buttons and is the one copy that cannot import this.
"""

from __future__ import annotations

import re

#: Named groups let the expander dispatch without re-parsing:
#: ``simple`` for the plain lookups, ``position`` for ``$(1)``–``$(9)``,
#: ``lo``/``hi`` for ``$(random a,b)``, ``items`` for ``$(pick a,b,c)``.
VARIABLE_PATTERN = re.compile(
    r"\$\((?:"
    r"(?P<simple>user|sender|touser|query|channel|count)"
    r"|(?P<position>[1-9])"
    r"|random\s+(?P<lo>\d+)\s*,\s*(?P<hi>\d+)"
    r"|pick\s+(?P<items>[^)]+)"
    r")\)"
)

#: Anything shaped like a variable, in either Niibot's ``$(name)`` or
#: StreamElements' ``${name}`` spelling.
_ANY_VARIABLE = re.compile(r"\$[({]\s*([a-zA-Z_][\w.]*|\d+)")


def unsupported_variables(text: str) -> list[str]:
    """Names of variable-shaped tokens in *text* that Niibot cannot expand.

    Works by deleting every form the expander understands and reporting what is
    left, so a new supported variable only has to be added to
    ``VARIABLE_PATTERN`` for this to stay correct.
    """
    leftovers = _ANY_VARIABLE.findall(VARIABLE_PATTERN.sub("", text))
    return list(dict.fromkeys(leftovers))  # de-duplicate, keep order
