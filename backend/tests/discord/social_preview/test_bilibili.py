"""Tests for Bilibili URL patterns, embed builders, and cog handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.cogs.social_preview import _embeds as embeds_mod
from discord.cogs.social_preview import constants
from discord.cogs.social_preview._embeds import build_bilibili_live_embed
from discord.cogs.social_preview.cog import SocialPreviewCog

from core import EmbedFactory

from ._helpers import SENDER_AVATAR_URL, _make_message

# ===========================================================================
# constants — URL regex patterns
# ===========================================================================


class TestBilibiliRE:
    RE = constants.BILIBILI_RE

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.bilibili.com/video/BV1xx411c7mD",
            "https://bilibili.com/video/BVabcDEF123",
            "https://m.bilibili.com/video/BV1xx411c7mD",
            "https://b23.tv/AbCdEf",
        ],
    )
    def test_matches(self, url: str) -> None:
        assert self.RE.search(url) is not None

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.bilibili.com/",
            "https://www.bilibili.com/video/",
            "https://youtube.com/watch?v=BV1xx411c7mD",
        ],
    )
    def test_no_match(self, url: str) -> None:
        assert self.RE.search(url) is None

    def test_captures_bvid_from_full_url(self) -> None:
        m = self.RE.search("https://www.bilibili.com/video/BV1xx411c7mD")
        assert m is not None
        assert m.group(1) == "BV1xx411c7mD"

    def test_short_url_group1_is_none(self) -> None:
        m = self.RE.search("https://b23.tv/AbCdEf")
        assert m is not None
        assert m.group(1) is None


class TestBilibiliSpaceRegex:
    RE = constants.BILIBILI_SPACE_RE

    def test_matches(self) -> None:
        assert self.RE.search("https://space.bilibili.com/12345678") is not None

    def test_captures_mid(self) -> None:
        m = self.RE.search("https://space.bilibili.com/12345678")
        assert m is not None
        assert m.group(1) == "12345678"

    def test_no_match_on_video_url(self) -> None:
        assert self.RE.search("https://www.bilibili.com/video/BV1xx") is None


class TestBilibiliLiveRE:
    RE = constants.BILIBILI_LIVE_RE

    @pytest.mark.parametrize(
        "url",
        [
            "https://live.bilibili.com/10000001",
            "http://live.bilibili.com/10000001",
            "https://live.bilibili.com/10000001?live_from=71002&visit_id=abc123",
        ],
    )
    def test_matches(self, url: str) -> None:
        assert self.RE.search(url) is not None

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.bilibili.com/video/BV1xx411c7mD",
            "https://space.bilibili.com/12345",
            "https://live.bilibili.com/",
            "https://notbilibili.com/live/123",
        ],
    )
    def test_no_match(self, url: str) -> None:
        assert self.RE.search(url) is None

    def test_captures_room_id(self) -> None:
        m = self.RE.search("https://live.bilibili.com/10000001?live_from=71002")
        assert m is not None
        assert m.group(1) == "10000001"


# ===========================================================================
# _embeds — Bilibili embed builders
# ===========================================================================


class TestBuildBilibiliEmbed:
    def _data(self) -> dict:
        return {
            "title": "My Video",
            "desc": "A description",
            "pic": "https://img.com/v.jpg",
            "owner": {"mid": 12345, "name": "Creator", "face": "https://img.com/avatar.jpg"},
            "stat": {"view": 1000, "like": 500, "coin": 100, "favorite": 200, "share": 50},
        }

    def test_title_set(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert embed.title == "My Video"

    def test_author_name_from_owner(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert embed.author.name == "Creator"

    def test_author_url_links_to_space(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert embed.author.url == "https://space.bilibili.com/12345"

    def test_author_url_absent_when_no_mid(self, embed_factory: EmbedFactory) -> None:
        data = self._data()
        data["owner"] = {"name": "Creator", "face": "https://img.com/avatar.jpg"}
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, data, "https://bilibili.com/video/BV1x"
        )
        assert not embed.author.url

    def test_metrics_layout(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert len(embed.fields) == 6
        assert embed.fields[0].name == "播放"
        assert embed.fields[0].inline
        assert embed.fields[1].name == "分享"
        assert embed.fields[1].inline
        assert embed.fields[2].name == "​"
        assert embed.fields[2].inline
        assert embed.fields[3].name == "點讚"
        assert embed.fields[3].inline
        assert embed.fields[4].name == "投幣"
        assert embed.fields[4].inline
        assert embed.fields[5].name == "收藏"
        assert embed.fields[5].inline

    def test_view_count_uses_compact_format(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert embed.fields[0].value == "1.0K"

    def test_share_absent_when_zero(self, embed_factory: EmbedFactory) -> None:
        data = self._data()
        data["stat"]["share"] = 0
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, data, "https://bilibili.com/video/BV1x"
        )
        assert all(f.name != "分享" for f in embed.fields)

    def test_no_metrics_field_when_stat_empty(self, embed_factory: EmbedFactory) -> None:
        data = self._data()
        data["stat"] = {}
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, data, "https://bilibili.com/video/BV1x"
        )
        assert len(embed.fields) == 0

    def test_desc_equals_title_suppresses_description(self, embed_factory: EmbedFactory) -> None:
        data = self._data()
        data["desc"] = "My Video"
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, data, "https://bilibili.com/video/BV1x"
        )
        assert embed.description is None

    def test_footer_defers_to_factory(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert embed.footer.text != "Bilibili"

    def test_image_set(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert embed.image.url == "https://img.com/v.jpg"

    def test_sender_avatar_set_as_thumbnail(self, embed_factory: EmbedFactory) -> None:
        avatar = "https://cdn.discordapp.com/avatars/1/abc.png"
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x", sender_avatar_url=avatar
        )
        assert embed.thumbnail.url == avatar

    def test_no_thumbnail_when_sender_avatar_omitted(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_embed(
            embed_factory, self._data(), "https://bilibili.com/video/BV1x"
        )
        assert not embed.thumbnail.url


class TestBuildBilibiliSpaceEmbed:
    _SPACE_URL = "https://space.bilibili.com/12345678"

    def _data(self) -> dict:
        return {
            "card": {
                "mid": "12345678",
                "name": "Test User",
                "face": "https://img.com/avatar.jpg",
                "sign": "A short bio.",
                "fans": 79803,
                "attention": 743,
            },
            "archive_count": 275,
        }

    def test_no_title(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_space_embed(embed_factory, self._data(), self._SPACE_URL)
        assert embed.title is None

    def test_author_name_and_icon(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_space_embed(embed_factory, self._data(), self._SPACE_URL)
        assert embed.author.name == "Test User"
        assert embed.author.icon_url == "https://img.com/avatar.jpg"
        assert embed.author.url == self._SPACE_URL

    def test_description_is_sign(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_space_embed(embed_factory, self._data(), self._SPACE_URL)
        assert "bio" in embed.description

    def test_stats_fields(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_space_embed(embed_factory, self._data(), self._SPACE_URL)
        names = [f.name for f in embed.fields]
        assert "粉絲" in names
        assert "關注" in names
        assert "影片" in names

    def test_fans_compact_format(self, embed_factory: EmbedFactory) -> None:
        embed = embeds_mod.build_bilibili_space_embed(embed_factory, self._data(), self._SPACE_URL)
        fans_field = next(f for f in embed.fields if f.name == "粉絲")
        assert fans_field.value == "79.8K"


class TestBuildBilibiliLiveEmbed:
    _ROOM_URL = "https://live.bilibili.com/10000001"

    def _room(self, **overrides: object) -> dict:
        base: dict = {
            "uid": 12300001,
            "room_id": 10000001,
            "title": "Test Stream Title",
            "live_status": 1,
            "online": 10000,
            "attention": 100000,
            "area_name": "英雄聯盟",
            "parent_area_name": "遊戲",
            "live_time": "2026-04-20 20:30:00",
            "user_cover": "https://i2.hdslb.com/bfs/live/cover.jpg",
            "keyframe": "https://i2.hdslb.com/bfs/live/keyframe.jpg",
        }
        base.update(overrides)
        return base

    def _card_data(self) -> dict:
        return {
            "card": {
                "mid": "12300001",
                "name": "TestStreamer",
                "face": "https://i2.hdslb.com/bfs/face/avatar.jpg",
            }
        }

    def test_title_set(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(), self._card_data(), self._ROOM_URL
        )
        assert embed.title == "Test Stream Title"

    def test_status_field_live(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=1), self._card_data(), self._ROOM_URL
        )
        assert next(f for f in embed.fields if f.name == "狀態").value == "直播中"

    def test_status_field_offline(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=0), self._card_data(), self._ROOM_URL
        )
        assert next(f for f in embed.fields if f.name == "狀態").value == "下播"

    def test_status_field_rotating(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=2), self._card_data(), self._ROOM_URL
        )
        assert next(f for f in embed.fields if f.name == "狀態").value == "輪播"

    def test_area_field(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(), self._card_data(), self._ROOM_URL
        )
        assert next(f for f in embed.fields if f.name == "分類").value == "英雄聯盟"

    def test_viewer_count_only_when_live(self, embed_factory: EmbedFactory) -> None:
        live_embed = build_bilibili_live_embed(
            embed_factory,
            self._room(live_status=1, online=10000),
            self._card_data(),
            self._ROOM_URL,
        )
        offline_embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=0, online=0), self._card_data(), self._ROOM_URL
        )
        assert any(f.name == "觀看人數" for f in live_embed.fields)
        assert not any(f.name == "觀看人數" for f in offline_embed.fields)

    def test_viewer_count_compact_format(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory,
            self._room(live_status=1, online=10000),
            self._card_data(),
            self._ROOM_URL,
        )
        assert next(f for f in embed.fields if f.name == "觀看人數").value == "10.0K"

    def test_keyframe_used_as_image_when_live(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=1), self._card_data(), self._ROOM_URL
        )
        assert embed.image.url == "https://i2.hdslb.com/bfs/live/keyframe.jpg"

    def test_user_cover_used_when_offline(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=0), self._card_data(), self._ROOM_URL
        )
        assert embed.image.url == "https://i2.hdslb.com/bfs/live/cover.jpg"

    def test_author_name_from_card(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(), self._card_data(), self._ROOM_URL
        )
        assert embed.author.name == "TestStreamer"

    def test_author_url_links_to_space(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(), self._card_data(), self._ROOM_URL
        )
        assert embed.author.url == "https://space.bilibili.com/12300001"

    def test_no_card_data_still_builds(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(embed_factory, self._room(), None, self._ROOM_URL)
        assert isinstance(embed, discord.Embed)
        assert embed.author.name is None

    def test_area_falls_back_to_parent(self, embed_factory: EmbedFactory) -> None:
        room = self._room()
        del room["area_name"]
        embed = build_bilibili_live_embed(embed_factory, room, None, self._ROOM_URL)
        area = next((f for f in embed.fields if f.name == "分類"), None)
        assert area is not None
        assert area.value == "遊戲"

    def test_no_area_field_when_absent(self, embed_factory: EmbedFactory) -> None:
        room = self._room()
        del room["area_name"]
        del room["parent_area_name"]
        embed = build_bilibili_live_embed(embed_factory, room, None, self._ROOM_URL)
        assert not any(f.name == "分類" for f in embed.fields)

    # ── 開播時間 ────────────────────────────────────────────────────────────────

    def test_live_time_shown_when_live(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory,
            self._room(live_status=1, live_time="2026-04-20 20:30:00"),
            self._card_data(),
            self._ROOM_URL,
        )
        assert any(f.name == "開播時間" for f in embed.fields)
        assert next(f for f in embed.fields if f.name == "開播時間").value == "20:30"

    def test_live_time_absent_when_offline(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory,
            self._room(live_status=0, live_time="0000-00-00 00:00:00"),
            self._card_data(),
            self._ROOM_URL,
        )
        assert not any(f.name == "開播時間" for f in embed.fields)

    def test_live_time_zero_sentinel_ignored(self, embed_factory: EmbedFactory) -> None:
        """live_time="0000-00-00 00:00:00" (offline sentinel) must not appear even when live."""
        embed = build_bilibili_live_embed(
            embed_factory,
            self._room(live_status=1, live_time="0000-00-00 00:00:00"),
            self._card_data(),
            self._ROOM_URL,
        )
        assert not any(f.name == "開播時間" for f in embed.fields)

    # ── 關注數 ──────────────────────────────────────────────────────────────────

    def test_attention_shown_when_live(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory,
            self._room(live_status=1, attention=100000),
            self._card_data(),
            self._ROOM_URL,
        )
        assert any(f.name == "關注" for f in embed.fields)
        assert next(f for f in embed.fields if f.name == "關注").value == "100.0K"

    def test_attention_shown_when_offline(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory,
            self._room(live_status=0, attention=100000),
            self._card_data(),
            self._ROOM_URL,
        )
        assert any(f.name == "關注" for f in embed.fields)

    def test_attention_absent_when_zero(self, embed_factory: EmbedFactory) -> None:
        embed = build_bilibili_live_embed(
            embed_factory, self._room(attention=0), self._card_data(), self._ROOM_URL
        )
        assert not any(f.name == "關注" for f in embed.fields)

    # ── Field grid layout ───────────────────────────────────────────────────────

    def test_live_full_layout_is_six_fields(self, embed_factory: EmbedFactory) -> None:
        """Row1: 狀態|分類|觀看人數  Row2: 開播時間|關注|spacer = 6 fields."""
        embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=1), self._card_data(), self._ROOM_URL
        )
        assert len(embed.fields) == 6
        assert embed.fields[5].name == "​"

    def test_offline_full_layout_is_three_fields(self, embed_factory: EmbedFactory) -> None:
        """Row1: 狀態|分類|關注 = 3 fields, no spacer needed."""
        embed = build_bilibili_live_embed(
            embed_factory, self._room(live_status=0), self._card_data(), self._ROOM_URL
        )
        assert len(embed.fields) == 3
        assert not any(f.name == "​" for f in embed.fields)


# ===========================================================================
# cog — _handle_bilibili / _handle_bilibili_live (mocked HTTP)
# ===========================================================================


class TestCogBilibili:
    """The video handler now delegates to shared.bilibili_client; patch that."""

    _VIDEO_DATA = {
        "bvid": "BV1xx411c7mD",
        "title": "My BV Video",
        "desc": "Some description",
        "pic": "https://img.com/v.jpg",
        "owner": {"name": "Uploader", "face": "https://img.com/a.jpg"},
        "stat": {"view": 5000, "like": 200, "coin": 50, "favorite": 100},
    }

    @staticmethod
    def _patch_client(return_value):
        return patch(
            "discord.cogs.social_preview.cog.fetch_bilibili_video_data",
            AsyncMock(return_value=return_value),
        )

    @pytest.mark.asyncio
    async def test_sends_embed_on_success(self, cog: SocialPreviewCog) -> None:
        msg = _make_message("https://www.bilibili.com/video/BV1xx411c7mD")
        with self._patch_client(self._VIDEO_DATA):
            await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.title == "My BV Video"

    @pytest.mark.asyncio
    async def test_no_send_when_client_returns_none(self, cog: SocialPreviewCog) -> None:
        msg = _make_message("https://www.bilibili.com/video/BV1xx411c7mD")
        with self._patch_client(None):
            await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deletes_original_message(self, cog: SocialPreviewCog) -> None:
        msg = _make_message("https://www.bilibili.com/video/BV1xx411c7mD")
        with self._patch_client(self._VIDEO_DATA):
            await cog.on_message(msg)
        msg.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_embed_thumbnail_is_sender_avatar(self, cog: SocialPreviewCog) -> None:
        msg = _make_message("https://www.bilibili.com/video/BV1xx411c7mD")
        with self._patch_client(self._VIDEO_DATA):
            await cog.on_message(msg)
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.thumbnail.url == SENDER_AVATAR_URL


class TestCogBilibiliLive:
    def _live_api_resp(self, **overrides: object) -> MagicMock:
        room: dict = {
            "uid": 12300001,
            "room_id": 10000001,
            "title": "Test Stream Title",
            "live_status": 1,
            "online": 10000,
            "attention": 100000,
            "area_name": "英雄聯盟",
            "live_time": "2026-04-20 20:30:00",
            "user_cover": "https://i2.hdslb.com/bfs/live/cover.jpg",
            "keyframe": "https://i2.hdslb.com/bfs/live/keyframe.jpg",
        }
        room.update(overrides)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"code": 0, "data": room})
        return resp

    def _card_api_resp(self) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(
            return_value={
                "code": 0,
                "data": {
                    "card": {
                        "mid": "12300001",
                        "name": "TestStreamer",
                        "face": "https://i2.hdslb.com/bfs/face/avatar.jpg",
                    }
                },
            }
        )
        return resp

    @pytest.mark.asyncio
    async def test_sends_embed_on_success(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(side_effect=[self._live_api_resp(), self._card_api_resp()])
        msg = _make_message("https://live.bilibili.com/10000001")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.title == "Test Stream Title"

    @pytest.mark.asyncio
    async def test_share_url_with_query_params(self, cog: SocialPreviewCog) -> None:
        """URLs with ?live_from=...&visit_id=... are matched and room_id extracted correctly."""
        cog._http.get = AsyncMock(side_effect=[self._live_api_resp(), self._card_api_resp()])
        msg = _make_message("https://live.bilibili.com/10000001?live_from=71002&visit_id=abc123def")
        await cog.on_message(msg)
        msg.channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deletes_original_message(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(side_effect=[self._live_api_resp(), self._card_api_resp()])
        msg = _make_message("https://live.bilibili.com/10000001")
        await cog.on_message(msg)
        msg.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_embed_still_sent_when_card_api_fails(self, cog: SocialPreviewCog) -> None:
        """Card API failure degrades gracefully — embed sent without author name."""
        card_err = MagicMock()
        card_err.raise_for_status = MagicMock(side_effect=Exception("timeout"))
        cog._http.get = AsyncMock(side_effect=[self._live_api_resp(), card_err])
        msg = _make_message("https://live.bilibili.com/10000001")
        await cog.on_message(msg)

        msg.channel.send.assert_awaited_once()
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.author.name is None

    @pytest.mark.asyncio
    async def test_no_send_on_live_api_error(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(side_effect=Exception("timeout"))
        msg = _make_message("https://live.bilibili.com/10000001")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_send_on_api_error_code(self, cog: SocialPreviewCog) -> None:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"code": -404, "data": None})
        cog._http.get = AsyncMock(return_value=resp)
        msg = _make_message("https://live.bilibili.com/10000001")
        await cog.on_message(msg)
        msg.channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_embed_thumbnail_is_sender_avatar(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(side_effect=[self._live_api_resp(), self._card_api_resp()])
        msg = _make_message("https://live.bilibili.com/10000001")
        await cog.on_message(msg)
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert embed.thumbnail.url == SENDER_AVATAR_URL

    @pytest.mark.asyncio
    async def test_offline_room_embed(self, cog: SocialPreviewCog) -> None:
        cog._http.get = AsyncMock(
            side_effect=[self._live_api_resp(live_status=0, online=0), self._card_api_resp()]
        )
        msg = _make_message("https://live.bilibili.com/10000001")
        await cog.on_message(msg)

        embed = msg.channel.send.call_args.kwargs["embed"]
        status = next(f for f in embed.fields if f.name == "狀態")
        assert status.value == "下播"
        assert not any(f.name == "觀看人數" for f in embed.fields)
