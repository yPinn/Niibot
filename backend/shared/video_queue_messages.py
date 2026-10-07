"""Chat copy for the Video Queue — `!vq` / `!np` replies and redemption results.

One module so the chat command and the channel-points redemption say exactly
the same thing (the redemption path only prefixes ``@user``). House style:
short but polite, only a successful request carries an emote, and no technical
detail — a viewer needs to know how to request and what the limits are.

Every title that reaches chat goes through ``_clean_title`` and every message
through ``_fit``: provider titles run up to ~140 characters (Twitch) and a
Twitch chat message over 500 characters is rejected outright, i.e. the viewer
would get no reply at all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from shared.models.video_queue import VideoQueueEntry, VideoQueueInsert, VideoQueueSettings
from shared.services.video_queue_admission import AdmissionReason
from shared.services.video_queue_insert import InsertReason
from shared.video_segments import MIN_SEGMENT_SECONDS, SegmentErrorCode
from shared.video_sources import (
    UNPLAYABLE_AGE_RESTRICTED,
    UNPLAYABLE_INVALID_PAGE,
    UNPLAYABLE_LIVE,
    UNPLAYABLE_NOT_EMBEDDABLE,
    UNPLAYABLE_NOT_VIDEO,
    UNPLAYABLE_PRIVATE,
    UNPLAYABLE_REMOVED,
    build_watch_url,
)

TWITCH_MESSAGE_LIMIT = 500
TITLE_MAX = 60
LIST_TITLE_MAX = 30
LIST_PREVIEW_COUNT = 3

NOTHING_PLAYING = "目前沒有播放中的影片"
QUEUE_EMPTY = "目前沒有待播影片"
NO_OWN_REQUEST = "你目前沒有待播中的點播"
NOT_OWN_REQUEST = "只能取消自己點的影片"
SKIP_RACED = "影片已換，未跳過"
UNAVAILABLE = "暫時無法點播，請稍後再試"
PAUSED = "目前暫停點播"

_SORRY = "抱歉，這部影片無法點播"

# Why a video can't play, said plainly: a viewer who spent points deserves to
# know it's the video (or the streamer's choice), not a glitch worth retrying.
# Anything unrecognised stays the generic _SORRY.
_UNPLAYABLE: dict[str, str] = {
    UNPLAYABLE_INVALID_PAGE: "找不到指定的分P，請確認連結",
    UNPLAYABLE_NOT_VIDEO: "這則貼文不是影片，請確認連結",
    UNPLAYABLE_LIVE: "直播進行中無法點播，結束後可點播重播",
    UNPLAYABLE_NOT_EMBEDDABLE: "影片擁有者不允許外部播放",
    UNPLAYABLE_AGE_RESTRICTED: "這部影片有年齡限制，無法在實況中播放",
    UNPLAYABLE_PRIVATE: "這是私人影片，無法播放",
    UNPLAYABLE_REMOVED: "這部影片已被移除或無法觀看",
}

# Blocklist matches name the rule's kind, never its value (the keyword itself
# stays private). A blocked *requester* is deliberately not told — it invites
# arguments and alt accounts — and gets the generic _SORRY.
_BLOCKED: dict[str, str] = {
    "video": "這部影片已被實況主設為不開放點播",
    "creator": "這位創作者的影片不開放點播",
    "keyword": "影片標題含有不開放點播的關鍵字",
}


SEGMENT_EXAMPLE = "1:30-4:00"

_SEGMENT_ERRORS: dict[str, str] = {
    "format": f"時間格式錯誤，例：{SEGMENT_EXAMPLE}",
    "order": "開始時間需早於結束時間",
    "out_of_range": "時間點超出影片長度，請確認",
    "too_short": f"片段至少需 {MIN_SEGMENT_SECONDS} 秒",
}


def segment_error_message(code: SegmentErrorCode | str) -> str:
    return _SEGMENT_ERRORS.get(code, _SEGMENT_ERRORS["format"])


def too_long_message(details: Mapping[str, int | str]) -> str:
    """``segment`` detail: 1 = a segment was chosen, 0 = one could be (hint), else n/a."""
    limit = int(details["limit_seconds"])
    segment = int(details.get("segment", -1))
    if segment == 1:
        return f"片段長度請在 {format_length(limit)}內"
    if segment == 0:
        example = f"1:30-{format_clock(90 + limit)}"
        return f"影片長度請在 {format_length(limit)}內，可指定片段，例：{example}"
    return f"影片長度請在 {format_length(limit)}內"


def _fit(message: str) -> str:
    if len(message) <= TWITCH_MESSAGE_LIMIT:
        return message
    return message[: TWITCH_MESSAGE_LIMIT - 1] + "…"


def _clean_title(entry_title: str | None, fallback: str, limit: int = TITLE_MAX) -> str:
    # Collapse newlines/runs of whitespace: chat is single-line.
    title = " ".join((entry_title or "").split()) or fallback
    return title if len(title) <= limit else title[: limit - 1] + "…"


def _entry_title(entry: VideoQueueEntry, limit: int = TITLE_MAX) -> str:
    return _clean_title(entry.title, entry.video_id, limit)


def format_clock(seconds: int) -> str:
    """``90`` → ``1:30``; under a minute → ``45 秒``."""
    minutes, secs = divmod(max(0, int(seconds)), 60)
    return f"{minutes}:{secs:02d}" if minutes else f"{secs} 秒"


def format_length(seconds: int) -> str:
    """``600`` → ``10 分鐘``; ``90`` → ``1 分 30 秒``."""
    minutes, secs = divmod(max(0, int(seconds)), 60)
    if not minutes:
        return f"{secs} 秒"
    return f"{minutes} 分鐘" if not secs else f"{minutes} 分 {secs} 秒"


def rejection_message(reason: AdmissionReason, details: Mapping[str, int | str]) -> str:
    if reason in (AdmissionReason.DISABLED, AdmissionReason.SOURCE_DISABLED):
        return PAUSED
    if reason is AdmissionReason.INVALID_URL:
        if details.get("hint") == "twitch_channel":
            return "直播無法點播，請改用 VOD 連結（twitch.tv/videos/…）"
        return "不支援此連結，請使用 YouTube／Twitch／Bilibili／IG Reel"
    if reason is AdmissionReason.DUPLICATE:
        return "這部影片已在待播中"
    if reason is AdmissionReason.QUEUE_FULL:
        return "待播已滿，請稍後再試"
    if reason is AdmissionReason.USER_LIMIT:
        return f"每人最多點 {details['max_per_user']} 首，請等播完再點"
    if reason is AdmissionReason.USER_COOLDOWN:
        return f"請於 {format_clock(int(details['remaining_seconds']))} 後再點播"
    if reason is AdmissionReason.MIN_VIEWS:
        return f"影片觀看數需達 {int(details['min_view_count']):,} 以上"
    if reason is AdmissionReason.TOO_LONG:
        return too_long_message(details)
    if reason is AdmissionReason.INVALID_SEGMENT:
        return segment_error_message(str(details.get("segment_error") or ""))
    if reason is AdmissionReason.REPLAY_COOLDOWN:
        return f"這部影片 {details['hours']} 小時內播過了，請換一部"
    if reason is AdmissionReason.NOT_PLAYABLE:
        return _UNPLAYABLE.get(str(details.get("unplayable_reason") or ""), _SORRY)
    if reason is AdmissionReason.BLOCKED:
        return _BLOCKED.get(str(details.get("blocked_kind") or ""), _SORRY)
    # METADATA_UNVERIFIABLE, QUEUE_CHANGED: transient, retrying is the fix.
    return UNAVAILABLE


def accepted_message(title: str | None, video_id: str, position: int | None) -> str:
    place = f"，第 {position} 首" if position else ""
    return _fit(f"「{_clean_title(title, video_id)}」已加入待播{place} SeemsGood")


def now_playing_message(entry: VideoQueueEntry) -> str:
    """No remaining time: it is stale the moment it is sent, and the overlay
    already shows a live countdown for anyone who needs one."""
    url = build_watch_url(entry.video_type, entry.video_id, entry.start_seconds)
    return _fit(f"▶「{_entry_title(entry)}」 {url} | 點播：{entry.requested_by}")


def queue_list_message(
    current: VideoQueueEntry | None,
    queued: Sequence[VideoQueueEntry],
    insert: VideoQueueInsert | None = None,
) -> str:
    if current is None and not queued and insert is None:
        return QUEUE_EMPTY
    parts: list[str] = []
    # The live insert is the background: it shows only once the queue is empty.
    if insert is not None and current is None:
        parts.append(f"直播中：{_insert_name(insert, LIST_TITLE_MAX)}")
    if current is not None:
        parts.append(f"▶ {_entry_title(current, LIST_TITLE_MAX)}")
    if queued:
        titles = " ".join(
            f"{i}.{_entry_title(entry, LIST_TITLE_MAX)}"
            for i, entry in enumerate(queued[:LIST_PREVIEW_COUNT], 1)
        )
        overflow = (
            f"（+{len(queued) - LIST_PREVIEW_COUNT}）" if len(queued) > LIST_PREVIEW_COUNT else ""
        )
        parts.append(f"{titles}{overflow}")
    if insert is not None and current is not None:
        parts.append(f"播完回到直播：{_insert_name(insert, LIST_TITLE_MAX)}")
    return _fit(" | ".join(parts))


# ---------------------------------------------------------------------------
# Live insert (直播播放) — broadcaster-only, see shared.services.video_queue_insert
# ---------------------------------------------------------------------------

INSERT_NONE = "目前沒有播放直播"
INSERT_STOPPED = "已結束直播，恢復播放佇列"
INSERT_USAGE = "用法：!vq live <Twitch 頻道或 YouTube 直播網址> | !vq live stop"

_INSERT_REJECTIONS: dict[InsertReason, str] = {
    InsertReason.INVALID_URL: "直播只支援 Twitch 頻道或 YouTube 直播網址",
    InsertReason.NOT_LIVE: "目前沒有進行中的直播",
    InsertReason.OWN_CHANNEL: "不能播放自己的直播",
    InsertReason.NOT_PLAYABLE: "這個直播不開放外部播放",
    InsertReason.UNVERIFIABLE: "暫時無法播放這個直播，請稍後再試",
}


def insert_watch_url(insert: VideoQueueInsert) -> str:
    if insert.source_type == "twitch_live":
        return f"https://www.twitch.tv/{insert.source_id}"
    return f"https://youtu.be/{insert.source_id}"


def _insert_name(insert: VideoQueueInsert, limit: int = TITLE_MAX) -> str:
    return _clean_title(insert.creator_name, insert.source_id, limit)


# Where a wrong-kind URL should go instead: chat names the command, the
# dashboard names the 影片 / 直播 mode of its single URL box.
IS_LIVE_HINT = {
    "chat": "這是進行中的直播，請用 !vq live <網址> 播放",
    "dashboard": "這是進行中的直播，請切換到「直播」播放",
}
_IS_VIDEO_HINT = {
    "chat": "這是一般影片，請用 !vq <網址> 點播",
    "dashboard": "這是一般影片，請切換到「影片」加入",
}


def insert_rejection_message(
    reason: InsertReason, *, surface: Literal["chat", "dashboard"] = "chat"
) -> str:
    if reason is InsertReason.IS_VIDEO:
        return _IS_VIDEO_HINT[surface]
    return _INSERT_REJECTIONS.get(reason, UNAVAILABLE)


def insert_started_message(insert: VideoQueueInsert) -> str:
    return _fit(f"開始播放 {_insert_name(insert)} 的直播，有點播時會先播點播")


def insert_now_playing_message(insert: VideoQueueInsert) -> str:
    title = f"「{_clean_title(insert.title, '', TITLE_MAX)}」" if insert.title else ""
    return _fit(f"直播中：{_insert_name(insert)}{title} {insert_watch_url(insert)}")


def removed_message(entry: VideoQueueEntry) -> str:
    return _fit(f"已取消「{_entry_title(entry)}」")


def no_such_position_message(position: int) -> str:
    return f"沒有第 {position} 首"


def skipped_message(next_entry: VideoQueueEntry | None) -> str:
    if next_entry is None:
        return "已跳過，待播已空"
    return _fit(f"已跳過，下一首「{_entry_title(next_entry)}」")


def cleared_message(total: int) -> str:
    return f"已清空 {total} 首" if total else QUEUE_EMPTY


def usage_message(*, is_moderator: bool, reward_name: str | None) -> str:
    # Never let a reply start with "!": another bot in chat would read the
    # bot's own message as a command. Hence the "用法：" lead-in.
    if is_moderator:
        return "用法：!vq <網址> | list | remove | skip | clear | rules"
    commands = "!vq list | !vq remove | !vq rules | !np"
    if reward_name:
        return _fit(f"點播請兌換「{_clean_title(reward_name, reward_name)}」 | {commands}")
    return f"用法：{commands}"


def rules_message(settings: VideoQueueSettings, reward_name: str | None) -> str:
    """The limits a viewer's (redemption) request is held to — only those on."""
    if not settings.enabled:
        return PAUSED
    if not reward_name:
        return "目前不開放觀眾點播"
    parts = [
        f"兌換「{_clean_title(reward_name, reward_name)}」點播",
        f"可指定片段：網址 {SEGMENT_EXAMPLE}",
    ]
    limits = [x for x in (settings.max_duration_seconds, settings.max_duration_redemption) if x > 0]
    if limits:
        parts.append(f"長度 {format_length(min(limits))}內")
    if settings.max_per_user > 0:
        parts.append(f"每人 {settings.max_per_user} 首")
    if settings.user_cooldown_seconds > 0:
        parts.append(f"間隔 {format_length(settings.user_cooldown_seconds)}")
    if settings.min_view_count > 0:
        parts.append(f"觀看數 {settings.min_view_count:,} 以上")
    if settings.replay_cooldown_hours > 0:
        parts.append(f"{settings.replay_cooldown_hours} 小時內不重播")
    return _fit(" | ".join(parts))
