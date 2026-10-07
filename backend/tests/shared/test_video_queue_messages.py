"""Copy contract for shared.video_queue_messages (chat `!vq` / `!np` / redemption)."""

from __future__ import annotations

import pytest

from shared.models.video_queue import VideoQueueEntry, VideoQueueSettings
from shared.services.video_queue_admission import AdmissionReason
from shared.video_queue_messages import (
    TWITCH_MESSAGE_LIMIT,
    accepted_message,
    cleared_message,
    format_clock,
    format_length,
    now_playing_message,
    queue_list_message,
    rejection_message,
    removed_message,
    rules_message,
    skipped_message,
    usage_message,
)

_DETAILS: dict[AdmissionReason, dict[str, int | str]] = {
    AdmissionReason.QUEUE_FULL: {"queue_size": 20, "max_queue_size": 20},
    AdmissionReason.USER_LIMIT: {"max_per_user": 3},
    AdmissionReason.USER_COOLDOWN: {"remaining_seconds": 90},
    AdmissionReason.MIN_VIEWS: {"view_count": 12, "min_view_count": 5000},
    AdmissionReason.TOO_LONG: {"duration_seconds": 900, "limit_seconds": 600},
    AdmissionReason.REPLAY_COOLDOWN: {"hours": 6},
    AdmissionReason.NOT_PLAYABLE: {"unplayable_reason": "private"},
    AdmissionReason.METADATA_UNVERIFIABLE: {"field": "duration_seconds"},
    AdmissionReason.INVALID_SEGMENT: {"segment_error": "format"},
}


def _entry(**kw) -> VideoQueueEntry:
    base = {
        "id": 1,
        "channel_id": "ch1",
        "video_id": "dQw4w9WgXcQ",
        "requested_by": "viewer",
        "source": "chat",
        "status": "playing",
        "video_type": "youtube",
        "title": "Never Gonna Give You Up",
    }
    return VideoQueueEntry(**{**base, **kw})


EXPECTED_REJECTIONS = {
    AdmissionReason.DISABLED: "目前暫停點播",
    AdmissionReason.SOURCE_DISABLED: "目前暫停點播",
    AdmissionReason.INVALID_URL: "不支援此連結，請使用 YouTube／Twitch／Bilibili／IG Reel",
    AdmissionReason.DUPLICATE: "這部影片已在待播中",
    AdmissionReason.QUEUE_FULL: "待播已滿，請稍後再試",
    AdmissionReason.USER_LIMIT: "每人最多點 3 首，請等播完再點",
    AdmissionReason.USER_COOLDOWN: "請於 1:30 後再點播",
    AdmissionReason.NOT_PLAYABLE: "抱歉，這部影片無法點播",
    AdmissionReason.INVALID_SEGMENT: "時間格式錯誤，例：1:30-4:00",
    AdmissionReason.METADATA_UNVERIFIABLE: "暫時無法點播，請稍後再試",
    AdmissionReason.MIN_VIEWS: "影片觀看數需達 5,000 以上",
    AdmissionReason.TOO_LONG: "影片長度請在 10 分鐘內",
    AdmissionReason.REPLAY_COOLDOWN: "這部影片 6 小時內播過了，請換一部",
    AdmissionReason.BLOCKED: "抱歉，這部影片無法點播",
    AdmissionReason.QUEUE_CHANGED: "暫時無法點播，請稍後再試",
}


def test_every_admission_reason_has_reviewed_copy():
    assert set(EXPECTED_REJECTIONS) == set(AdmissionReason)
    for reason, expected in EXPECTED_REJECTIONS.items():
        assert rejection_message(reason, _DETAILS.get(reason, {})) == expected


def test_rejections_carry_no_emote_or_counts_viewers_dont_need():
    for reason in AdmissionReason:
        message = rejection_message(reason, _DETAILS.get(reason, {}))
        assert "SeemsGood" not in message
        assert "KappaPride" not in message
    # The submitted video's own view count is not disclosed, only the bar.
    assert "12" not in rejection_message(
        AdmissionReason.MIN_VIEWS, _DETAILS[AdmissionReason.MIN_VIEWS]
    )


@pytest.mark.parametrize(
    ("unplayable_reason", "expected"),
    [
        ("invalid_page", "找不到指定的分P，請確認連結"),
        ("not_video", "這則貼文不是影片，請確認連結"),
        ("live", "直播進行中無法點播，結束後可點播重播"),
        ("age_restricted", "抱歉，這部影片無法點播"),
        ("not_embeddable", "抱歉，這部影片無法點播"),
        ("", "抱歉，這部影片無法點播"),
    ],
)
def test_unplayable_only_explains_what_the_requester_can_fix(unplayable_reason, expected):
    assert (
        rejection_message(AdmissionReason.NOT_PLAYABLE, {"unplayable_reason": unplayable_reason})
        == expected
    )


def test_time_formats():
    assert format_clock(90) == "1:30"
    assert format_clock(45) == "45 秒"
    assert format_length(600) == "10 分鐘"
    assert format_length(90) == "1 分 30 秒"
    assert format_length(30) == "30 秒"


def test_accepted_message():
    assert accepted_message("Song", "vid", 2) == "「Song」已加入待播，第 2 首 SeemsGood"
    # Promoted to playing before the lookup — no misleading position.
    assert accepted_message("Song", "vid", None) == "「Song」已加入待播 SeemsGood"
    assert accepted_message(None, "vid", 1) == "「vid」已加入待播，第 1 首 SeemsGood"


def test_titles_are_single_line_and_truncated():
    message = accepted_message("A\nB" + "x" * 200, "vid", 1)
    assert "\n" not in message
    assert "A B" in message
    assert "…" in message
    assert len(message) < 100


def test_now_playing_has_link_and_requester_but_no_countdown():
    line = now_playing_message(_entry())
    assert line == "▶「Never Gonna Give You Up」 https://youtu.be/dQw4w9WgXcQ | 點播：viewer"
    assert "剩餘" not in line


def test_queue_list_stays_under_the_twitch_limit_with_long_titles():
    long = "標題" * 80  # Twitch titles run to 140 characters
    queued = [_entry(id=i, status="queued", title=long) for i in range(2, 10)]
    message = queue_list_message(_entry(title=long), queued)
    assert len(message) <= TWITCH_MESSAGE_LIMIT
    assert message.startswith("▶ ")
    assert "（+5）" in message


def test_queue_list_empty():
    assert queue_list_message(None, []) == "目前沒有待播影片"


def test_other_replies():
    assert removed_message(_entry(title="Mine")) == "已取消「Mine」"
    assert skipped_message(_entry(title="Next")) == "已跳過，下一首「Next」"
    assert skipped_message(None) == "已跳過，待播已空"
    assert cleared_message(3) == "已清空 3 首"
    assert cleared_message(0) == "目前沒有待播影片"


def test_usage_by_role():
    assert usage_message(is_moderator=True, reward_name="點歌") == (
        "用法：!vq <網址> | list | remove | skip | clear | rules"
    )
    assert usage_message(is_moderator=False, reward_name="點歌") == (
        "點播請兌換「點歌」 | !vq list | !vq remove | !vq rules | !np"
    )
    assert usage_message(is_moderator=False, reward_name=None) == (
        "用法：!vq list | !vq remove | !vq rules | !np"
    )


def test_rules_lists_only_enabled_limits():
    settings = VideoQueueSettings(
        channel_id="ch1",
        max_duration_seconds=300,
        max_duration_redemption=600,
        max_per_user=3,
        user_cooldown_seconds=300,
        min_view_count=5000,
        replay_cooldown_hours=6,
    )
    assert rules_message(settings, "點歌") == (
        "兌換「點歌」點播 | 可指定片段：網址 1:30-4:00 | 長度 5 分鐘內 | 每人 3 首 | 間隔 5 分鐘 | "
        "觀看數 5,000 以上 | 6 小時內不重播"
    )
    bare = VideoQueueSettings(channel_id="ch1", max_duration_redemption=0)
    assert rules_message(bare, "點歌") == "兌換「點歌」點播 | 可指定片段：網址 1:30-4:00"
    assert rules_message(bare, None) == "目前不開放觀眾點播"
    assert rules_message(VideoQueueSettings(channel_id="ch1", enabled=False), "點歌") == (
        "目前暫停點播"
    )


def test_no_reply_can_trigger_another_bot():
    """Bot replies never start with "!" — another bot in chat would read it as a command."""
    entry = _entry(title="!ban everyone")
    samples = [
        accepted_message("!ban everyone", "vid", 1),
        now_playing_message(entry),
        queue_list_message(entry, [entry]),
        removed_message(entry),
        skipped_message(entry),
        rules_message(VideoQueueSettings(channel_id="ch1"), "!reward"),
        usage_message(is_moderator=True, reward_name=None),
        usage_message(is_moderator=False, reward_name=None),
        usage_message(is_moderator=False, reward_name="!reward"),
        *(rejection_message(r, _DETAILS.get(r, {})) for r in AdmissionReason),
    ]
    assert not [s for s in samples if s.startswith("!")]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("format", "時間格式錯誤，例：1:30-4:00"),
        ("order", "開始時間需早於結束時間"),
        ("out_of_range", "時間點超出影片長度，請確認"),
        ("too_short", "片段至少需 10 秒"),
    ],
)
def test_segment_errors_have_reviewed_copy(code, expected):
    assert rejection_message(AdmissionReason.INVALID_SEGMENT, {"segment_error": code}) == expected


@pytest.mark.parametrize(
    ("segment", "expected"),
    [
        (1, "片段長度請在 10 分鐘內"),
        (0, "影片長度請在 10 分鐘內，可指定片段，例：1:30-11:30"),
        (-1, "影片長度請在 10 分鐘內"),
    ],
)
def test_too_long_hints_a_segment_only_where_one_helps(segment, expected):
    details = {"duration_seconds": 900, "limit_seconds": 600, "segment": segment}
    assert rejection_message(AdmissionReason.TOO_LONG, details) == expected


def test_twitch_channel_link_points_at_a_vod():
    message = rejection_message(AdmissionReason.INVALID_URL, {"hint": "twitch_channel"})
    assert message == "直播無法點播，請改用 VOD 連結（twitch.tv/videos/…）"


def test_insert_copy():
    from shared.models.video_queue import VideoQueueInsert
    from shared.services.video_queue_insert import InsertReason
    from shared.video_queue_messages import (
        insert_now_playing_message,
        insert_rejection_message,
        insert_started_message,
    )

    insert = VideoQueueInsert(
        id=1,
        channel_id="ch1",
        source_type="youtube_live",
        source_id="jfKfPfyJRdk",
        volume_percent=30,
        title="lofi radio",
        creator_name="Lofi Girl",
    )
    assert insert_started_message(insert) == "開始插播 Lofi Girl 的直播，佇列暫停"
    assert insert_now_playing_message(insert) == (
        "插播中：Lofi Girl「lofi radio」 https://youtu.be/jfKfPfyJRdk"
    )
    assert queue_list_message(None, [], insert) == "插播中：Lofi Girl"
    assert accepted_message("Song", "vid", 2, inserting=True) == (
        "「Song」已加入待播，第 2 首（目前插播中，結束後播放） SeemsGood"
    )
    assert {insert_rejection_message(reason) for reason in InsertReason} >= {
        "插播只支援 Twitch 頻道或 YouTube 直播網址",
        "目前沒有進行中的直播",
        "不能插播自己的直播",
    }
