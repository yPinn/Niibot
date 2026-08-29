"""Rendering helpers for EventsComponent's configurable chat greetings.

Kept separate from ``utils.substitution`` (which handles custom command /
trigger responses with a chatter object and its own variable set). These are
pure functions over a plain ``dict[str, str]`` of event variables.
"""

import re

MESSAGE_VAR_LIMIT = 200

_VAR_RE = re.compile(r"\$\((\w+)\)")


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


def render_template(template: str, variables: dict[str, str]) -> str:
    """Substitute ``$(name)`` placeholders in a single left-to-right pass.

    Unknown placeholders are left as-is, and any ``$(...)`` that appears *inside*
    a substituted value (e.g. a viewer typing ``$(user)`` into their resub note)
    is NOT re-expanded — the single-pass regex makes variable injection via the
    ``$(message)`` value structurally impossible, regardless of dict order.
    """
    return _VAR_RE.sub(lambda m: variables.get(m.group(1), m.group(0)), template)
