#!/usr/bin/env python3
"""Preview and build 2:3 WebP derivatives from a collection artwork catalog."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from _lib import REPO_ROOT, utf8_stdio
from PIL import Image, ImageCms, ImageDraw, ImageOps, UnidentifiedImageError, features

_MACHINE_KEY = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SOURCE_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.(?:jpe?g|png)$")
_SOURCE_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG"}
_CATALOG_SCHEMA_VERSION = 1
_MANIFEST_SCHEMA_VERSION = 2
_MANIFEST_NAME = "integrity.json"
_PREVIEW_REPORT_NAME = "preview-report.json"
_DEFAULT_MAX_PIXELS = 50_000_000
_BUILD_SIZE = (720, 1080)
_PREVIEW_SIZE = _BUILD_SIZE


class AssetBuildError(ValueError):
    """Raised when artwork or catalog data violates the asset contract."""


@dataclass(frozen=True, slots=True)
class AssetBuildConfig:
    action: Literal["preview", "build"] | str
    catalog_path: Path
    source_root: Path
    output_dir: Path
    output_width: int = _BUILD_SIZE[0]
    output_height: int = _BUILD_SIZE[1]
    quality: int = 85
    method: int = 6
    max_pixels: int = _DEFAULT_MAX_PIXELS
    crop_warning_fraction: float = 0.18
    upscale_warning_factor: float = 1.15

    def __post_init__(self) -> None:
        if self.action not in {"preview", "build"}:
            raise AssetBuildError("action must be preview or build")
        for label, value in (
            ("output width", self.output_width),
            ("output height", self.output_height),
            ("pixel safety limit", self.max_pixels),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise AssetBuildError(f"{label} must be a positive integer")
        if self.output_width * 3 != self.output_height * 2:
            raise AssetBuildError("output dimensions must use the 2:3 card ratio")
        if not isinstance(self.quality, int) or not 0 <= self.quality <= 100:
            raise AssetBuildError("WebP quality must be between 0 and 100")
        if not isinstance(self.method, int) or not 0 <= self.method <= 6:
            raise AssetBuildError("WebP method must be between 0 and 6")
        if not math.isfinite(self.crop_warning_fraction) or not (
            0 <= self.crop_warning_fraction <= 1
        ):
            raise AssetBuildError("crop warning fraction must be between 0 and 1")
        if not math.isfinite(self.upscale_warning_factor) or self.upscale_warning_factor < 1:
            raise AssetBuildError("upscale warning factor must be at least 1")
        source_root = self.source_root.resolve()
        output_dir = self.output_dir.resolve()
        if (
            source_root == output_dir
            or source_root.is_relative_to(output_dir)
            or output_dir.is_relative_to(source_root)
        ):
            raise AssetBuildError("source and output roots must not overlap")


@dataclass(frozen=True, slots=True)
class FocalPoint:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class CatalogCard:
    collection_key: str
    key: str
    source_name: str
    source_path: Path
    revision: int
    display_name: str | None
    crop_mode: Literal["cover", "contain"]
    focal_point: FocalPoint

    @property
    def output_relative_path(self) -> Path:
        return Path(self.collection_key) / f"{self.key}-r{self.revision}.webp"


@dataclass(frozen=True, slots=True)
class CatalogCollection:
    key: str
    display_name: str | None
    cards: tuple[CatalogCard, ...]


@dataclass(frozen=True, slots=True)
class CollectionCatalog:
    collections: tuple[CatalogCollection, ...]

    @property
    def cards(self) -> tuple[CatalogCard, ...]:
        return tuple(card for collection in self.collections for card in collection.cards)


@dataclass(frozen=True, slots=True)
class SourceArtwork:
    card: CatalogCard
    format: str
    sha256: str
    width: int
    height: int
    has_alpha: bool


@dataclass(frozen=True, slots=True)
class ProcessedArtwork:
    source: SourceArtwork
    crop_box: tuple[int, int, int, int]
    crop_fraction: float
    upscale_factor: float
    output_path: Path


@dataclass(frozen=True, slots=True)
class AssetBuildReport:
    created: int
    unchanged: bool
    output_dir: Path
    warnings: tuple[dict[str, Any], ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AssetBuildError(f"{label} does not exist: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssetBuildError(f"cannot read {label} at {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise AssetBuildError(f"{label} must contain a JSON object")
    return loaded


def _display_name(value: object, location: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise AssetBuildError(f"{location}.display_name must be null or 1-128 characters")
    return value


def _machine_key(value: object, location: str) -> str:
    if not isinstance(value, str) or not _MACHINE_KEY.fullmatch(value):
        raise AssetBuildError(
            f"{location} key must use lowercase letters, numbers, and single hyphens"
        )
    return value


def _finite_unit_number(value: object, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AssetBuildError(f"{location} must be a number between 0 and 1")
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise AssetBuildError(f"{location} must be a number between 0 and 1")
    return number


def load_catalog(config: AssetBuildConfig) -> CollectionCatalog:
    """Load and validate display metadata, paths, revisions, and framing settings."""
    payload = _read_json_object(config.catalog_path, "catalog")
    if payload.get("schema_version") != _CATALOG_SCHEMA_VERSION:
        raise AssetBuildError(f"catalog schema_version must be {_CATALOG_SCHEMA_VERSION}")
    raw_collections = payload.get("collections")
    if not isinstance(raw_collections, list) or not raw_collections:
        raise AssetBuildError("catalog.collections must be a non-empty array")

    source_root = config.source_root.resolve()
    collections: list[CatalogCollection] = []
    collection_keys: set[str] = set()
    output_keys: set[tuple[str, str]] = set()
    source_paths: set[Path] = set()

    for collection_index, raw_collection in enumerate(raw_collections):
        location = f"collections[{collection_index}]"
        if not isinstance(raw_collection, dict):
            raise AssetBuildError(f"{location} must be an object")
        collection_key = _machine_key(raw_collection.get("key"), "collection")
        if collection_key in collection_keys:
            raise AssetBuildError(f"duplicate collection key: {collection_key}")
        collection_keys.add(collection_key)
        collection_display_name = _display_name(raw_collection.get("display_name"), location)
        raw_cards = raw_collection.get("cards")
        if not isinstance(raw_cards, list) or not raw_cards:
            raise AssetBuildError(f"{location}.cards must be a non-empty array")

        cards: list[CatalogCard] = []
        for card_index, raw_card in enumerate(raw_cards):
            card_location = f"{location}.cards[{card_index}]"
            if not isinstance(raw_card, dict):
                raise AssetBuildError(f"{card_location} must be an object")
            card_key = _machine_key(raw_card.get("key"), "card")
            output_key = (collection_key, card_key)
            if output_key in output_keys:
                raise AssetBuildError(
                    f"duplicate card key in collection {collection_key}: {card_key}"
                )
            output_keys.add(output_key)

            source_name = raw_card.get("source")
            if not isinstance(source_name, str) or not _SOURCE_NAME.fullmatch(source_name):
                raise AssetBuildError(
                    f"{card_location}.source must be one lowercase JPEG/PNG filename"
                )
            source_path = (source_root / collection_key / source_name).resolve()
            try:
                source_path.relative_to(source_root)
            except ValueError as exc:
                raise AssetBuildError(
                    f"{card_location}.source must stay inside the artwork root"
                ) from exc
            if source_path in source_paths:
                raise AssetBuildError(f"source file is listed more than once: {source_name}")
            source_paths.add(source_path)

            revision = raw_card.get("revision")
            if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
                raise AssetBuildError(f"{card_location}.revision must be a positive integer")
            crop = raw_card.get("crop")
            if not isinstance(crop, dict):
                raise AssetBuildError(f"{card_location}.crop must be an object")
            crop_mode = crop.get("mode")
            if crop_mode not in {"cover", "contain"}:
                raise AssetBuildError(f"{card_location}.crop.mode must be cover or contain")
            focal = crop.get("focal_point")
            if not isinstance(focal, dict):
                raise AssetBuildError(f"{card_location}.crop.focal_point must be an object")

            cards.append(
                CatalogCard(
                    collection_key=collection_key,
                    key=card_key,
                    source_name=source_name,
                    source_path=source_path,
                    revision=revision,
                    display_name=_display_name(raw_card.get("display_name"), card_location),
                    crop_mode=crop_mode,
                    focal_point=FocalPoint(
                        x=_finite_unit_number(
                            focal.get("x"), f"{card_location}.crop.focal_point.x"
                        ),
                        y=_finite_unit_number(
                            focal.get("y"), f"{card_location}.crop.focal_point.y"
                        ),
                    ),
                )
            )
        collections.append(
            CatalogCollection(
                key=collection_key,
                display_name=collection_display_name,
                cards=tuple(cards),
            )
        )
    return CollectionCatalog(collections=tuple(collections))


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in {"RGBA", "LA", "PA"} or (
        image.mode == "P" and "transparency" in image.info
    )


def _open_normalized(path: Path, expected_format: str, max_pixels: int) -> Image.Image:
    try:
        with Image.open(path) as opened:
            if opened.format != expected_format:
                actual = opened.format or "unknown"
                raise AssetBuildError(
                    f"{path.name}: extension does not match decoded format ({actual})"
                )
            if getattr(opened, "n_frames", 1) != 1:
                raise AssetBuildError(
                    f"{path.name}: animated or multi-frame artwork is unsupported"
                )
            if opened.width * opened.height > max_pixels:
                raise AssetBuildError(f"{path.name}: exceeds the {max_pixels:,}-pixel safety limit")
            opened.load()
            normalized = ImageOps.exif_transpose(opened)
            normalized.load()
            return normalized.copy()
    except AssetBuildError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise AssetBuildError(f"{path.name}: cannot decode source artwork ({exc})") from exc


def _convert_to_srgb(image: Image.Image, *, keep_alpha: bool, source_name: str) -> Image.Image:
    alpha = image.convert("RGBA").getchannel("A") if keep_alpha else None
    color = image.convert("RGB")
    icc_profile = image.info.get("icc_profile")
    if icc_profile:
        try:
            input_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_profile))
            output_profile = ImageCms.createProfile("sRGB")
            transformed = ImageCms.profileToProfile(
                color,
                input_profile,
                output_profile,
                outputMode="RGB",
                renderingIntent=ImageCms.Intent.PERCEPTUAL,
            )
            if transformed is None:
                raise ImageCms.PyCMSError("profile conversion returned no image")
            color.close()
            color = transformed
        except (ImageCms.PyCMSError, OSError, TypeError, ValueError) as exc:
            color.close()
            if alpha is not None:
                alpha.close()
            raise AssetBuildError(
                f"{source_name}: cannot convert embedded color profile to sRGB"
            ) from exc
    if alpha is None:
        return color
    color.putalpha(alpha)
    alpha.close()
    return color


def _cover_box(
    width: int,
    height: int,
    output_width: int,
    output_height: int,
    focal_point: FocalPoint,
) -> tuple[int, int, int, int]:
    if width * output_height > height * output_width:
        crop_width = max(1, round(height * output_width / output_height))
        left = round(focal_point.x * width - crop_width / 2)
        left = min(max(left, 0), width - crop_width)
        return (left, 0, left + crop_width, height)
    crop_height = max(1, round(width * output_height / output_width))
    top = round(focal_point.y * height - crop_height / 2)
    top = min(max(top, 0), height - crop_height)
    return (0, top, width, top + crop_height)


def _frame_image(
    image: Image.Image, card: CatalogCard, config: AssetBuildConfig
) -> tuple[Image.Image, tuple[int, int, int, int], float, float]:
    width, height = image.size
    if card.crop_mode == "contain":
        scale = min(config.output_width / width, config.output_height / height)
        resized_size = (
            max(1, round(width * scale)),
            max(1, round(height * scale)),
        )
        resized = image.resize(resized_size, Image.Resampling.LANCZOS).convert("RGBA")
        canvas = Image.new("RGBA", (config.output_width, config.output_height), (0, 0, 0, 0))
        offset = (
            (config.output_width - resized.width) // 2,
            (config.output_height - resized.height) // 2,
        )
        canvas.alpha_composite(resized, dest=offset)
        resized.close()
        return canvas, (0, 0, width, height), 0.0, scale

    crop_box = _cover_box(
        width,
        height,
        config.output_width,
        config.output_height,
        card.focal_point,
    )
    cropped = image.crop(crop_box)
    crop_width = crop_box[2] - crop_box[0]
    crop_height = crop_box[3] - crop_box[1]
    crop_fraction = 1 - (crop_width * crop_height) / (width * height)
    upscale_factor = max(
        config.output_width / crop_width,
        config.output_height / crop_height,
    )
    resized = cropped.resize((config.output_width, config.output_height), Image.Resampling.LANCZOS)
    cropped.close()
    return resized, crop_box, crop_fraction, upscale_factor


def _process_card(card: CatalogCard, target: Path, config: AssetBuildConfig) -> ProcessedArtwork:
    if not card.source_path.is_file():
        raise AssetBuildError(f"source artwork does not exist: {card.source_path}")
    expected_format = _SOURCE_FORMATS[card.source_path.suffix.lower()]
    normalized = _open_normalized(card.source_path, expected_format, config.max_pixels)
    try:
        source = SourceArtwork(
            card=card,
            format=expected_format.lower(),
            sha256=_sha256(card.source_path),
            width=normalized.width,
            height=normalized.height,
            has_alpha=_has_alpha(normalized),
        )
        converted = _convert_to_srgb(
            normalized,
            keep_alpha=source.has_alpha,
            source_name=card.source_name,
        )
        try:
            framed, crop_box, crop_fraction, upscale_factor = _frame_image(converted, card, config)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                framed.save(
                    target,
                    format="WEBP",
                    quality=config.quality,
                    method=config.method,
                    alpha_quality=100,
                    exact=False,
                )
            finally:
                framed.close()
        finally:
            converted.close()
    finally:
        normalized.close()
    return ProcessedArtwork(
        source=source,
        crop_box=crop_box,
        crop_fraction=crop_fraction,
        upscale_factor=upscale_factor,
        output_path=target,
    )


def _encoding_contract(config: AssetBuildConfig) -> dict[str, Any]:
    return {
        "format": "webp",
        "width": config.output_width,
        "height": config.output_height,
        "quality": config.quality,
        "method": config.method,
        "alpha_quality": 100,
        "exact_transparent_rgb": False,
        "resampling": "lanczos",
        "color_space": "srgb",
        "metadata": "stripped",
    }


def _record(processed: ProcessedArtwork) -> dict[str, Any]:
    source = processed.source
    card = source.card
    return {
        "collection_key": card.collection_key,
        "card_key": card.key,
        "revision": card.revision,
        "source_file": f"{card.collection_key}/{card.source_name}",
        "source_format": source.format,
        "source_sha256": source.sha256,
        "source_width": source.width,
        "source_height": source.height,
        "source_has_alpha": source.has_alpha,
        "crop_mode": card.crop_mode,
        "focal_point": {"x": card.focal_point.x, "y": card.focal_point.y},
        "crop_box": list(processed.crop_box),
        "crop_fraction": round(processed.crop_fraction, 6),
        "upscale_factor": round(processed.upscale_factor, 6),
        "output_sha256": _sha256(processed.output_path),
        "output_bytes": processed.output_path.stat().st_size,
    }


def _warnings(processed: ProcessedArtwork, config: AssetBuildConfig) -> list[dict[str, Any]]:
    relative_path = processed.source.card.output_relative_path.as_posix()
    warnings: list[dict[str, Any]] = []
    if processed.crop_fraction > config.crop_warning_fraction:
        warnings.append(
            {
                "path": relative_path,
                "kind": "heavy_crop",
                "value": round(processed.crop_fraction, 6),
                "threshold": config.crop_warning_fraction,
            }
        )
    if processed.upscale_factor > config.upscale_warning_factor:
        warnings.append(
            {
                "path": relative_path,
                "kind": "large_upscale",
                "value": round(processed.upscale_factor, 6),
                "threshold": config.upscale_warning_factor,
            }
        )
    return warnings


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _build_contact_sheet(
    collection: CatalogCollection, preview_root: Path, output_size: tuple[int, int]
) -> None:
    columns = min(4, len(collection.cards))
    rows = math.ceil(len(collection.cards) / columns)
    image_width, image_height = output_size
    gap = max(8, image_width // 30)
    label_height = max(24, image_height // 20)
    sheet = Image.new(
        "RGB",
        (
            gap + columns * (image_width + gap),
            gap + rows * (image_height + label_height + gap),
        ),
        (20, 21, 25),
    )
    draw = ImageDraw.Draw(sheet)
    try:
        for index, card in enumerate(collection.cards):
            row, column = divmod(index, columns)
            x = gap + column * (image_width + gap)
            y = gap + row * (image_height + label_height + gap)
            with Image.open(preview_root / card.output_relative_path) as preview:
                rgba = preview.convert("RGBA")
                background = Image.new("RGBA", rgba.size, (35, 36, 42, 255))
                background.alpha_composite(rgba)
                sheet.paste(background.convert("RGB"), (x, y))
                background.close()
                rgba.close()
            label = card.display_name or card.key
            draw.text((x, y + image_height + 4), label, fill=(236, 236, 240))
        target = preview_root / collection.key / "contact-sheet.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(target, format="JPEG", quality=88, optimize=True)
    finally:
        sheet.close()


def _replace_preview_dir(temp_dir: Path, output_dir: Path) -> None:
    if not output_dir.exists():
        temp_dir.replace(output_dir)
        return
    if not output_dir.is_dir():
        raise AssetBuildError(f"preview output path is not a directory: {output_dir}")
    backup = output_dir.with_name(f".{output_dir.name}-previous")
    if backup.exists():
        raise AssetBuildError(f"stale preview backup must be removed first: {backup}")
    output_dir.replace(backup)
    try:
        temp_dir.replace(output_dir)
    except Exception:
        backup.replace(output_dir)
        raise
    shutil.rmtree(backup)


def _preview_assets(catalog: CollectionCatalog, config: AssetBuildConfig) -> AssetBuildReport:
    config.output_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{config.output_dir.name}-build-",
            dir=config.output_dir.parent,
        )
    )
    records: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, Any]] = []
    try:
        for card in catalog.cards:
            relative_path = card.output_relative_path
            processed = _process_card(card, temp_dir / relative_path, config)
            records[relative_path.as_posix()] = {
                **_record(processed),
                "collection_display_name": next(
                    collection.display_name
                    for collection in catalog.collections
                    if collection.key == card.collection_key
                ),
                "display_name": card.display_name,
            }
            warnings.extend(_warnings(processed, config))
        for collection in catalog.collections:
            _build_contact_sheet(
                collection,
                temp_dir,
                (config.output_width, config.output_height),
            )
        _write_json(
            temp_dir / _PREVIEW_REPORT_NAME,
            {
                "schema_version": _MANIFEST_SCHEMA_VERSION,
                "mode": "preview",
                "encoding": _encoding_contract(config),
                "cards": records,
                "warnings": warnings,
            },
        )
        _replace_preview_dir(temp_dir, config.output_dir)
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise
    return AssetBuildReport(
        created=len(catalog.cards),
        unchanged=False,
        output_dir=config.output_dir,
        warnings=tuple(warnings),
    )


def _load_existing_manifest(config: AssetBuildConfig) -> dict[str, Any]:
    manifest_path = config.output_dir / _MANIFEST_NAME
    if not manifest_path.exists():
        orphaned = list(config.output_dir.rglob("*.webp")) if config.output_dir.exists() else []
        if orphaned:
            raise AssetBuildError(
                f"immutable output exists without {_MANIFEST_NAME}: {orphaned[0]}"
            )
        return {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "encoding": _encoding_contract(config),
            "files": {},
        }
    manifest = _read_json_object(manifest_path, "integrity manifest")
    if manifest.get("schema_version") != _MANIFEST_SCHEMA_VERSION:
        raise AssetBuildError("immutable output uses an unsupported manifest schema")
    if manifest.get("encoding") != _encoding_contract(config):
        raise AssetBuildError(
            "existing immutable output uses a different encoding contract; use a new output root"
        )
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise AssetBuildError("immutable output has an invalid files manifest")
    for relative_name, record in files.items():
        if not isinstance(relative_name, str) or not isinstance(record, dict):
            raise AssetBuildError("immutable output has an invalid file record")
        output_path = config.output_dir / Path(relative_name)
        expected_hash = record.get("output_sha256")
        if not output_path.is_file() or not isinstance(expected_hash, str):
            raise AssetBuildError(f"immutable output is incomplete: {relative_name}")
        if _sha256(output_path) != expected_hash:
            raise AssetBuildError(f"immutable output was modified: {relative_name}")
    return manifest


def _immutable_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in {"output_bytes"}}


def _build_assets(catalog: CollectionCatalog, config: AssetBuildConfig) -> AssetBuildReport:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_existing_manifest(config)
    existing_files = manifest["files"]
    assert isinstance(existing_files, dict)

    with tempfile.TemporaryDirectory(
        prefix=f".{config.output_dir.name}-build-",
        dir=config.output_dir.parent,
    ) as temp_name:
        temp_dir = Path(temp_name)
        prepared: list[tuple[CatalogCard, ProcessedArtwork, dict[str, Any]]] = []
        warnings: list[dict[str, Any]] = []
        for card in catalog.cards:
            relative_path = card.output_relative_path
            processed = _process_card(card, temp_dir / relative_path, config)
            record = _record(processed)
            prepared.append((card, processed, record))
            warnings.extend(_warnings(processed, config))

        created = 0
        merged_files = dict(existing_files)
        for card, _processed, record in prepared:
            relative_name = card.output_relative_path.as_posix()
            target = config.output_dir / card.output_relative_path
            existing_record = existing_files.get(relative_name)
            if existing_record is None and not target.exists():
                continue
            if not isinstance(existing_record, dict) or not target.is_file():
                raise AssetBuildError(f"immutable artwork revision is incomplete: {relative_name}")
            if _immutable_fields(existing_record) != _immutable_fields(record):
                raise AssetBuildError(
                    f"immutable artwork revision differs: {relative_name}; increment revision"
                )

        for card, processed, record in prepared:
            relative_name = card.output_relative_path.as_posix()
            target = config.output_dir / card.output_relative_path
            if relative_name in existing_files:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            processed.output_path.replace(target)
            merged_files[relative_name] = record
            created += 1

        if created:
            manifest_path = config.output_dir / _MANIFEST_NAME
            staged_manifest = temp_dir / _MANIFEST_NAME
            _write_json(
                staged_manifest,
                {
                    "schema_version": _MANIFEST_SCHEMA_VERSION,
                    "encoding": _encoding_contract(config),
                    "files": merged_files,
                },
            )
            staged_manifest.replace(manifest_path)

    return AssetBuildReport(
        created=created,
        unchanged=created == 0,
        output_dir=config.output_dir,
        warnings=tuple(warnings),
    )


def build_collection_assets(config: AssetBuildConfig) -> AssetBuildReport:
    """Generate a mutable review preview or immutable runtime derivatives."""
    if not features.check("webp"):
        raise AssetBuildError("Pillow was installed without WebP encoder support")
    catalog = load_catalog(config)
    if config.action == "preview":
        return _preview_assets(catalog, config)
    return _build_assets(catalog, config)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _quality(value: str) -> int:
    parsed = int(value)
    if not 0 <= parsed <= 100:
        raise argparse.ArgumentTypeError("must be between 0 and 100")
    return parsed


def _method(value: str) -> int:
    parsed = int(value)
    if not 0 <= parsed <= 6:
        raise argparse.ArgumentTypeError("must be between 0 and 6")
    return parsed


def _max_megapixels(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return parsed


def _warning_percent(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or not 0 <= parsed <= 100:
        raise argparse.ArgumentTypeError("must be between 0 and 100")
    return parsed


def _upscale_factor(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _megapixels_to_pixels(value: object) -> int:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise AssetBuildError("max megapixels must be a positive finite number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise AssetBuildError("max megapixels must be a positive finite number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise AssetBuildError("max megapixels must be a positive finite number")
    return int(parsed * 1_000_000)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=("preview", "build"))
    parser.add_argument("--catalog", type=Path, help="catalog JSON path")
    parser.add_argument("--source-root", type=Path, help="artwork collections root")
    parser.add_argument("--output-dir", type=Path, help="preview or runtime output root")
    parser.add_argument("--output-width", type=_positive_int)
    parser.add_argument("--output-height", type=_positive_int)
    parser.add_argument("--quality", type=_quality, default=85)
    parser.add_argument("--method", type=_method, default=6)
    parser.add_argument(
        "--max-megapixels",
        type=_max_megapixels,
        default=_DEFAULT_MAX_PIXELS / 1_000_000,
        help="decoded source safety limit (default: 50)",
    )
    parser.add_argument(
        "--crop-warning-percent",
        type=_warning_percent,
        default=18.0,
        help="warn when cover removes more than this percentage (default: 18)",
    )
    parser.add_argument(
        "--upscale-warning-factor",
        type=_upscale_factor,
        default=1.15,
        help="warn above this linear upscale factor (default: 1.15)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or build catalog-driven collection WebP derivatives"
    )
    add_arguments(parser)
    return parser


def run(args: argparse.Namespace) -> int:
    catalog_path = (
        Path(args.catalog)
        if args.catalog
        else (REPO_ROOT / "artwork" / "collections" / "catalog.json")
    )
    source_root = Path(args.source_root) if args.source_root else catalog_path.parent
    if args.output_dir:
        output_dir = Path(args.output_dir)
    elif args.action == "preview":
        output_dir = REPO_ROOT / "tasks" / "collection-assets-preview"
    else:
        output_dir = REPO_ROOT / "frontend" / "public" / "images" / "collections"
    default_width, default_height = _PREVIEW_SIZE if args.action == "preview" else _BUILD_SIZE
    output_width = default_width if args.output_width is None else args.output_width
    output_height = default_height if args.output_height is None else args.output_height
    try:
        config = AssetBuildConfig(
            action=args.action,
            catalog_path=catalog_path.resolve(),
            source_root=source_root.resolve(),
            output_dir=output_dir.resolve(),
            output_width=output_width,
            output_height=output_height,
            quality=args.quality,
            method=args.method,
            max_pixels=_megapixels_to_pixels(args.max_megapixels),
            crop_warning_fraction=args.crop_warning_percent / 100,
            upscale_warning_factor=args.upscale_warning_factor,
        )
        report = build_collection_assets(config)
    except (AssetBuildError, OSError) as exc:
        print(f"[collection-assets] ERROR: {exc}", file=sys.stderr)
        return 1

    state = "unchanged" if report.unchanged else f"created={report.created}"
    print(
        f"[collection-assets] {args.action}: {state}; warnings={len(report.warnings)}; "
        f"{report.output_dir}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
