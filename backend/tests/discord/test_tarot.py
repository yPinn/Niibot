"""Discord Tarot integration with the local versioned deck catalog."""

from __future__ import annotations

from types import SimpleNamespace

from cogs import tarot as tarot_module


def test_discord_tarot_uses_versioned_frontend_asset_url(monkeypatch) -> None:
    monkeypatch.setattr(
        tarot_module,
        "get_settings",
        lambda: SimpleNamespace(frontend_url="https://niibot.tv/"),
        raising=False,
    )
    cog = tarot_module.TarotCog.__new__(tarot_module.TarotCog)

    cog._load_data()

    assert cog._card_image_url("0") == (
        "https://niibot.tv/images/tarot/decks/rider-waite-smith-pkt/v1/cards/major-00-the-fool.jpg"
    )
