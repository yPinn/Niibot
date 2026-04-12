"""Unit tests for discord.cogs.giveaway._persistence.GiveawayPersistence.

Imports the module directly via importlib to avoid triggering the full
discord-bot import chain (which requires a live discord.py environment).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

# Load _persistence.py directly without going through the cog package chain
_MODULE_PATH = (
    Path(__file__).parent.parent.parent / "discord" / "cogs" / "giveaway" / "_persistence.py"
)
_spec = importlib.util.spec_from_file_location("giveaway_persistence", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
GiveawayPersistence = _mod.GiveawayPersistence

_SAMPLE_DATA: dict[int, dict] = {
    111: {"prize_name": "Steam key", "participants": [1, 2, 3]},
    222: {"prize_name": "Nitro", "participants": []},
}


# ---------------------------------------------------------------------------
# load() — synchronous
# ---------------------------------------------------------------------------


class TestLoad:
    def test_missing_file_returns_empty_dict(self, tmp_path: Path):
        p = GiveawayPersistence(tmp_path / "does_not_exist.json")
        assert p.load() == {}

    def test_valid_file_returns_data(self, tmp_path: Path):
        fp = tmp_path / "active.json"
        fp.write_text(json.dumps({"111": {"prize_name": "key"}}), encoding="utf-8")
        p = GiveawayPersistence(fp)
        result = p.load()
        assert result == {111: {"prize_name": "key"}}

    def test_string_keys_are_converted_to_int(self, tmp_path: Path):
        fp = tmp_path / "active.json"
        fp.write_text(json.dumps({"99": {}, "42": {}}), encoding="utf-8")
        p = GiveawayPersistence(fp)
        result = p.load()
        assert all(isinstance(k, int) for k in result)

    def test_corrupt_json_returns_empty_dict(self, tmp_path: Path):
        fp = tmp_path / "active.json"
        fp.write_text("not valid json {{{", encoding="utf-8")
        p = GiveawayPersistence(fp)
        assert p.load() == {}

    def test_empty_file_returns_empty_dict(self, tmp_path: Path):
        fp = tmp_path / "active.json"
        fp.write_text("", encoding="utf-8")
        p = GiveawayPersistence(fp)
        assert p.load() == {}


# ---------------------------------------------------------------------------
# save() — asynchronous, non-blocking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSave:
    async def test_creates_file_with_correct_content(self, tmp_path: Path):
        fp = tmp_path / "active.json"
        p = GiveawayPersistence(fp)

        await p.save(_SAMPLE_DATA)

        saved = json.loads(fp.read_text(encoding="utf-8"))
        # Keys are serialised as strings in JSON
        assert saved == {str(k): v for k, v in _SAMPLE_DATA.items()}

    async def test_overwrites_existing_file(self, tmp_path: Path):
        fp = tmp_path / "active.json"
        fp.write_text(json.dumps({"999": {"old": True}}), encoding="utf-8")
        p = GiveawayPersistence(fp)

        await p.save({1: {"new": True}})

        saved = json.loads(fp.read_text(encoding="utf-8"))
        assert "999" not in saved
        assert saved == {"1": {"new": True}}

    async def test_save_empty_dict(self, tmp_path: Path):
        fp = tmp_path / "active.json"
        p = GiveawayPersistence(fp)

        await p.save({})

        saved = json.loads(fp.read_text(encoding="utf-8"))
        assert saved == {}

    async def test_roundtrip_load_after_save(self, tmp_path: Path):
        fp = tmp_path / "active.json"
        p = GiveawayPersistence(fp)

        await p.save(_SAMPLE_DATA)
        result = p.load()

        assert result == _SAMPLE_DATA

    async def test_save_does_not_mutate_input(self, tmp_path: Path):
        """save() takes a snapshot, so modifying the dict after call has no effect."""
        fp = tmp_path / "active.json"
        p = GiveawayPersistence(fp)
        data = {1: {"prize": "A"}}

        await p.save(data)
        data[1]["prize"] = "MUTATED"  # mutate after save

        saved = json.loads(fp.read_text(encoding="utf-8"))
        assert saved["1"]["prize"] == "A"

    async def test_atomic_write_leaves_no_temp_file(self, tmp_path: Path):
        """_write_json must use os.replace so no .tmp file is left after a successful write."""
        fp = tmp_path / "active.json"
        p = GiveawayPersistence(fp)

        await p.save({1: {"prize": "atomictest"}})

        leftover_tmps = list(tmp_path.glob("*.tmp"))
        assert leftover_tmps == [], f"Unexpected temp files: {leftover_tmps}"
        assert fp.exists()

    async def test_final_file_is_valid_json_after_save(self, tmp_path: Path):
        """The destination file must always be parseable JSON (never truncated)."""
        fp = tmp_path / "active.json"
        p = GiveawayPersistence(fp)
        data = {i: {"prize": f"item_{i}", "participants": list(range(i))} for i in range(50)}

        await p.save(data)

        content = fp.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert len(parsed) == 50
