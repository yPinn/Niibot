"""Video Queue play segments: the ``<url> 1:30-4:00`` time syntax + its validation.

A submission may follow its URL with a time range (see
``tasks/video-queue-live-and-segments.md`` for the design):

    ``1:30``       play from 1:30 to the end
    ``1:30-4:00``  play 1:30 → 4:00
    ``-4:00``      play from the start to 4:00

Points are ``m:ss`` (minutes may exceed 59) or ``h:mm:ss``. Tolerated but not
advertised: full-width ``：``/``－``, ``~``/``～``/``–``/``—`` as the dash,
spaces around the dash, and unit forms (``1m30s``, ``1h2m``). Bare numbers and
decimals (``90``, ``1.30``) are rejected — they are ambiguous.

Only text that *starts* with a digit or ``-`` right after the URL is treated as
a time; anything else is a comment and ignored. Once treated as a time, a parse
failure rejects the submission rather than silently playing the whole video.

The resolved segment is stored in the existing ``start_seconds`` +
``duration_seconds`` (= segment length) columns.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from shared.safe_urls import text_after_first_url

# Platforms whose player can seek and whose end is host-controlled. Twitch clips
# (≤60s, direct mp4) and Instagram Reels ignore a time instead of rejecting —
# a redemption should not burn its points over an unsupported option.
SEGMENT_VIDEO_TYPES = frozenset({"youtube", "twitch_vod", "bilibili"})

MIN_SEGMENT_SECONDS = 10

# A VOD is hours long: with no end point, play a window of at most this many
# seconds from the start point.
TWITCH_VOD_WINDOW_SECONDS = 600

SegmentErrorCode = Literal["format", "order", "out_of_range", "too_short"]


class SegmentError(ValueError):
    """A requested time range that cannot be played."""

    def __init__(self, code: SegmentErrorCode) -> None:
        self.code: SegmentErrorCode = code
        super().__init__(code)


@dataclass(frozen=True)
class TimeRange:
    """A requester-typed range; either side may be omitted (not both)."""

    start: int | None
    end: int | None


@dataclass(frozen=True)
class PlaybackSegment:
    """What the overlay plays: from ``start_seconds`` for ``duration_seconds``.

    ``duration_seconds`` is None only when neither the video length nor an end
    point is known (best-effort metadata). ``trimmed`` is True when the segment
    is narrower than the whole video by request (a typed range or a URL ``?t=``).
    """

    start_seconds: int
    duration_seconds: int | None
    trimmed: bool


_DASHES = str.maketrans({"~": "-", "〜": "-", "–": "-", "—": "-"})
_CLOCK = r"\d+(?::\d{2}){1,2}"
_UNITS = r"\d+h(?:\d+m)?(?:\d+s)?|\d+m(?:\d+s)?|\d+s"
_POINT = rf"(?:{_CLOCK}|{_UNITS})"
_RANGE_RE = re.compile(
    rf"(?P<start>{_POINT})?\s*(?:-\s*(?P<end>{_POINT})?)?(?=\s|$)",
    re.IGNORECASE,
)
_UNIT_RE = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", re.IGNORECASE)


def _point_seconds(text: str) -> int:
    if ":" in text:
        parts = [int(p) for p in text.split(":")]
        if any(p >= 60 for p in parts[1:]):
            raise SegmentError("format")
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    m = _UNIT_RE.fullmatch(text)
    assert m is not None  # guaranteed by _RANGE_RE
    h, mi, s = (int(g) if g else 0 for g in m.groups())
    return h * 3600 + mi * 60 + s


def parse_time_range(text: str) -> TimeRange | None:
    """Parse the time range at the start of ``text`` (the text after the URL).

    Returns None when ``text`` does not start with a digit or ``-`` (no time
    given, possibly a comment). Raises ``SegmentError("format")`` when it does
    but is not a valid range; ``"order"`` when start ≥ end.
    """
    text = unicodedata.normalize("NFKC", text).translate(_DASHES).lstrip()
    if not text or not (text[0].isdigit() or text[0] == "-"):
        return None
    m = _RANGE_RE.match(text)
    if m is None or (m.group("start") is None and m.group("end") is None):
        raise SegmentError("format")
    start = _point_seconds(m.group("start")) if m.group("start") else None
    end = _point_seconds(m.group("end")) if m.group("end") else None
    if start is not None and end is not None and start >= end:
        raise SegmentError("order")
    return TimeRange(start, end)


def parse_submission_range(text: str) -> TimeRange | None:
    """Time range following the first URL in a raw submission, if any."""
    rest = text_after_first_url(text)
    return parse_time_range(rest) if rest else None


def plan_segment(
    video_type: str,
    video_seconds: int | None,
    *,
    url_start: int = 0,
    requested: TimeRange | None = None,
    window_cap: int = 0,
) -> PlaybackSegment:
    """Resolve what to play from the video length, the URL's ``?t=`` and a typed range.

    A typed range wins over ``url_start`` entirely (``-4:00`` plays from 0).
    ``window_cap`` (the submission's length limit, 0 = none) narrows the
    default Twitch VOD window so a VOD without an end point is not rejected
    just because the window is longer than the limit.

    Raises ``SegmentError`` for a range outside the video or shorter than
    ``MIN_SEGMENT_SECONDS``.
    """
    if video_type not in SEGMENT_VIDEO_TYPES:
        return PlaybackSegment(0, video_seconds, trimmed=False)

    if requested is not None:
        start, end = requested.start or 0, requested.end
    else:
        start, end = max(0, url_start), None
    if end is not None and start >= end:
        raise SegmentError("order")
    if video_seconds is not None and (
        start >= video_seconds or (end is not None and end > video_seconds)
    ):
        raise SegmentError("out_of_range")

    if video_type == "twitch_vod" and end is None:
        window = min(TWITCH_VOD_WINDOW_SECONDS, window_cap or TWITCH_VOD_WINDOW_SECONDS)
        length: int | None = (
            min(window, video_seconds - start) if video_seconds is not None else window
        )
    elif end is not None:
        length = end - start
    else:
        length = video_seconds - start if video_seconds is not None else None

    trimmed = requested is not None or start > 0
    if trimmed and length is not None and length < MIN_SEGMENT_SECONDS:
        raise SegmentError("too_short")
    return PlaybackSegment(start, length, trimmed=trimmed)
