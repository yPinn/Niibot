"""Rendering helpers for EventsComponent's configurable chat greetings.

Kept separate from ``utils.substitution`` (which handles custom command /
trigger responses with a chatter object and its own variable set). These are
pure functions over a plain ``dict[str, str]`` of event variables.
"""

import re

MESSAGE_VAR_LIMIT = 200

# ``$(name)`` or ``$(@name)`` — the ``@`` form is a separate dict key the caller
# supplies (``@user`` -> ``"@小明"`` or, for an anonymous chatter, the plain name).
_VAR_RE = re.compile(r"\$\((@?\w+)\)")

# ``[[ ... ]]`` marks an optional segment: dropped entirely when any ``$(var)``
# inside it has no value, otherwise the brackets are stripped and it renders.
_SEGMENT_RE = re.compile(r"\[\[(.*?)\]\]", re.DOTALL)


def mention_vars(key: str, name: str, *, anonymous: bool = False) -> dict[str, str]:
    """``{key: name, "@"+key: mention}`` — the mention is ``@name`` unless the
    chatter is anonymous or nameless, in which case it stays plain."""
    mention = name if (anonymous or not name) else f"@{name}"
    return {key: name, f"@{key}": mention}


def clean_message_var(value: str) -> str:
    """Neutralise a viewer-typed ``$(message)`` variable.

    Collapses newlines / whitespace runs, drops one leading Twitch command char
    (``/`` or ``.``) so the bot can't be made to run a command, and caps length
    so a long resub note can't push the greeting past Twitch's 500-char limit.
    """
    text = " ".join(value.split())
    if text and text[0] in "/.":
        text = text[1:].lstrip()
    return text[:MESSAGE_VAR_LIMIT]


def _resolve_segments(template: str, variables: dict[str, str]) -> str:
    """Drop each ``[[ ... ]]`` whose referenced vars aren't all populated; strip
    the brackets from the rest. An absent key and an empty value both count as
    "no value"."""

    def repl(m: re.Match[str]) -> str:
        segment = m.group(1)
        if any(not variables.get(name, "") for name in _VAR_RE.findall(segment)):
            return ""
        return segment

    return _SEGMENT_RE.sub(repl, template)


def render_template(template: str, variables: dict[str, str]) -> str:
    """Render a channel's greeting template.

    1. ``[[ optional ]]`` segments collapse when a var inside has no value.
    2. ``$(name)`` / ``$(@name)`` are substituted in a single left-to-right pass:
       a known key resolves to its value (possibly ``""``); an unknown key is
       left literal. Any ``$(...)`` inside a substituted value (e.g. a viewer
       typing ``$(user)`` into their resub note) is NOT re-expanded — injection
       via the ``$(message)`` value is structurally impossible.
    """
    template = _resolve_segments(template, variables)
    return _VAR_RE.sub(lambda m: variables.get(m.group(1), m.group(0)), template)
