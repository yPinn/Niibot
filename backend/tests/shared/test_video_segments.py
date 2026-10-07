"""Time-range syntax and segment planning (shared.video_segments)."""

from __future__ import annotations

import pytest

from shared.video_segments import (
    PlaybackSegment,
    SegmentError,
    TimeRange,
    parse_submission_range,
    parse_time_range,
    plan_segment,
)

# ---------------------------------------------------------------------------
# parse_time_range
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1:30", TimeRange(90, None)),
        ("1:30-4:00", TimeRange(90, 240)),
        ("-4:00", TimeRange(None, 240)),
        ("90:00", TimeRange(5400, None)),
        ("1:02:03-1:05:00", TimeRange(3723, 3900)),
        ("0:45", TimeRange(45, None)),
        # Tolerated, not advertised.
        ("1:30 - 4:00", TimeRange(90, 240)),
        ("1:30 -4:00", TimeRange(90, 240)),
        ("1：30－4：00", TimeRange(90, 240)),
        ("1:30~4:00", TimeRange(90, 240)),
        ("1:30～4:00", TimeRange(90, 240)),
        ("1:30–4:00", TimeRange(90, 240)),
        ("1:30—4:00", TimeRange(90, 240)),
        ("1m30s-4m", TimeRange(90, 240)),
        ("1h2m", TimeRange(3720, None)),
        ("90s", TimeRange(90, None)),
        ("1M30S", TimeRange(90, None)),
        # A comment after the time is ignored.
        ("1:30-4:00 這段最好聽", TimeRange(90, 240)),
        ("  1:30", TimeRange(90, None)),
    ],
)
def test_parses_supported_forms(text, expected):
    assert parse_time_range(text) == expected


@pytest.mark.parametrize("text", ["", "好聽", "  推推", "@someone 1:30", "lofi"])
def test_text_not_starting_with_a_time_is_a_comment(text):
    assert parse_time_range(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "90",  # bare number: seconds or minutes?
        "5",
        "1.30",  # decimal
        "1:3",  # seconds need two digits
        "1:75",  # seconds out of range
        "1:60:00",  # minutes out of range in h:mm:ss
        "-",
        "- 好聽",
        "1:30-好聽",
        "2倍速好看",
        "1:30:00:00",
    ],
)
def test_malformed_time_rejects(text):
    with pytest.raises(SegmentError) as exc_info:
        parse_time_range(text)
    assert exc_info.value.code == "format"


@pytest.mark.parametrize("text", ["4:00-1:30", "1:30-1:30"])
def test_start_must_precede_end(text):
    with pytest.raises(SegmentError) as exc_info:
        parse_time_range(text)
    assert exc_info.value.code == "order"


# ---------------------------------------------------------------------------
# parse_submission_range — locating the time after the URL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://youtu.be/dQw4w9WgXcQ 1:30-4:00", TimeRange(90, 240)),
        ("youtu.be/dQw4w9WgXcQ -4:00", TimeRange(None, 240)),
        ("看這個 https://youtu.be/dQw4w9WgXcQ 1:30", TimeRange(90, None)),
        ("https://youtu.be/dQw4w9WgXcQ", None),
        ("https://youtu.be/dQw4w9WgXcQ 好聽", None),
        ("「https://youtu.be/dQw4w9WgXcQ」 1:30", TimeRange(90, None)),
        # A time before the URL is not "after the URL".
        ("1:30 https://youtu.be/dQw4w9WgXcQ", None),
        ("no url here 1:30", None),
    ],
)
def test_time_follows_the_first_url(text, expected):
    assert parse_submission_range(text) == expected


def test_bare_time_is_never_mistaken_for_the_url():
    with pytest.raises(SegmentError):
        parse_submission_range("https://youtu.be/dQw4w9WgXcQ 1.30")


# ---------------------------------------------------------------------------
# plan_segment
# ---------------------------------------------------------------------------


def test_whole_video_without_any_time():
    assert plan_segment("youtube", 300) == PlaybackSegment(0, 300, trimmed=False)


def test_typed_range():
    assert plan_segment("youtube", 300, requested=TimeRange(90, 240)) == PlaybackSegment(
        90, 150, trimmed=True
    )


def test_start_only_plays_to_the_end():
    assert plan_segment("youtube", 300, requested=TimeRange(90, None)) == PlaybackSegment(
        90, 210, trimmed=True
    )


def test_end_only_plays_from_zero_even_with_a_url_offset():
    # A typed time wins over the URL's ?t= (Twitch VOD) entirely.
    assert plan_segment(
        "twitch_vod", 300, url_start=60, requested=TimeRange(None, 120)
    ) == PlaybackSegment(0, 120, trimmed=True)


def test_url_offset_is_the_start_when_nothing_is_typed():
    assert plan_segment("twitch_vod", 300, url_start=60) == PlaybackSegment(60, 240, trimmed=True)


@pytest.mark.parametrize("video_type", ["twitch_clip", "instagram_reel"])
def test_unsupported_platforms_ignore_the_time(video_type):
    assert plan_segment(
        video_type, 30, url_start=5, requested=TimeRange(10, 20)
    ) == PlaybackSegment(0, 30, trimmed=False)


@pytest.mark.parametrize(
    ("requested", "url_start"),
    [
        (TimeRange(300, None), 0),
        (TimeRange(90, 301), 0),
        (None, 300),
    ],
)
def test_range_outside_the_video_rejects(requested, url_start):
    with pytest.raises(SegmentError) as exc_info:
        plan_segment("twitch_vod", 300, url_start=url_start, requested=requested)
    assert exc_info.value.code == "out_of_range"


def test_end_at_exactly_the_video_length_is_fine():
    assert plan_segment("youtube", 300, requested=TimeRange(200, 300)).duration_seconds == 100


def test_segment_shorter_than_ten_seconds_rejects():
    with pytest.raises(SegmentError) as exc_info:
        plan_segment("youtube", 300, requested=TimeRange(90, 99))
    assert exc_info.value.code == "too_short"
    assert plan_segment("youtube", 300, requested=TimeRange(90, 100)).duration_seconds == 10


def test_unknown_length_keeps_what_can_be_known():
    # Bilibili best-effort metadata: no length to check against.
    assert plan_segment("bilibili", None, requested=TimeRange(90, None)) == PlaybackSegment(
        90, None, trimmed=True
    )
    assert plan_segment("bilibili", None, requested=TimeRange(90, 240)) == PlaybackSegment(
        90, 150, trimmed=True
    )


class TestTwitchVodWindow:
    def test_window_is_capped_from_the_start_point(self):
        # 2h VOD, start 1h50m in → 10 min remains, capped at the 600s window.
        assert plan_segment("twitch_vod", 7200, url_start=6600).duration_seconds == 600

    def test_shorter_remainder_wins_over_the_cap(self):
        assert plan_segment("twitch_vod", 7200, url_start=7100).duration_seconds == 100

    def test_unknown_length_falls_back_to_the_window(self):
        assert plan_segment("twitch_vod", None) == PlaybackSegment(0, 600, trimmed=False)

    def test_window_narrows_to_the_length_limit(self):
        assert plan_segment("twitch_vod", 7200, window_cap=300).duration_seconds == 300

    def test_typed_end_replaces_the_window(self):
        assert plan_segment("twitch_vod", 7200, requested=TimeRange(60, 1260)) == PlaybackSegment(
            60, 1200, trimmed=True
        )

    def test_start_at_or_past_the_end_rejects(self):
        with pytest.raises(SegmentError) as exc_info:
            plan_segment("twitch_vod", 7200, url_start=7200)
        assert exc_info.value.code == "out_of_range"
