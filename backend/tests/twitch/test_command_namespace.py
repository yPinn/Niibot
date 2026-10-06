"""TwitchIO decorator names must match the shared command namespace."""

from twitch.components.attendance import AttendanceComponent
from twitch.components.channel_info import ChannelInfoComponent
from twitch.components.crosshair import CrosshairComponent
from twitch.components.fortune import FortuneComponent
from twitch.components.games import GamesComponent
from twitch.components.general_commands import GeneralCommandsComponent
from twitch.components.quotes import QuoteComponent
from twitch.components.tarot import TarotComponent
from twitch.components.tft import TftComponent
from twitch.components.video_queue import VideoQueueComponent
from twitch.components.viewer_stats import ViewerStatsComponent

from shared.builtin_commands import BUILTIN_DEFS

_RUNTIME_COMMANDS = [
    GeneralCommandsComponent.help,
    AttendanceComponent.checkin,
    GeneralCommandsComponent.schedule,
    GeneralCommandsComponent.uptime,
    GeneralCommandsComponent.ping,
    GeneralCommandsComponent.delete_own_messages,
    AttendanceComponent.rank,
    VideoQueueComponent.cmd_np,
    ViewerStatsComponent.followage,
    ViewerStatsComponent.subage,
    ViewerStatsComponent.accountage,
    ViewerStatsComponent.bits,
    QuoteComponent.quote,
    GamesComponent.choose,
    FortuneComponent.fortune,
    TarotComponent.tarot,
    GamesComponent.roll,
    CrosshairComponent.xhc,
    TftComponent.tft,
    ChannelInfoComponent.title,
    ChannelInfoComponent.game,
    ChannelInfoComponent.tags,
    ViewerStatsComponent.subcount,
    GeneralCommandsComponent.shoutout,
    ChannelInfoComponent.marker,
    GamesComponent.winner,
    GeneralCommandsComponent.condemn,
]


def test_every_catalog_name_and_alias_matches_the_runtime_decorator() -> None:
    expected = {
        defn["command_name"]: {
            alias.strip() for alias in (defn.get("aliases") or "").split(",") if alias.strip()
        }
        for defn in BUILTIN_DEFS
    }
    actual = {command.name: set(command.aliases) for command in _RUNTIME_COMMANDS}

    assert actual == expected


def test_crosshairs_is_canonical_and_xhc_is_an_alias() -> None:
    assert CrosshairComponent.xhc.name == "crosshairs"
    assert set(CrosshairComponent.xhc.aliases) == {"xhc", "準星"}


def test_help_does_not_expose_unregistered_commands_alias() -> None:
    assert GeneralCommandsComponent.help.name == "help"
    assert set(GeneralCommandsComponent.help.aliases) == {"指令"}
