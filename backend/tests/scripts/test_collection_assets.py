"""Tests for the catalog-driven check-in collection artwork pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageCms
from PIL.PngImagePlugin import PngInfo
from scripts.assets import collections as cli


def _config(tmp_path: Path, **overrides: object) -> cli.AssetBuildConfig:
    values: dict[str, object] = {
        "action": "build",
        "catalog_path": tmp_path / "catalog.json",
        "source_root": tmp_path / "originals",
        "output_dir": tmp_path / "generated",
        "output_width": 10,
        "output_height": 15,
        "quality": 85,
        "method": 6,
        "max_pixels": 1_000_000,
        "crop_warning_fraction": 0.18,
        "upscale_warning_factor": 1.15,
    }
    values.update(overrides)
    return cli.AssetBuildConfig(**values)


def _card(
    *,
    key: str = "ka-01",
    source: str = "ka1.png",
    revision: int = 1,
    display_name: str | None = None,
    mode: str = "cover",
    x: float = 0.5,
    y: float = 0.5,
) -> dict[str, Any]:
    return {
        "key": key,
        "source": source,
        "revision": revision,
        "display_name": display_name,
        "crop": {"mode": mode, "focal_point": {"x": x, "y": y}},
    }


def _write_catalog(
    config: cli.AssetBuildConfig,
    cards: list[dict[str, Any]],
    *,
    collection_key: str = "aespa",
    collection_display_name: str | None = "aespa",
) -> None:
    config.catalog_path.parent.mkdir(parents=True, exist_ok=True)
    config.catalog_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "collections": [
                    {
                        "key": collection_key,
                        "display_name": collection_display_name,
                        "cards": cards,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _save_png(
    path: Path,
    size: tuple[int, int] = (20, 30),
    *,
    alpha: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "RGBA" if alpha else "RGB"
    color = (28, 92, 166, 0 if alpha else 255) if alpha else (28, 92, 166)
    image = Image.new(mode, size, color)
    if alpha:
        image.putpixel((size[0] - 1, size[1] - 1), (210, 140, 80, 255))
    image.save(path, format="PNG")


def _save_jpeg(path: Path, size: tuple[int, int], *, orientation: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, (180, 80, 40))
    exif = Image.Exif()
    exif[274] = orientation
    exif[315] = "metadata must not reach the derivative"
    image.save(path, format="JPEG", quality=95, exif=exif)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_catalog_keeps_display_text_separate_from_lowercase_machine_paths(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    _write_catalog(
        config,
        [_card(display_name="Karina #01")],
        collection_key="le-sserafim",
        collection_display_name="LE SSERAFIM",
    )
    _save_png(config.source_root / "le-sserafim" / "ka1.png")

    catalog = cli.load_catalog(config)

    assert catalog.collections[0].display_name == "LE SSERAFIM"
    assert catalog.cards[0].display_name == "Karina #01"
    assert catalog.cards[0].source_path == config.source_root / "le-sserafim" / "ka1.png"
    assert catalog.cards[0].output_relative_path == Path("le-sserafim/ka-01-r1.webp")


def test_repository_catalog_lists_every_source_file_exactly_once(tmp_path: Path) -> None:
    source_root = cli.REPO_ROOT / "artwork" / "collections"
    config = _config(
        tmp_path,
        catalog_path=source_root / "catalog.json",
        source_root=source_root,
    )

    catalog = cli.load_catalog(config)

    listed = {card.source_path.relative_to(source_root).as_posix() for card in catalog.cards}
    actual = {
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    }
    assert len(catalog.cards) == 48
    assert listed == actual


def test_repository_catalog_uses_member_stage_names_for_card_identity(
    tmp_path: Path,
) -> None:
    source_root = cli.REPO_ROOT / "artwork" / "collections"
    config = _config(
        tmp_path,
        catalog_path=source_root / "catalog.json",
        source_root=source_root,
    )
    expected_members = {
        "aespa": {"karina": ("Karina", 5), "winter": ("Winter", 4)},
        "bts": {"jungkook": ("Jungkook", 3), "v": ("V", 5)},
        "itzy": {"yuna": ("Yuna", 3)},
        "ive": {
            "leeseo": ("Leeseo", 1),
            "liz": ("Liz", 4),
            "rei": ("Rei", 2),
            "wonyoung": ("Wonyoung", 4),
        },
        "le-sserafim": {"chaewon": ("Chaewon", 3)},
        "nmixx": {"haewon": ("Haewon", 5), "sullyoon": ("Sullyoon", 4)},
        "uc": {"eunha": ("Eunha", 5)},
    }

    catalog = cli.load_catalog(config)
    collections = {collection.key: collection for collection in catalog.collections}

    assert set(collections) == set(expected_members)
    assert collections["uc"].display_name is None
    for collection_key, expected in expected_members.items():
        cards = collections[collection_key].cards
        grouped: dict[str, list[cli.CatalogCard]] = {}
        for card in cards:
            member_key, separator, sequence = card.key.rpartition("-")
            assert separator == "-"
            assert len(sequence) == 2 and sequence.isdigit()
            assert card.source_path.stem == card.key
            grouped.setdefault(member_key, []).append(card)

        actual = {
            member_key: (member_cards[0].display_name, len(member_cards))
            for member_key, member_cards in grouped.items()
        }
        assert actual == expected
        for member_key, (display_name, _) in expected.items():
            assert all(card.display_name == display_name for card in grouped[member_key])


def test_preview_uses_focal_cover_without_distortion_or_touching_source(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, action="preview")
    _write_catalog(config, [_card(x=1.0)])
    source = config.source_root / "aespa" / "ka1.png"
    source.parent.mkdir(parents=True)
    image = Image.new("RGB", (30, 30), "red")
    for x in range(10, 30):
        for y in range(30):
            image.putpixel((x, y), (0, 0, 255))
    image.save(source)
    source_hash = _sha256(source)

    report = cli.build_collection_assets(config)

    assert report.created == 1
    assert report.unchanged is False
    assert _sha256(source) == source_hash
    output = config.output_dir / "aespa" / "ka-01-r1.webp"
    with Image.open(output) as derivative:
        assert derivative.size == (10, 15)
        red, green, blue = derivative.convert("RGB").getpixel((5, 7))
        assert blue > 200
        assert red < 30
        assert green < 30
    assert (config.output_dir / "aespa" / "contact-sheet.jpg").is_file()
    preview = json.loads((config.output_dir / "preview-report.json").read_text("utf-8"))
    assert preview["cards"]["aespa/ka-01-r1.webp"]["crop_box"] == [10, 0, 30, 30]


def test_contain_preserves_the_whole_image_with_transparent_padding(tmp_path: Path) -> None:
    config = _config(tmp_path, action="preview", output_width=20, output_height=30)
    _write_catalog(config, [_card(mode="contain")])
    _save_png(config.source_root / "aespa" / "ka1.png", size=(30, 30))

    cli.build_collection_assets(config)

    with Image.open(config.output_dir / "aespa" / "ka-01-r1.webp") as derivative:
        rgba = derivative.convert("RGBA")
        assert rgba.size == (20, 30)
        assert rgba.getpixel((10, 0))[3] == 0
        assert rgba.getpixel((10, 15))[3] > 240


def test_applies_exif_before_framing_and_strips_metadata(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_catalog(config, [_card(source="ka1.jpg")])
    source = config.source_root / "aespa" / "ka1.jpg"
    _save_jpeg(source, (30, 20), orientation=6)

    cli.build_collection_assets(config)

    manifest = json.loads((config.output_dir / "integrity.json").read_text("utf-8"))
    card = manifest["files"]["aespa/ka-01-r1.webp"]
    assert card["source_width"] == 20
    assert card["source_height"] == 30
    with Image.open(config.output_dir / "aespa" / "ka-01-r1.webp") as derivative:
        assert not derivative.getexif()


def test_preserves_png_alpha_and_converts_embedded_srgb_profile(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_catalog(config, [_card()])
    source = config.source_root / "aespa" / "ka1.png"
    source.parent.mkdir(parents=True)
    image = Image.new("RGBA", (20, 30), (20, 40, 60, 0))
    for x in range(10, 20):
        for y in range(30):
            image.putpixel((x, y), (220, 180, 120, 255))
    metadata = PngInfo()
    metadata.add_text("Comment", "private production note")
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    image.save(source, pnginfo=metadata, icc_profile=profile)

    cli.build_collection_assets(config)

    with Image.open(config.output_dir / "aespa" / "ka-01-r1.webp") as derivative:
        assert derivative.mode == "RGBA"
        assert derivative.getchannel("A").getextrema() == (0, 255)
        assert "Comment" not in derivative.info
        assert "exif" not in derivative.info
        assert "xmp" not in derivative.info
        assert "icc_profile" not in derivative.info


def test_report_records_crop_upscale_and_threshold_warnings(tmp_path: Path) -> None:
    config = _config(tmp_path, action="preview", output_width=20, output_height=30)
    _write_catalog(config, [_card()])
    _save_png(config.source_root / "aespa" / "ka1.png", size=(10, 40))

    report = cli.build_collection_assets(config)

    assert len(report.warnings) == 2
    preview = json.loads((config.output_dir / "preview-report.json").read_text("utf-8"))
    record = preview["cards"]["aespa/ka-01-r1.webp"]
    assert record["crop_fraction"] == pytest.approx(0.625)
    assert record["upscale_factor"] == pytest.approx(2.0)
    assert {warning["kind"] for warning in preview["warnings"]} == {
        "heavy_crop",
        "large_upscale",
    }


@pytest.mark.parametrize(
    ("catalog", "message"),
    [
        ({"schema_version": 2, "collections": []}, "schema_version"),
        (
            {
                "schema_version": 1,
                "collections": [{"key": "BTS", "display_name": "BTS", "cards": [_card()]}],
            },
            "collection key",
        ),
        (
            {
                "schema_version": 1,
                "collections": [{"key": "aespa", "display_name": " ", "cards": [_card()]}],
            },
            "display_name",
        ),
        (
            {
                "schema_version": 1,
                "collections": [
                    {
                        "key": "aespa",
                        "display_name": None,
                        "cards": [_card(source="../outside.png")],
                    }
                ],
            },
            "source",
        ),
        (
            {
                "schema_version": 1,
                "collections": [{"key": "aespa", "display_name": None, "cards": [_card(x=1.1)]}],
            },
            "focal_point.x",
        ),
        (
            {
                "schema_version": 1,
                "collections": [
                    {
                        "key": "aespa",
                        "display_name": None,
                        "cards": [_card(mode="stretch")],
                    }
                ],
            },
            "crop.mode",
        ),
    ],
)
def test_rejects_invalid_catalog_entries(
    tmp_path: Path, catalog: dict[str, Any], message: str
) -> None:
    config = _config(tmp_path)
    config.catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(cli.AssetBuildError, match=message):
        cli.load_catalog(config)


def test_rejects_duplicate_output_keys_and_bad_source_files(tmp_path: Path) -> None:
    duplicate = _config(tmp_path / "duplicate")
    _write_catalog(duplicate, [_card(), _card(source="ka2.png")])
    with pytest.raises(cli.AssetBuildError, match="duplicate card key"):
        cli.load_catalog(duplicate)

    signature = _config(tmp_path / "signature")
    _write_catalog(signature, [_card(source="ka1.jpg")])
    fake_jpeg = signature.source_root / "aespa" / "ka1.jpg"
    _save_png(fake_jpeg)
    with pytest.raises(cli.AssetBuildError, match="extension does not match"):
        cli.build_collection_assets(signature)

    corrupt = _config(tmp_path / "corrupt")
    _write_catalog(corrupt, [_card()])
    broken = corrupt.source_root / "aespa" / "ka1.png"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"not an image")
    with pytest.raises(cli.AssetBuildError, match="cannot decode"):
        cli.build_collection_assets(corrupt)


def test_rejects_oversized_header_before_full_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class OversizedImageHeader:
        format = "PNG"
        n_frames = 1
        width = 1_000
        height = 1_000

        def __enter__(self) -> OversizedImageHeader:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def load(self) -> None:
            raise AssertionError("oversized artwork must be rejected before pixel decode")

    monkeypatch.setattr(cli.Image, "open", lambda _path: OversizedImageHeader())

    with pytest.raises(cli.AssetBuildError, match="pixel safety limit"):
        cli._open_normalized(tmp_path / "oversized.png", "PNG", 100_000)


def test_build_adds_cards_but_never_overwrites_an_existing_revision(tmp_path: Path) -> None:
    config = _config(tmp_path)
    first_source = config.source_root / "aespa" / "ka1.png"
    second_source = config.source_root / "aespa" / "ka2.png"
    _save_png(first_source)
    _write_catalog(config, [_card()])

    first = cli.build_collection_assets(config)
    first_output = config.output_dir / "aespa" / "ka-01-r1.webp"
    first_output_hash = _sha256(first_output)

    _save_png(second_source)
    _write_catalog(config, [_card(), _card(key="ka-02", source="ka2.png")])
    second = cli.build_collection_assets(config)

    assert first.created == 1
    assert second.created == 1
    assert _sha256(first_output) == first_output_hash
    assert (config.output_dir / "aespa" / "ka-02-r1.webp").is_file()

    Image.new("RGB", (20, 30), (240, 30, 90)).save(first_source, format="PNG")
    with pytest.raises(cli.AssetBuildError, match="immutable"):
        cli.build_collection_assets(config)
    assert _sha256(first_output) == first_output_hash

    _write_catalog(config, [_card(revision=2), _card(key="ka-02", source="ka2.png")])
    third = cli.build_collection_assets(config)
    assert third.created == 1
    assert (config.output_dir / "aespa" / "ka-01-r2.webp").is_file()
    assert _sha256(first_output) == first_output_hash


def test_existing_build_rejects_changed_encoding_or_corrupt_output(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_catalog(config, [_card()])
    _save_png(config.source_root / "aespa" / "ka1.png")
    cli.build_collection_assets(config)

    changed_encoding = _config(tmp_path, quality=80)
    with pytest.raises(cli.AssetBuildError, match="encoding contract"):
        cli.build_collection_assets(changed_encoding)

    output = config.output_dir / "aespa" / "ka-01-r1.webp"
    output.write_bytes(b"corrupt")
    with pytest.raises(cli.AssetBuildError, match="immutable"):
        cli.build_collection_assets(config)


def test_requires_webp_encoder_support(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config(tmp_path)
    _write_catalog(config, [_card()])
    _save_png(config.source_root / "aespa" / "ka1.png")
    monkeypatch.setattr(cli.features, "check", lambda feature: False)

    with pytest.raises(cli.AssetBuildError, match="WebP encoder"):
        cli.build_collection_assets(config)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"action": "publish"}, "action"),
        ({"output_width": 0}, "output width"),
        ({"output_height": 16}, "2:3"),
        ({"quality": 101}, "quality"),
        ({"method": 7}, "method"),
        ({"crop_warning_fraction": 1.1}, "crop warning"),
        ({"upscale_warning_factor": 0.9}, "upscale warning"),
    ],
)
def test_rejects_invalid_build_configuration(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(cli.AssetBuildError, match=message):
        _config(tmp_path, **overrides)


@pytest.mark.parametrize(
    "output_dir",
    [
        Path("originals"),
        Path("originals/preview"),
        Path("."),
    ],
)
def test_rejects_any_overlap_between_source_and_output_roots(
    tmp_path: Path, output_dir: Path
) -> None:
    with pytest.raises(cli.AssetBuildError, match="must not overlap"):
        _config(tmp_path, output_dir=tmp_path / output_dir)


def test_parser_uses_preview_and_fhd_build_defaults() -> None:
    preview = cli.build_parser().parse_args(["preview"])
    build = cli.build_parser().parse_args(["build"])

    assert preview.action == "preview"
    assert build.action == "build"
    assert preview.output_width is None
    assert preview.output_height is None
    assert preview.quality == 85
    assert preview.method == 6

    for invalid in (
        ["publish"],
        ["build", "--quality", "101"],
        ["preview", "--max-megapixels", "nan"],
    ):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(invalid)


def test_preview_defaults_to_the_same_fhd_card_geometry_as_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, cli.AssetBuildConfig] = {}

    def capture(config: cli.AssetBuildConfig) -> cli.AssetBuildReport:
        seen["config"] = config
        return cli.AssetBuildReport(
            created=0,
            unchanged=True,
            output_dir=config.output_dir,
            warnings=(),
        )

    monkeypatch.setattr(cli, "build_collection_assets", capture)
    args = cli.build_parser().parse_args(
        [
            "preview",
            "--catalog",
            str(tmp_path / "catalog.json"),
            "--source-root",
            str(tmp_path / "originals"),
            "--output-dir",
            str(tmp_path / "preview"),
        ]
    )

    assert cli.run(args) == 0
    assert (seen["config"].output_width, seen["config"].output_height) == (720, 1080)


def test_run_accepts_string_paths_forwarded_by_nb(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_root = tmp_path / "originals"
    catalog_path = tmp_path / "catalog.json"
    output_dir = tmp_path / "preview"
    config = _config(
        tmp_path,
        action="preview",
        catalog_path=catalog_path,
        source_root=source_root,
        output_dir=output_dir,
    )
    _write_catalog(config, [_card()])
    _save_png(source_root / "aespa" / "ka1.png")
    args = argparse.Namespace(
        action="preview",
        catalog=str(catalog_path),
        source_root=str(source_root),
        output_dir=str(output_dir),
        output_width=10,
        output_height=15,
        quality=85,
        method=6,
        max_megapixels=1.0,
        crop_warning_percent=18.0,
        upscale_warning_factor=1.15,
    )

    assert cli.run(args) == 0
    assert (output_dir / "aespa" / "ka-01-r1.webp").is_file()
    assert "created=1" in capsys.readouterr().out


def test_run_reports_contract_errors_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = cli.build_parser().parse_args(["preview", "--catalog", str(tmp_path / "missing.json")])

    assert cli.run(args) == 1
    assert "ERROR" in capsys.readouterr().err

    args.max_megapixels = float("inf")
    assert cli.run(args) == 1
    assert "positive finite number" in capsys.readouterr().err

    args.max_megapixels = 1.0
    args.output_width = 0
    assert cli.run(args) == 1
    assert "output width" in capsys.readouterr().err
