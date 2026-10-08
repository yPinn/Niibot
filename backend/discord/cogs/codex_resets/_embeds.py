"""Embed builders for Codex Resets notifications.

Layout, most important first
----------------------------
- colour: the notification kind (see _COLOR_*), readable before any text
- title: the short notification itself (plain text — no link)
- author: always Codex Resets, the data source (no link)
- description: countdown / `-#` note when needed (titles cannot render
  timestamps), then the attributed original — 4096 chars, so the excerpt
  stays near-complete
- fields: the facts, full-width, one line each, `English（中文）`; times are
  Discord timestamps so every viewer sees their own timezone
- 原文: the poster's words, verbatim, last — the only untranslated content;
  everything else is Niibot's Chinese summary
- no footer: it repeated the author row
- buttons: the only CTAs — the post, Open Codex once quota is usable, and
  always the site
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

# The original shares the 4096-char description with the headline and facts.
TEXT_LIMIT = 3500

SITE_URL = "https://codex-resets.com"
# The site's own favicon (Tibo, who announces nearly every reset).
_SITE_ICON = f"{SITE_URL}/thsottiaux-avatar.jpg"
# Names the data source; no link — the buttons are the only CTAs.
_SITE_AUTHOR: dict[str, str | None] = {"name": "Codex Resets", "icon_url": _SITE_ICON}
CODEX_URL = "https://chatgpt.com/codex"

# (label, url) pairs rendered as link buttons under a notification.
Link = tuple[str, str]

# One colour per notification kind, so the kind reads before any text does.
_COLOR_REGULAR = discord.Color.green()  # full reset — quota usable now
_COLOR_BANKED = discord.Color.gold()  # banked reset — credit to spend later
_COLOR_SCHEDULED = discord.Color.blurple()  # announced, not yet executed
_COLOR_REMINDER = discord.Color.red()  # announced reset is minutes away
_COLOR_WATCH = discord.Color.purple()  # AI forecast — speculative
_COLOR_STATUS = discord.Color.teal()  # /codex
_COLOR_ENDED = discord.Color.light_grey()  # superseded / historical

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


_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
# Where a cut still reads as a whole thought: paragraph end, else sentence end.
_SENTENCE_END = re.compile(r"[.!?。！？](?=\s|$)")


def _cut(text: str, limit: int) -> str:
    """Trim to `limit` at the last paragraph, else sentence, boundary in the back half."""
    head = text[:limit]
    floor = limit // 2
    if (para := head.rfind("\n\n")) >= floor:
        return head[:para]
    ends = [m.end() for m in _SENTENCE_END.finditer(head) if m.end() >= floor]
    return head[: ends[-1]] if ends else head.rstrip()


def clean_text(text: str, limit: int = TEXT_LIMIT) -> str:
    """Post text with its paragraphs intact; long posts end on a whole paragraph/sentence."""
    text = _TRAILING_TCO.sub("", text or "").strip()
    paragraphs = [
        "\n".join(line.strip() for line in block.splitlines() if line.strip())
        for block in _PARAGRAPH_BREAK.split(text)
    ]
    text = "\n\n".join(p for p in paragraphs if p)
    truncated = len(text) > limit
    text = limit_markdown(_cut(text, limit).rstrip() if truncated else text)
    return text + " …" if truncated else text


def quote(text: str) -> str:
    """Per-line `> ` quote; a bare `> ` keeps paragraph gaps inside the block.

    Not `>>>`: that quotes to the end of the description, and the reference
    time line has to follow the quote unquoted.
    """
    return "\n".join(f"> {line}" for line in text.split("\n"))


def _source_url(item: dict[str, Any]) -> str | None:
    return (item.get("source") or {}).get("url")


def _is_observed(item: dict[str, Any]) -> bool:
    return (item.get("source") or {}).get("type") == "observed"


# Known X handles → display name, so the quote reads "Tibo (@thsottiaux)".
_POSTER_NAMES = {"thsottiaux": "Tibo"}


def _clock(local: datetime) -> str:
    """`2026/10/08 3:00 PM` — plain English 12-hour clock for the reference line."""
    half = "AM" if local.hour < 12 else "PM"
    return f"{local:%Y/%m/%d} {local.hour % 12 or 12}:{local:%M} {half}"


def format_zone(dt: datetime, tz: ZoneInfo) -> str:
    """`2026/10/08 3:00 PM UTC+8` — an offset, not an ambiguous abbreviation."""
    local = dt.astimezone(tz)
    offset = local.utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset else 0
    sign, minutes = ("+" if minutes >= 0 else "-"), abs(minutes)
    hours, rest = divmod(minutes, 60)
    label = f"UTC{sign}{hours}" + (f":{rest:02d}" if rest else "")
    return f"{_clock(local)} {label}"


def _ts(value: str, style: TimestampStyle) -> str:
    return discord.utils.format_dt(parse_dt(value), style)


# Layout:
#   description — `###` headline about now / next, optional `-#` note, then the
#                 attributed original as `>>>` (last: it quotes to the end). The
#                 description holds 4096 chars, so the original stays near-complete.
#   fields      — the facts: full-width (inline=False), ONE line each, never
#                 relying on a narrow column to wrap.
# Language: terms from an official announcement (Tibo / OpenAI on X) keep the
# English original — `Banked Reset（儲存額度）`; anything non-official (Codex
# Resets observations, its AI forecast, Niibot's own estimates) is Chinese only.


def _bi(en: str, zh: str) -> str:
    return f"{en}（{zh}）"


def _when(value: str, *, relative: bool = True) -> str:
    """Field value, one line: the viewer's local time (Discord timestamps).

    Pass relative=False when the headline already counts down.
    """
    return _local(value, relative=relative)


def _reference(value: str, tz: ZoneInfo | None) -> str:
    """Description's last line: the key time in one reference zone.

    The guild's chosen zone (`/codex-config channel timezone`), defaulting to
    Pacific — the zone the announcements themselves speak in.
    """
    zone = format_zone(parse_dt(value), tz) if tz is not None else _pacific(value)
    return f"-# {zone}"


def _local(value: str, *, relative: bool = True) -> str:
    """`2026/10/08 15:00 · in 9 hours` in the viewer's own timezone (Discord timestamps)."""
    parts = [f"{_ts(value, 'd')} {_ts(value, 't')}"]
    if relative:
        parts.append(_ts(value, "R"))
    return " · ".join(parts)


# Tibo / OpenAI announce in Pacific time ("by EOD PST"): the default reference zone.
_PACIFIC = ZoneInfo("America/Los_Angeles")


def _pacific(value: str) -> str:
    """`2026/10/08 12:00 AM PDT` — %Z follows DST (PDT / PST)."""
    local = parse_dt(value).astimezone(_PACIFIC)
    return f"{_clock(local)} {local:%Z}"


_RESET_TYPE = {"regular": ("Full Reset", "全面重置"), "banked": ("Banked Reset", "儲存額度")}


def _type(item: dict[str, Any]) -> str:
    """Official post: `Banked Reset（儲存額度）`; observed (non-official): `儲存額度（觀測）`."""
    en, zh = _RESET_TYPE["banked" if item.get("reset_type") == "banked" else "regular"]
    return f"{zh}（觀測）" if _is_observed(item) else _bi(en, zh)


def _watch_level(watch: dict[str, Any]) -> str:
    level = str(watch.get("level") or "")
    return _WATCH_LEVEL.get(level, level or "—")  # AI forecast: non-official, Chinese only


def _original(item: dict[str, Any]) -> str | None:
    """The poster's own words, untranslated, with who said it and where.

    Everything else in the embed is Niibot's Chinese summary of Codex Resets
    data; this block is the only verbatim content. Observed resets carry an
    unrelated reply as text, so they get none. The trailing t.co link (nearly
    always a quoted post) is dropped without a marker; 查看公告 has the rest.
    """
    if _is_observed(item):
        return None
    text = clean_text(item.get("text", ""))
    if not text:
        return None
    # One quiet line naming the poster; a quote reads as a quote.
    handle = (item.get("source") or {}).get("author")
    if not handle:
        return quote(text)
    name = _POSTER_NAMES.get(handle.lower())
    who = f"{name} (@{handle})" if name else f"@{handle}"
    return f"-# {who}\n{quote(text)}"


def _description(
    lead: str | None = None,
    note: str | None = None,
    original: str | None = None,
    reference: str | None = None,
) -> str | None:
    """lead + note / original / reference time — blocks separated by blank lines."""
    top = "\n".join(part for part in (lead, note) if part)
    return "\n\n".join(part for part in (top, original, reference) if part) or None


def _base(
    factory: EmbedFactory,
    *,
    title: str,
    color: discord.Color,
    description: str | None,
    facts: list[tuple[str, str]],
) -> discord.Embed:
    """Shared chrome; `facts` become one-line full-width fields, in order.

    No title / author links and no footer: the link buttons below are the only
    CTAs, and the author row already names the source. The author is always
    Codex Resets, so it never reads as if the poster wrote the Chinese summary.
    """
    embed: discord.Embed = factory.build(
        title=title,
        description=description,
        color=color,
        author=_SITE_AUTHOR,
        footer=None,
    )
    for name, value in facts:
        embed.add_field(name=name, value=value, inline=False)
    return embed


def build_reset_embed(
    factory: EmbedFactory, reset: dict[str, Any], tz: ZoneInfo | None = None
) -> discord.Embed:
    banked = reset.get("reset_type") == "banked"
    return _base(
        factory,
        title=(
            "Codex 儲存額度已入帳，可自行決定何時使用"
            if banked
            else "Codex 額度已重置，現在就能使用"
        ),
        description=_description(
            note="-# 無正式公告，由 Codex Resets 觀測" if _is_observed(reset) else None,
            original=_original(reset),
            reference=_reference(reset["announced_at"], tz),
        ),
        facts=[("類型", _type(reset)), ("生效時間", _when(reset["announced_at"]))],
        color=_COLOR_BANKED if banked else _COLOR_REGULAR,
    )


# state: (title, color). Title and colour already say the state, so there is no
# status field. A settled announcement is history — grey; the green "reset"
# notice sent alongside `done` is the one that matters now.
_SCHEDULED_STATE: dict[str, tuple[str, discord.Color]] = {
    "pending": ("Codex 重置預告", _COLOR_SCHEDULED),
    "done": ("Codex 預告的重置已執行", _COLOR_ENDED),
    "ended": ("Codex 重置預告已取消或過期", _COLOR_ENDED),
}


def build_scheduled_embed(
    factory: EmbedFactory,
    scheduled: dict[str, Any],
    state: ScheduledState = "pending",
    tz: ZoneInfo | None = None,
) -> discord.Embed:
    title, color = _SCHEDULED_STATE[state]
    due = scheduled.get("scheduled_for")
    pending = state == "pending"
    lead = note = None
    if pending:
        # Titles cannot render timestamps, so the countdown leads the description.
        lead = f"### 預計 {_ts(due, 'R')} 重置" if due else "### 時間尚未公布"
        note = "-# 實際執行後會再通知"
    when = _when(due, relative=not pending) if due else "未公布"
    return _base(
        factory,
        title=title,
        description=_description(
            lead, note, _original(scheduled), _reference(due, tz) if due else None
        ),
        facts=[("預定時間", when), ("類型", _type(scheduled))],
        color=color,
    )


def build_reminder_embed(
    factory: EmbedFactory, scheduled: dict[str, Any], minutes: int, tz: ZoneInfo | None = None
) -> discord.Embed:
    """Heads-up shortly before an officially announced reset time."""
    due = scheduled["scheduled_for"]
    return _base(
        factory,
        title="Codex 即將重置",
        description=_description(
            f"### 預計 {_ts(due, 'R')} 重置",
            f"-# 依官方預告，提前 {minutes} 分鐘提醒",
            reference=_reference(due, tz),
        ),
        facts=[("預定時間", _when(due, relative=False)), ("類型", _type(scheduled))],
        color=_COLOR_REMINDER,
    )


def build_watch_embed(
    factory: EmbedFactory,
    watch: dict[str, Any],
    *,
    ended: bool = False,
    tz: ZoneInfo | None = None,
) -> discord.Embed:
    chance = watch.get("reset_chance_percent")
    if ended:
        title = "Codex 重置預測已結束"
    elif chance is not None:
        title = f"Codex 近期重置機率約 {chance}%"
    else:
        title = "Codex 近期重置的跡象升高"
    facts = [("預測等級", _watch_level(watch))]
    if window := watch.get("forecast_window"):
        facts.append(("預估時段", limit_markdown(str(window))))
    expires = None if ended else watch.get("expires_at")
    if expires:
        facts.append(("有效至", _when(expires)))
    return _base(
        factory,
        title=title,
        description=_description(
            note="-# Codex Resets 的 AI 推測，並非 OpenAI 官方承諾",
            reference=_reference(expires, tz) if expires else None,
        ),
        facts=facts,
        color=_COLOR_ENDED if ended else _COLOR_WATCH,
    )


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


def _next_reset(data: dict[str, Any], median: tuple[float, int] | None) -> tuple[str, str | None]:
    """(headline, note) for what happens next — the status embed's lead."""
    scheduled = data.get("scheduled_reset")
    watch = data.get("active_watch")
    days_since = (data.get("stats") or {}).get("days_since_last")

    if scheduled:
        due = scheduled.get("scheduled_for")
        if not due:
            return "### 官方已預告重置，時間未定", f"-# {_type(scheduled)}"
        return (
            f"### 官方預告 {_ts(due, 'R')} 重置",
            f"-# {_local(due, relative=False)} · {_type(scheduled)}",
        )
    if watch:
        chance = watch.get("reset_chance_percent")
        odds = f"機率約 {chance}%" if chance is not None else _watch_level(watch)
        return f"### AI 預測：近期重置{odds}", "-# Codex Resets 的 AI 推測，並非官方資訊"
    if median is None or days_since is None:
        return "### 目前沒有重置預告", None
    gap, count = median
    head = f"### 預估約 {gap - days_since:.1f} 天內重置" if days_since < gap else "### 隨時可能重置"
    return head, f"-# 尚無官方預告，依近 {count} 次重置間隔的中位數（{gap:.1f} 天）推算"


def build_status_embed(
    factory: EmbedFactory,
    data: dict[str, Any],
    tz: ZoneInfo | None = None,
    recent: list[dict[str, Any]] | None = None,
) -> discord.Embed:
    latest = data.get("latest_reset")
    stats = data.get("stats") or {}
    median = recent_median_gap(recent)

    facts: list[tuple[str, str]] = []
    if latest:
        facts.append(("上次重置", f"{_type(latest)} · {_ts(latest['announced_at'], 'R')}"))
    if total := stats.get("total"):
        parts = [f"累計 {total} 次"]
        if median is not None:
            parts.append(f"近期約 {median[0]:.1f} 天一次")
        elif (avg := stats.get("avg_interval_days")) is not None:
            parts.append(f"平均約 {avg:.1f} 天一次")
        facts.append(("統計", " · ".join(parts)))

    headline, note = _next_reset(data, median)
    due = (data.get("scheduled_reset") or {}).get("scheduled_for")
    return _base(
        factory,
        title="Codex 重置狀態",
        description=_description(headline, note, reference=_reference(due, tz) if due else None),
        facts=facts,
        color=_COLOR_STATUS,
    )


# ── Link buttons ─────────────────────────────────────────────────────────────
# Pure (label, url) lists so they are testable without an event loop; the cog
# wraps them with link_view() at send / edit time. Every message carries the
# Codex Resets site; the post link first, Open Codex only once quota is usable.

_SITE_LINK = ("Codex Resets", SITE_URL)
_CODEX_LINK = ("開啟 Codex", CODEX_URL)


def _links(*pairs: tuple[str, str | None]) -> list[Link]:
    return [(label, url) for label, url in pairs if url]


def reset_links(reset: dict[str, Any]) -> list[Link]:
    # An observed reset's source is an unrelated reply, hidden like its text.
    post = None if _is_observed(reset) else _source_url(reset)
    return _links(("查看公告", post), _CODEX_LINK, _SITE_LINK)


def scheduled_links(scheduled: dict[str, Any], state: ScheduledState = "pending") -> list[Link]:
    codex = _CODEX_LINK if state == "done" else ("", None)
    return _links(("查看公告", _source_url(scheduled)), codex, _SITE_LINK)


def reminder_links(scheduled: dict[str, Any]) -> list[Link]:
    return _links(("查看公告", _source_url(scheduled)), _SITE_LINK)


def watch_links(watch: dict[str, Any]) -> list[Link]:
    return _links(("預測依據", _source_url(watch)), _SITE_LINK)


def status_links(data: dict[str, Any]) -> list[Link]:
    latest = data.get("latest_reset") or {}
    return _links(("上次公告", _source_url(latest)), _CODEX_LINK, _SITE_LINK)


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
