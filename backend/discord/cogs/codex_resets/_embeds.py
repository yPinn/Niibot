"""Embed builders for Codex Resets notifications.

Layout
------
- author row: who said it (the X poster) or Codex Resets itself, linked
- description: the quoted announcement, then a `-#` note as its own section
- fields: at most three inline facts so they render as a single row
- no thumbnail: it would squeeze the field row, and the avatar already sits in
  the author row

Absolute times use the guild's configured timezone (`/codex set-channel`) when
set; otherwise Discord timestamps, which follow each viewer's device. The
relative countdown is always a Discord timestamp.
"""

from __future__ import annotations

import re
import statistics
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import discord
from discord.utils import TimestampStyle

from core import EmbedFactory

FOOTER = "Data from Codex Resets"
# Long-form X posts exceed 280; the description itself allows 4096.
TEXT_LIMIT = 600

SITE_URL = "https://codex-resets.com"
# The site's own favicon — the account that announces nearly every reset.
_SITE_ICON = f"{SITE_URL}/thsottiaux-avatar.jpg"
_SITE_ICON_AUTHOR = "thsottiaux"
_SITE_AUTHOR: dict[str, str | None] = {
    "name": "Codex Resets",
    "url": SITE_URL,
    "icon_url": _SITE_ICON,
}
CODEX_URL = "https://chatgpt.com/codex"

# (label, url) pairs rendered as link buttons under a notification.
Link = tuple[str, str]

_COLOR_REGULAR = discord.Color.green()
_COLOR_BANKED = discord.Color.gold()
_COLOR_SCHEDULED = discord.Color.blurple()
_COLOR_WATCH = discord.Color.orange()
_COLOR_ENDED = discord.Color.light_grey()

_WATCH_LEVEL = {"elevated": "升高", "strong": "強烈"}

# Trailing t.co links in X posts are media attachments — noise in a quote.
_TRAILING_TCO = re.compile(r"(?:\s*https://t\.co/\S+)+\s*$")

ScheduledState = Literal["pending", "done", "ended"]


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


_URL = re.compile(r"(https?://\S+)")
# Block-level syntax would restyle a whole line of an X post (headers, subtext, quotes).
_BLOCK_SYNTAX = re.compile(r"^(-#|#{1,3}|>{1,3})(?=\s)", re.MULTILINE)
# X handles like @wong2__ would otherwise toggle underline; || would hide text.
_INLINE_ESCAPES = (("```", r"\`\`\`"), ("||", r"\|\|"), ("_", r"\_"))
_PAIRED_MARKERS = (r"\*\*", "~~", "`")
_SINGLE_STAR = re.compile(r"(?<![\\*])\*(?!\*)")


def _escape_segment(segment: str) -> str:
    segment = segment.replace("\\", "\\\\")
    for raw, escaped in _INLINE_ESCAPES:
        segment = segment.replace(raw, escaped)
    return segment


def _balance(text: str) -> str:
    """Drop the last unpaired marker so truncation never leaves stray `**`."""
    for marker in _PAIRED_MARKERS:
        hits = list(re.finditer(rf"(?<!\\){marker}", text))
        if len(hits) % 2:
            text = text[: hits[-1].start()] + text[hits[-1].end() :]
    singles = list(_SINGLE_STAR.finditer(text))
    if len(singles) % 2:
        text = text[: singles[-1].start()] + r"\*" + text[singles[-1].end() :]
    return text


def limit_markdown(text: str) -> str:
    """Keep bold / italic / strikethrough / inline code; neutralise everything else."""
    parts = _URL.split(text)
    text = "".join(p if i % 2 else _escape_segment(p) for i, p in enumerate(parts))
    text = _BLOCK_SYNTAX.sub(r"\\\1", text)
    return _balance(text)


def clean_text(text: str, limit: int = TEXT_LIMIT) -> str:
    text = _TRAILING_TCO.sub("", text or "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)
    truncated = len(text) > limit
    text = limit_markdown(text[:limit].rstrip() if truncated else text)
    return text + "…" if truncated else text


def quote(text: str) -> str:
    return "\n".join(f"> {line}" for line in text.splitlines())


def _source_url(item: dict[str, Any]) -> str | None:
    return (item.get("source") or {}).get("url")


def _is_observed(item: dict[str, Any]) -> bool:
    return (item.get("source") or {}).get("type") == "observed"


def _author(item: dict[str, Any]) -> dict[str, str | None]:
    """Author row: the X poster for a post, otherwise Codex Resets itself."""
    source = item.get("source") or {}
    handle = source.get("author")
    if source.get("type") != "x_post" or not handle:
        return _SITE_AUTHOR
    icon = _SITE_ICON if handle.lower() == _SITE_ICON_AUTHOR else None
    return {"name": f"@{handle}", "url": f"https://x.com/{handle}", "icon_url": icon}


def format_zone(dt: datetime, tz: ZoneInfo) -> str:
    """`2026-10-08 15:00 (UTC+8)` — an offset, not an ambiguous abbreviation like CST."""
    local = dt.astimezone(tz)
    offset = local.utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset else 0
    sign, minutes = ("+" if minutes >= 0 else "-"), abs(minutes)
    hours, rest = divmod(minutes, 60)
    label = f"UTC{sign}{hours}" + (f":{rest:02d}" if rest else "")
    return f"{local:%Y-%m-%d %H:%M} ({label})"


def _when(value: str, tz: ZoneInfo | None = None, style: TimestampStyle = "f") -> str:
    """Absolute time (guild timezone if set) with a relative countdown underneath."""
    dt = parse_dt(value)
    absolute = format_zone(dt, tz) if tz else discord.utils.format_dt(dt, style)
    return f"{absolute}\n-# {discord.utils.format_dt(dt, 'R')}"


def _kind(item: dict[str, Any]) -> str:
    return "儲存額度" if item.get("reset_type") == "banked" else "全面重置"


def _odds(watch: dict[str, Any]) -> str:
    level = _WATCH_LEVEL.get(watch.get("level", ""), watch.get("level") or "—")
    chance = watch.get("reset_chance_percent")
    return f"**{level}**" + ("" if chance is None else f" · {chance}%")


def _sections(*blocks: str | None) -> str | None:
    """Join non-empty description blocks with a blank line between them."""
    return "\n\n".join(b for b in blocks if b) or None


def _base(
    factory: EmbedFactory,
    *,
    title: str,
    color: discord.Color,
    author: dict[str, str | None],
    description: str | None = None,
    url: str | None = None,
    timestamp: str | None = None,
) -> discord.Embed:
    embed: discord.Embed = factory.build(
        title=title,
        description=description,
        url=url,
        color=color,
        timestamp=parse_dt(timestamp) if timestamp else None,
        author=author,
        footer=FOOTER,
    )
    return embed


def build_reset_embed(
    factory: EmbedFactory, reset: dict[str, Any], tz: ZoneInfo | None = None
) -> discord.Embed:
    banked = reset.get("reset_type") == "banked"
    observed = _is_observed(reset)

    title = "Codex 儲存額度已發放" if banked else "Codex 額度已重置"
    body: str | None
    note: str | None
    if observed:
        title += "（觀測）"
        body, note = None, "-# 無正式公告，由 Codex Resets 觀測"
    else:
        text = clean_text(reset.get("text", ""))
        body = quote(text) if text else None
        note = "-# 額度存入帳戶，可自行決定何時使用" if banked else None

    embed = _base(
        factory,
        title=title,
        author=_SITE_AUTHOR if observed else _author(reset),
        description=_sections(body, note),
        url=None if observed else _source_url(reset),
        color=_COLOR_BANKED if banked else _COLOR_REGULAR,
        timestamp=reset["announced_at"],
    )
    embed.add_field(name="類型", value=f"**{_kind(reset)}**", inline=True)
    embed.add_field(name="公告時間", value=_when(reset["announced_at"], tz), inline=True)
    return embed


def build_scheduled_embed(
    factory: EmbedFactory,
    scheduled: dict[str, Any],
    state: ScheduledState = "pending",
    tz: ZoneInfo | None = None,
) -> discord.Embed:
    title, color, status = {
        "pending": ("Codex 重置預告", _COLOR_SCHEDULED, "等待執行"),
        "done": ("Codex 重置預告（已執行）", _COLOR_REGULAR, "已執行"),
        "ended": ("Codex 重置預告（已結束）", _COLOR_ENDED, "已取消或過期"),
    }[state]

    text = clean_text(scheduled.get("text", ""))
    note = "-# 實際執行後會另行通知" if state == "pending" else None
    embed = _base(
        factory,
        title=title,
        author=_author(scheduled),
        description=_sections(quote(text) if text else None, note),
        url=_source_url(scheduled),
        color=color,
        timestamp=scheduled["announced_at"],
    )

    scheduled_for = scheduled.get("scheduled_for")
    embed.add_field(
        name="預定時間", value=_when(scheduled_for, tz) if scheduled_for else "未公布", inline=True
    )
    embed.add_field(name="類型", value=_kind(scheduled), inline=True)
    embed.add_field(name="狀態", value=f"**{status}**", inline=True)
    return embed


def build_watch_embed(
    factory: EmbedFactory,
    watch: dict[str, Any],
    *,
    ended: bool = False,
    tz: ZoneInfo | None = None,
) -> discord.Embed:
    embed = _base(
        factory,
        title="Codex 重置觀察（已結束）" if ended else "Codex 可能即將重置",
        author=_SITE_AUTHOR,
        description="-# AI 推測，非 OpenAI 官方承諾",
        url=_source_url(watch),
        color=_COLOR_ENDED if ended else _COLOR_WATCH,
        timestamp=watch["observed_at"],
    )

    embed.add_field(name="觀察等級", value=_odds(watch), inline=True)
    if window := watch.get("forecast_window"):
        embed.add_field(name="預估時段", value=limit_markdown(str(window)), inline=True)
    if not ended and watch.get("expires_at"):
        embed.add_field(name="有效至", value=_when(watch["expires_at"], tz), inline=True)
    return embed


def build_reminder_embed(
    factory: EmbedFactory, scheduled: dict[str, Any], minutes: int, tz: ZoneInfo | None = None
) -> discord.Embed:
    """Heads-up shortly before an officially announced reset time."""
    due = discord.utils.format_dt(parse_dt(scheduled["scheduled_for"]), "R")
    embed = _base(
        factory,
        title="Codex 重置即將執行",
        author=_author(scheduled),
        description=_sections(f"官方預告的重置預計 **{due}** 執行", f"-# 提前 {minutes} 分鐘提醒"),
        url=_source_url(scheduled),
        color=_COLOR_SCHEDULED,
    )
    embed.add_field(name="預定時間", value=_when(scheduled["scheduled_for"], tz), inline=True)
    embed.add_field(name="類型", value=_kind(scheduled), inline=True)
    return embed


def recent_median_gap(recent: list[dict[str, Any]] | None) -> tuple[float, int] | None:
    """(median days between recent resets, gap count); None with fewer than 3 gaps.

    The API's all-time average is skewed by rare long droughts (mean ≈ 2× median),
    so estimates use the median of the recent window instead.
    """
    times = sorted(parse_dt(r["announced_at"]) for r in recent or [])
    gaps = [(b - a).total_seconds() / 86400 for a, b in zip(times, times[1:], strict=False)]
    if len(gaps) < 3:
        return None
    return statistics.median(gaps), len(gaps)


def _next_reset(
    data: dict[str, Any], tz: ZoneInfo | None, median: tuple[float, int] | None
) -> str | None:
    """Value for the status embed's 「下一次」 field, or None if unknown."""
    scheduled = data.get("scheduled_reset")
    watch = data.get("active_watch")
    days_since = (data.get("stats") or {}).get("days_since_last")

    if scheduled:
        when = (
            _when(scheduled["scheduled_for"], tz)
            if scheduled.get("scheduled_for")
            else "時間未公布"
        )
        return f"**官方預告**\n{when}"
    if watch:
        return f"觀察中 {_odds(watch)}\n-# AI 推測，非官方資訊"

    if median is None or days_since is None:
        return None
    gap, count = median
    if days_since < gap:
        return f"約 **{gap - days_since:.1f}** 天內\n-# 依近 {count} 次間隔中位數推算，非官方資訊"
    return f"已超過近期中位數\n-# 近 {count} 次中位數 {gap:.1f} 天，隨時可能重置"


def build_status_embed(
    factory: EmbedFactory,
    data: dict[str, Any],
    tz: ZoneInfo | None = None,
    recent: list[dict[str, Any]] | None = None,
) -> discord.Embed:
    latest = data.get("latest_reset")
    stats = data.get("stats") or {}
    median = recent_median_gap(recent)

    embed = _base(
        factory,
        title="Codex 重置狀態",
        author=_SITE_AUTHOR,
        description=None if latest else "尚無重置紀錄",
        url=SITE_URL,
        color=_COLOR_SCHEDULED,
    )

    if latest:
        kind = _kind(latest)
        label = f"[{kind}]({url})" if (url := _source_url(latest)) else kind
        embed.add_field(
            name="上次重置", value=f"**{label}**\n{_when(latest['announced_at'], tz)}", inline=True
        )

    if upcoming := _next_reset(data, tz, median):
        embed.add_field(name="下一次", value=upcoming, inline=True)

    total, avg = stats.get("total"), stats.get("avg_interval_days")
    if total:
        lines = [f"累計 **{total}** 次"]
        if median is not None:
            lines.append(f"近期約 **{median[0]:.1f}** 天一次")
        elif avg is not None:
            lines.append(f"平均 **{avg:.1f}** 天一次")
        if (days_since := stats.get("days_since_last")) is not None:
            lines.append(f"-# 距上次 {days_since:.1f} 天")
        embed.add_field(name="統計", value="\n".join(lines), inline=True)
    return embed


# ── Link buttons ─────────────────────────────────────────────────────────────
# Pure (label, url) lists so they are testable without an event loop; the cog
# wraps them with link_view() at send / edit time.


def _links(*pairs: tuple[str, str | None]) -> list[Link]:
    return [(label, url) for label, url in pairs if url]


def reset_links(reset: dict[str, Any]) -> list[Link]:
    # An observed reset's source is an unrelated reply, hidden like its text.
    if _is_observed(reset):
        return _links(("開啟 Codex", CODEX_URL), ("Codex Resets", SITE_URL))
    return _links(("查看公告", _source_url(reset)), ("開啟 Codex", CODEX_URL))


def scheduled_links(scheduled: dict[str, Any], state: ScheduledState = "pending") -> list[Link]:
    follow_up = {"pending": ("Codex Resets", SITE_URL), "done": ("開啟 Codex", CODEX_URL)}
    return _links(("查看公告", _source_url(scheduled)), follow_up.get(state, ("", None)))


def reminder_links(scheduled: dict[str, Any]) -> list[Link]:
    return _links(("查看公告", _source_url(scheduled)), ("Codex Resets", SITE_URL))


def watch_links(watch: dict[str, Any]) -> list[Link]:
    return _links(("觀察依據", _source_url(watch)), ("Codex Resets", SITE_URL))


def status_links(data: dict[str, Any]) -> list[Link]:
    latest = data.get("latest_reset") or {}
    return _links(
        ("上次公告", _source_url(latest)), ("開啟 Codex", CODEX_URL), ("Codex Resets", SITE_URL)
    )


def link_view(links: list[Link]) -> discord.ui.View | None:
    """Link-only view; never stored by discord.py, so it survives restarts as-is.

    Must be called inside a running event loop (discord.ui.View requirement).
    """
    if not links:
        return None
    view = discord.ui.View(timeout=None)
    for label, url in links:
        view.add_item(discord.ui.Button(label=label, url=url, style=discord.ButtonStyle.link))
    return view
