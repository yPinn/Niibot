"""Rendering helpers for EventsComponent's configurable chat greetings.

Kept separate from ``utils.substitution`` (which handles custom command /
trigger responses with a chatter object and its own variable set). These are
pure functions over a plain ``dict[str, str]`` of event variables.
"""

MESSAGE_VAR_LIMIT = 200


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
    """Substitute ``$(name)`` placeholders. Unknown placeholders are left as-is."""
    for name, value in variables.items():
        template = template.replace(f"$({name})", value)
    return template
