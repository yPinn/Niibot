"""Embed builders for Codex Resets notifications — deliberately minimal."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

import discord

from core import EmbedFactory

FOOTER = "Data from Codex Resets"
TEXT_LIMIT = 280

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


def build_reset_embed(factory: EmbedFactory, reset: dict[str, Any]) -> discord.Embed:
    banked = reset.get("reset_type") == "banked"
    observed = _is_observed(reset)

    title = "Codex 儲存額度已發放" if banked else "Codex 額度已重置"
    lines: list[str] = []
    if observed:
        title += "（觀測）"
        lines.append("-# 無正式公告，由 Codex Resets 觀測")
    else:
        text = clean_text(reset.get("text", ""))
        if text:
            lines.append(quote(text))
        if banked:
            lines.append("-# 額度存入帳戶，可自行決定何時使用")

    embed: discord.Embed = factory.build(
        title=title,
        description="\n".join(lines) or None,
        url=_source_url(reset),
        color=_COLOR_BANKED if banked else _COLOR_REGULAR,
        timestamp=parse_dt(reset["announced_at"]),
        author=None,
        footer=FOOTER,
    )
    return embed


def build_scheduled_embed(
    factory: EmbedFactory, scheduled: dict[str, Any], state: ScheduledState = "pending"
) -> discord.Embed:
    title, color = {
        "pending": ("Codex 重置預告", _COLOR_SCHEDULED),
        "done": ("Codex 重置預告（已執行）", _COLOR_REGULAR),
        "ended": ("Codex 重置預告（已結束）", _COLOR_ENDED),
    }[state]

    lines: list[str] = []
    text = clean_text(scheduled.get("text", ""))
    if text:
        lines.append(quote(text))

    scheduled_for = scheduled.get("scheduled_for")
    if scheduled_for:
        dt = parse_dt(scheduled_for)
        when = f"{discord.utils.format_dt(dt, 'F')}（{discord.utils.format_dt(dt, 'R')}）"
        lines.append(f"預定時間 {when}")
    else:
        lines.append("預定時間未公布")
    if state == "pending":
        lines.append("-# 實際執行後會另行通知")

    embed: discord.Embed = factory.build(
        title=title,
        description="\n".join(lines),
        url=_source_url(scheduled),
        color=color,
        timestamp=parse_dt(scheduled["announced_at"]),
        author=None,
        footer=FOOTER,
    )
    return embed


def build_watch_embed(
    factory: EmbedFactory, watch: dict[str, Any], *, ended: bool = False
) -> discord.Embed:
    level = _WATCH_LEVEL.get(watch.get("level", ""), watch.get("level", ""))
    head = f"觀察等級 {level}"
    chance = watch.get("reset_chance_percent")
    if chance is not None:
        head += f" · 機率 {chance}%"

    lines = [head]
    if watch.get("forecast_window"):
        lines.append(f"預估時段 {watch['forecast_window']}")
    if not ended and watch.get("expires_at"):
        lines.append(f"有效至 {discord.utils.format_dt(parse_dt(watch['expires_at']), 'R')}")
    lines.append("-# AI 推測，非 OpenAI 官方承諾")

    embed: discord.Embed = factory.build(
        title="Codex 重置觀察（已結束）" if ended else "Codex 可能即將重置",
        description="\n".join(lines),
        url=_source_url(watch),
        color=_COLOR_ENDED if ended else _COLOR_WATCH,
        timestamp=parse_dt(watch["observed_at"]),
        author=None,
        footer=FOOTER,
    )
    return embed


def build_status_embed(factory: EmbedFactory, data: dict[str, Any]) -> discord.Embed:
    latest = data.get("latest_reset")
    scheduled = data.get("scheduled_reset")
    watch = data.get("active_watch")
    stats = data.get("stats") or {}

    lines: list[str] = []
    if latest:
        kind = "儲存額度" if latest.get("reset_type") == "banked" else "一般"
        when = discord.utils.format_dt(parse_dt(latest["announced_at"]), "R")
        label = f"[上次重置]({_source_url(latest)})" if _source_url(latest) else "上次重置"
        lines.append(f"{label} {when}（{kind}）")
    else:
        lines.append("尚無重置紀錄")

    total = stats.get("total")
    avg = stats.get("avg_interval_days")
    if total:
        summary = f"累計 {total} 次"
        if avg is not None:
            summary += f" · 平均間隔 {avg:.1f} 天"
        lines.append(summary)

    if scheduled:
        if scheduled.get("scheduled_for"):
            dt = parse_dt(scheduled["scheduled_for"])
            lines.append(f"預告重置 {discord.utils.format_dt(dt, 'F')}")
        else:
            lines.append("預告重置（時間未公布）")
    elif watch:
        level = _WATCH_LEVEL.get(watch.get("level", ""), watch.get("level", ""))
        chance = watch.get("reset_chance_percent")
        lines.append(f"觀察中：{level}" + (f" · 機率 {chance}%" if chance is not None else ""))
        lines.append("-# AI 推測，非官方資訊")
    else:
        days_since = stats.get("days_since_last")
        if avg is not None and days_since is not None:
            lines.append(f"依平均推算約 {max(0.0, avg - days_since):.1f} 天後")
            lines.append("-# 推算值，非官方資訊")

    embed: discord.Embed = factory.build(
        title="Codex 重置狀態",
        description="\n".join(lines),
        color=_COLOR_SCHEDULED,
        author=None,
        footer=FOOTER,
    )
    return embed
