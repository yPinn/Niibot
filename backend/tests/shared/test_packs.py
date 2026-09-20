"""Tests for the directory-based pack loader and matcher."""

from __future__ import annotations

from pathlib import Path

from shared.packs import (
    Pack,
    PackEntry,
    load_packs,
    match_entries,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_pack_md(pack_dir: Path, *, pack_id: str, name: str, description: str = "") -> None:
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "PACK.md").write_text(
        f"---\nid: {pack_id}\nname: {name}\ndescription: {description}\n---\n",
        encoding="utf-8",
    )


def _write_entry(path: Path, *, keys: str, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nkeys: {keys}\n---\n\n{content}\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Loader: flat pack
# ---------------------------------------------------------------------------


def test_load_flat_pack_with_entries(tmp_path):
    data_dir = tmp_path
    pack_dir = data_dir / "packs" / "demo"
    _write_pack_md(pack_dir, pack_id="demo", name="Demo Pack", description="d")
    _write_entry(pack_dir / "kappa.md", keys="kappa, kappapride", content="Kappa lore")
    _write_entry(pack_dir / "pog.md", keys="pog, poggers", content="Pog lore")

    packs = load_packs(data_dir)

    assert "demo" in packs
    pack = packs["demo"]
    assert pack.name == "Demo Pack"
    assert pack.description == "d"
    assert len(pack.entries) == 2
    by_path = {e.path: e for e in pack.entries}
    assert by_path[("kappa",)].keys == ["kappa", "kappapride"]
    assert by_path[("kappa",)].content == "Kappa lore"
    assert by_path[("pog",)].keys == ["pog", "poggers"]


def test_load_skips_pack_md_as_entry(tmp_path):
    """PACK.md itself must not appear in entries even if it has a keys: line."""
    data_dir = tmp_path
    pack_dir = data_dir / "packs" / "demo"
    _write_pack_md(pack_dir, pack_id="demo", name="Demo")
    _write_entry(pack_dir / "real_entry.md", keys="x", content="x content")

    packs = load_packs(data_dir)

    paths = {e.path for e in packs["demo"].entries}
    assert ("real_entry",) in paths
    assert ("PACK",) not in paths


def test_entry_without_keys_is_skipped(tmp_path):
    data_dir = tmp_path
    pack_dir = data_dir / "packs" / "demo"
    _write_pack_md(pack_dir, pack_id="demo", name="Demo")
    # entry with no frontmatter -> no keys -> skipped
    (pack_dir / "stub.md").write_text("just prose, no frontmatter", encoding="utf-8")
    _write_entry(pack_dir / "good.md", keys="g", content="good")

    packs = load_packs(data_dir)

    paths = {e.path for e in packs["demo"].entries}
    assert paths == {("good",)}


# ---------------------------------------------------------------------------
# Loader: nested pack
# ---------------------------------------------------------------------------


def test_load_nested_pack_paths(tmp_path):
    data_dir = tmp_path
    pack_dir = data_dir / "packs" / "xd"
    _write_pack_md(pack_dir, pack_id="xd", name="XD")
    _write_entry(pack_dir / "基本資料.md", keys="basic", content="basic info")
    _write_entry(pack_dir / "核心人物" / "羅傑.md", keys="roger, 羅傑", content="roger detail")
    _write_entry(pack_dir / "核心人物" / "NL.md", keys="nl, never_loses", content="nl detail")

    packs = load_packs(data_dir)

    by_path = {e.path: e for e in packs["xd"].entries}
    assert ("基本資料",) in by_path
    assert ("核心人物", "羅傑") in by_path
    assert ("核心人物", "NL") in by_path
    assert by_path[("核心人物", "羅傑")].content == "roger detail"


def test_pack_without_pack_md_is_skipped(tmp_path):
    data_dir = tmp_path
    pack_dir = data_dir / "packs" / "broken"
    pack_dir.mkdir(parents=True)
    _write_entry(pack_dir / "x.md", keys="x", content="x")

    packs = load_packs(data_dir)

    assert "broken" not in packs


def test_missing_id_falls_back_to_dir_name(tmp_path):
    data_dir = tmp_path
    pack_dir = data_dir / "packs" / "fallback_id"
    pack_dir.mkdir(parents=True)
    (pack_dir / "PACK.md").write_text("---\nname: Fallback\n---\n", encoding="utf-8")
    _write_entry(pack_dir / "x.md", keys="x", content="x")

    packs = load_packs(data_dir)

    assert "fallback_id" in packs
    assert packs["fallback_id"].name == "Fallback"


def test_non_directory_at_packs_root_is_ignored(tmp_path):
    data_dir = tmp_path
    packs_root = data_dir / "packs"
    packs_root.mkdir()
    # stray flat file at packs root — should be ignored (old format no longer supported)
    (packs_root / "old_flat.md").write_text(
        "---\nid: old\nname: Old\n---\n## x\nkeys: x\nx\n", encoding="utf-8"
    )
    # valid dir alongside
    pack_dir = packs_root / "new"
    _write_pack_md(pack_dir, pack_id="new", name="New")
    _write_entry(pack_dir / "e.md", keys="e", content="e")

    packs = load_packs(data_dir)

    assert "old" not in packs
    assert "new" in packs


# ---------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------


def _pack(pack_id: str, name: str, entries: list[PackEntry]) -> Pack:
    return Pack(id=pack_id, name=name, description="", entries=entries)


def test_match_uses_word_boundary():
    """Short keys like 'w' must not match inside 'kekw'."""
    pack = _pack(
        "demo",
        "Demo",
        [
            PackEntry(keys=["w"], content="w content", path=("w",)),
            PackEntry(keys=["kekw"], content="kekw content", path=("kekw",)),
        ],
    )

    # only "kekw" appears, not standalone "w" → only kekw matches
    results = match_entries({"demo": pack}, ["demo"], "look at this kekw lol")
    contents = [r[1] for r in results]
    assert "kekw content" in contents
    assert "w content" not in contents


def test_match_includes_path_in_display_name():
    """Matched display label is 'pack.name / path/parts' so LLM gets breadcrumb."""
    pack = _pack(
        "xd",
        "XD Ent",
        [
            PackEntry(keys=["roger"], content="roger detail", path=("核心人物", "羅傑")),
            PackEntry(keys=["basic"], content="basic info", path=("基本資料",)),
        ],
    )

    results = match_entries({"xd": pack}, ["xd"], "tell me about roger please")
    display_names = [r[0] for r in results]
    assert "XD Ent / 核心人物 / 羅傑" in display_names


def test_match_respects_enabled_pack_order():
    a = _pack("a", "A", [PackEntry(keys=["foo"], content="A foo", path=("foo",))])
    b = _pack("b", "B", [PackEntry(keys=["foo"], content="B foo", path=("foo",))])

    results = match_entries({"a": a, "b": b}, ["b", "a"], "talk about foo")

    # Order follows enabled_ids: b first, a second
    assert [r[1] for r in results] == ["B foo", "A foo"]


def test_disabled_pack_is_not_matched():
    a = _pack("a", "A", [PackEntry(keys=["foo"], content="A foo", path=("foo",))])

    results = match_entries({"a": a}, [], "foo")

    assert results == []


def test_match_cjk_key_uses_substring_not_word_boundary():
    """Chinese keys must match even when adjacent to other Chinese chars
    (re.\\b only fires on ASCII word transitions)."""
    pack = _pack(
        "xd",
        "XD",
        [PackEntry(keys=["羅傑"], content="roger detail", path=("核心人物", "羅傑"))],
    )

    results = match_entries({"xd": pack}, ["xd"], "請問羅傑是誰?")

    assert any("roger detail" in c for _, c in results)


def test_ascii_key_matches_when_adjacent_to_cjk_but_not_inside_ascii_word():
    pack = _pack(
        "xd",
        "XD",
        [PackEntry(keys=["roger"], content="roger detail", path=("people", "roger"))],
    )

    assert match_entries({"xd": pack}, ["xd"], "誰是Roger？")
    assert match_entries({"xd": pack}, ["xd"], "Roger是誰？")
    assert match_entries({"xd": pack}, ["xd"], "progername") == []
