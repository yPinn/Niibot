"""Import custom commands from other Twitch chat bots.

Nightbot and StreamElements are the two the users we see are actually moving
off. The package is split so the risky parts stay testable in isolation:
``mapping`` is pure translation, ``sources`` are the per-platform HTTP
adapters, and ``service`` owns caching and the database writes.

Import from the submodules — there is no facade, so there is exactly one path
to every symbol.
"""
