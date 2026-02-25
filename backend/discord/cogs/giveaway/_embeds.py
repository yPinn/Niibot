"""Embed builders for giveaway announcements and results."""

from __future__ import annotations

from datetime import datetime

import discord


def _apply_embed_chrome(
    embed: discord.Embed,
    *,
    config: dict,
    global_config: dict,
    thumbnail_url: str,
) -> None:
    """Attach author, thumbnail, image, and footer from config."""
    giveaway_author = config.get("embed", {}).get("author", {})
    global_author = global_config.get("author", {})

    author_name = giveaway_author.get("name") or global_author.get("name")
    if author_name:
        author_icon = giveaway_author.get("icon_url") or global_author.get("icon_url") or None
        author_url = giveaway_author.get("url") or global_author.get("url") or None
        embed.set_author(name=author_name, icon_url=author_icon, url=author_url)

    embed.set_thumbnail(url=thumbnail_url)

    image_url = config.get("embed", {}).get("image")
    if image_url:
        embed.set_image(url=image_url)

    giveaway_footer = config.get("embed", {}).get("footer", {})
    global_footer = global_config.get("footer", {})

    footer_text = giveaway_footer.get("text") or global_footer.get("text")
    if footer_text:
        footer_icon = giveaway_footer.get("icon_url") or global_footer.get("icon_url") or None
        embed.set_footer(text=footer_text, icon_url=footer_icon)


def create_giveaway_embed(
    *,
    config: dict,
    global_config: dict,
    host: discord.User | discord.Member,
    prize_name: str,
    prize_count: int,
    description: str | None = None,
    end_time: datetime | None = None,
) -> discord.Embed:
    desc_text = description if description else "點擊下方按鈕參加抽獎"

    embed = discord.Embed(
        title="【抽獎】",
        description=desc_text,
        color=discord.Color.from_str(config["colors"]["active"]),
        timestamp=datetime.now(),
    )

    _apply_embed_chrome(
        embed, config=config, global_config=global_config, thumbnail_url=host.display_avatar.url
    )

    embed.add_field(name="獎品", value=prize_name, inline=True)
    embed.add_field(name="數量", value=f"**{prize_count}** 個", inline=True)
    embed.add_field(name="主持人", value=host.mention, inline=False)

    if end_time:
        time_str = end_time.strftime("%m/%d %H:%M")
        timestamp_unix = int(end_time.timestamp())
        embed.add_field(
            name="截止時間",
            value=f"**{time_str}**   (<t:{timestamp_unix}:R>)",
            inline=False,
        )

    embed.add_field(name="參加人數", value="**0** 人", inline=False)
    return embed


def create_result_embed(
    *,
    config: dict,
    global_config: dict,
    host: discord.Member | None,
    prize_name: str,
    prize_count: int,
    winner_ids: list[int],
    total_participants: int,
    host_avatar_url: str,
) -> discord.Embed:
    win_rate = (len(winner_ids) / total_participants * 100) if total_participants > 0 else 0

    embed = discord.Embed(
        title="【抽獎結果】",
        description=f"恭喜以下 **{len(winner_ids)}** 位得獎者！",
        color=discord.Color.from_str(config["colors"]["ended"]),
        timestamp=datetime.now(),
    )

    _apply_embed_chrome(
        embed, config=config, global_config=global_config, thumbnail_url=host_avatar_url
    )

    embed.add_field(name="獎品", value=prize_name, inline=True)
    embed.add_field(name="數量", value=f"**{prize_count}** 個", inline=True)
    if host:
        embed.add_field(name="主持人", value=host.mention, inline=False)

    winners_list = [f"{idx}. <@{uid}>" for idx, uid in enumerate(winner_ids, 1)]
    embed.add_field(name="得獎名單", value="\n".join(winners_list), inline=False)
    embed.add_field(name="總參加人數", value=f"**{total_participants}** 人", inline=True)
    embed.add_field(name="中獎率", value=f"**{win_rate:.1f}%**", inline=True)
    return embed
