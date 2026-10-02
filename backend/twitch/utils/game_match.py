"""Pick the Twitch category a viewer most likely meant by `!game <text>`.

Twitch's category search ranks by text relevance with no typo tolerance and no
notion of popularity, so `val` returns "Valkyrie Profile" ahead of VALORANT and
`lol` returns an obscure category literally named "LOL" ahead of League of
Legends. People type what they stream, and what they stream is overwhelmingly a
popular game, so candidates are weighted by where they sit in Twitch's
top-categories list (current viewership order).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from twitchio import Game

# Bonus for the #1 category, shrinking linearly down the list. Bigger than the
# prefix vs word-prefix gap (0.2), so a popular game beats an obscure one that
# matches about as well; too small for a popular game to win on an unrelated name.
_POPULARITY_WEIGHT = 0.5
_INJECT_SIMILARITY = 0.75


def fallback_queries(query: str) -> list[str]:
    """Shorter search terms to retry when the full query finds nothing.

    Twitch's search has no typo tolerance: "valrant" returns nothing while
    "val" finds Valorant. Try each word (longest first), then prefixes cut from
    the end (where typos tend to be), ending on 3 / 2 / 1 characters.
    """
    text = query.strip()
    seen = {text.casefold()}
    terms: list[str] = []

    def add(term: str) -> None:
        term = term.strip()
        if term and term.casefold() not in seen:
            seen.add(term.casefold())
            terms.append(term)

    for word in sorted(text.split(), key=len, reverse=True):
        if len(word) >= 2:
            add(word)
    near_end = range(len(text) - 1, max(len(text) - 5, 0), -1)
    for length in sorted({*near_end, 3, 2, 1}, reverse=True):
        if 0 < length < len(text):
            add(text[:length])
    return terms


def _words(name: str) -> list[str]:
    return re.findall(r"\w+", name.casefold())


def _similarity(wanted: str, name: str) -> float:
    return SequenceMatcher(None, wanted, name.casefold()).ratio()


def _quality(wanted: str, name: str) -> float:
    """Text match strength in [0, 1]: prefix > a word's prefix > similarity."""
    if name.casefold().startswith(wanted):
        return 1.0
    if any(word.startswith(wanted) for word in _words(name)):
        return 0.8
    return _similarity(wanted, name) * 0.7


def _abbreviates(wanted: str, name: str) -> bool:
    """`lol` -> League of Legends, `cs` -> Counter-Strike, `dbd` -> Dead by
    Daylight, `gta` -> Grand Theft Auto V (a 3+ letter query may be a prefix of
    the initials)."""
    if len(wanted) < 2 or " " in wanted:
        return False
    initials = "".join(word[0] for word in _words(name))
    return initials == wanted or (len(wanted) >= 3 and initials.startswith(wanted))


def pick_category(query: str, searched: list[Game], top: list[Game]) -> Game | None:
    """Choose the category for `query`.

    `searched` is Twitch's search result (relevance order); `top` is the
    top-categories list (popularity order, may be empty if it could not be
    fetched, in which case this degrades to text matching alone). Order of
    preference:

    1. a popular category whose name equals the query
    2. a popular category the query abbreviates
    3. any category whose name equals the query
    4. best text match plus a popularity bonus

    Popular categories that match the query but did not appear in the (short)
    search result are added, so they cannot be missed. Returns None only when
    there is nothing to choose from.
    """
    wanted = query.strip().casefold()
    rank = {game.id: i for i, game in enumerate(top)}

    pool = {game.id: game for game in searched}
    for game in top:
        if (
            _quality(wanted, game.name) >= 0.8
            or _abbreviates(wanted, game.name)
            or _similarity(wanted, game.name) >= _INJECT_SIMILARITY
        ):
            pool.setdefault(game.id, game)
    if not pool:
        return None

    games = list(pool.values())
    popular = sorted((g for g in games if g.id in rank), key=lambda g: rank[g.id])

    for game in popular:
        if game.name.casefold() == wanted:
            return game
    for game in popular:
        if _abbreviates(wanted, game.name):
            return game
    for game in games:
        if game.name.casefold() == wanted:
            return game

    def score(game: Game) -> float:
        bonus = _POPULARITY_WEIGHT * (1 - rank[game.id] / len(top)) if game.id in rank else 0.0
        return _quality(wanted, game.name) + bonus

    # max() keeps the first of equal scores: Twitch's own ranking breaks ties.
    return max(games, key=score)
