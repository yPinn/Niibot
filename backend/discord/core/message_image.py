"""Discord-style message image renderer using Pillow.

Layout mirrors Discord cozy mode, dark theme (#313338).
Font fallback chain handles broad Unicode (CJK, symbols, special chars).
"""

from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path

import aiohttp
from PIL import Image, ImageDraw, ImageFont

LOGGER: logging.Logger = logging.getLogger(__name__)

# ── Discord dark theme exact values ─────────────────────────────────────────
_BG = (49, 51, 56)  # #313338
_COLOR_USERNAME = (242, 243, 245)  # #f2f3f5
_COLOR_TIMESTAMP = (148, 155, 164)  # #949ba4
_COLOR_CONTENT = (219, 222, 225)  # #dbdee1

# ── Layout — Discord cozy mode ───────────────────────────────────────────────
_IMG_WIDTH = 600
_PAD_LEFT = 24  # 3×8 — decoration left clearance: 24-12 = 12px (= top clearance)
_PAD_TOP = 24  # 3×8 — decoration top clearance: 24-12 = 12px
_PAD_BOTTOM = 24  # 3×8 — symmetric with _PAD_TOP for vertical centering
_AVATAR_SIZE = 40  # 5×8
_DECO_SIZE = 64  # 8×8; offset=12; decoration edges: left=12px, top=12px (symmetric)
_CONTENT_X = _PAD_LEFT + _AVATAR_SIZE + 24  # 88px — 11×8
_CORNER_RADIUS = 8  # 1×8
_HEADER_H = 20  # 5×4 — actual rendered height of 16px name text
_CONTENT_GAP = 2
_LINE_H = 22  # Discord 1.375×16 — intentional off-grid
_HEADER_BASELINE = _PAD_TOP + 17  # "ls" baseline; name top ≈ _PAD_TOP

# ── Font sizes ───────────────────────────────────────────────────────────────
_FS_NAME = 16
_FS_TIME = 12
_FS_CONTENT = 16
_FS_TAG = 12

# ── Server tag pill ──────────────────────────────────────────────────────────
_TAG_H = 20  # 5×4 — 12px font + 4px vertical padding each side
_TAG_RADIUS = 4
_TAG_PAD_X = 8  # 1×8
_TAG_GAP = 4
_TAG_BADGE_SIZE = 16

# ── Font paths (ordered: best coverage first) ────────────────────────────────
# Linux (Docker) — Noto family covers the widest Unicode range
_LINUX_FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansSymbols-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf",
    # Canadian Aboriginal Syllabics (ᓚᘏᗢ)
    "/usr/share/fonts/truetype/noto/NotoSansCanadianAboriginal-Regular.ttf",
]
_LINUX_FONTS_BOLD = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKsc-Bold.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]
# Windows — ordered by Unicode breadth
_WIN_FONTS = [
    "C:/Windows/Fonts/msjh.ttc",  # JhengHei — CJK Traditional
    "C:/Windows/Fonts/msyh.ttc",  # YaHei    — CJK Simplified
    "C:/Windows/Fonts/euphemia.ttf",  # Euphemia — Canadian Aboriginal Syllabics (ᓚᘏᗢ etc.)
    "C:/Windows/Fonts/seguisym.ttf",  # Segoe UI Symbol — geometric/misc symbols
    "C:/Windows/Fonts/segoeui.ttf",  # Segoe UI — Latin/Greek/Cyrillic
    "C:/Windows/Fonts/arial.ttf",
]
_WIN_FONTS_BOLD = [
    "C:/Windows/Fonts/msjhbd.ttc",
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]

_LINUX_FONTS_EMOJI = [
    "/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf",
    "/usr/share/fonts/noto/NotoEmoji-Regular.ttf",
]
# Windows: Segoe UI Emoji is COLR (colour), Pillow can't render it — no emoji font on Windows.

_REGULAR_PATHS = _LINUX_FONTS + _WIN_FONTS + _LINUX_FONTS_EMOJI
_MEDIUM_PATHS = _LINUX_FONTS_BOLD + _WIN_FONTS_BOLD

# Emoji ranges absent from CJK/Latin fonts; _FontChain shortcuts to emoji font for these.
_EMOJI_RANGES: tuple[tuple[int, int], ...] = (
    (0x2300, 0x23FF),  # Miscellaneous Technical
    (0x2600, 0x27BF),  # Misc Symbols + Dingbats
    (0x1F000, 0x1FFFF),  # Main emoji block
)


def _is_emoji(code: int) -> bool:
    return any(lo <= code <= hi for lo, hi in _EMOJI_RANGES)


# ── Font utilities ────────────────────────────────────────────────────────────


def _load_font(paths: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load the first available font from *paths* at *size*."""
    for path in paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _font_width(font: ImageFont.FreeTypeFont | ImageFont.ImageFont, text: str) -> int:
    try:
        return int(font.getlength(text))  # type: ignore[union-attr]
    except AttributeError:
        bbox = font.getbbox(text)  # type: ignore[union-attr]
        return int(bbox[2] - bbox[0]) if bbox else 0


class _FontChain:
    """Per-character font fallback; emoji codepoints shortcut to the last (emoji) font."""

    def __init__(self, size: int, paths: list[str]) -> None:
        self._fonts: list[ImageFont.FreeTypeFont | ImageFont.ImageFont] = []
        for path in paths:
            if Path(path).exists():
                try:
                    self._fonts.append(ImageFont.truetype(path, size))
                except Exception:
                    pass
        if not self._fonts:
            self._fonts.append(ImageFont.load_default())

    def _best(self, char: str) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Return first font whose cmap contains *char*; fallback to last font."""
        code = ord(char)
        # Emoji codepoints are absent from CJK/Latin fonts — jump straight to emoji font.
        if _is_emoji(code):
            return self._fonts[-1]
        for f in self._fonts:
            try:
                # Pillow FreeTypeFont: font.font is FT2Font (C ext).
                # get_char_index available in Pillow < 10; use getbbox width as proxy otherwise.
                raw = getattr(f, "font", None)
                get_idx = getattr(raw, "get_char_index", None)
                if get_idx is not None:
                    if get_idx(code):
                        return f
                    continue
                # Fallback: non-zero getlength means font has SOME glyph for char.
                # Compare against U+FFFD (replacement char) — if widths differ the
                # font probably has a real glyph, not just the generic .notdef box.
                w_char = _font_width(f, char)
                w_ref = _font_width(f, "\ufffd")
                if w_char > 0 and w_char != w_ref:
                    return f
            except Exception:
                continue
        return self._fonts[-1]

    def width(self, text: str) -> int:
        return sum(_font_width(self._best(ch), ch) for ch in text)

    def draw(
        self,
        draw: ImageDraw.ImageDraw,
        pos: tuple[int, int],
        text: str,
        fill: tuple[int, int, int] | tuple[int, int, int, int],
    ) -> int:
        x, y = pos
        for ch in text:
            f = self._best(ch)
            draw.text((x, y), ch, font=f, fill=fill)
            x += _font_width(f, ch)
        return x


# ── Image helpers ─────────────────────────────────────────────────────────────


def _make_circle_avatar(raw: bytes, size: int) -> Image.Image:
    ss = size * 2
    img = Image.open(io.BytesIO(raw)).resize((ss, ss), Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new("L", (ss, ss), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, ss, ss), fill=255)
    out = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    out.paste(img, mask=mask)
    return out.resize((size, size), Image.Resampling.LANCZOS)


def _draw_server_tag(
    base: Image.Image,
    x: int,
    y: int,
    tag_text: str,
    badge_bytes: bytes | None,
    chain: _FontChain,
) -> int:
    """Draw server tag pill onto *base*. Returns total width consumed (incl. gap)."""
    badge_img: Image.Image | None = None
    if badge_bytes:
        try:
            badge_img = (
                Image.open(io.BytesIO(badge_bytes))
                .convert("RGBA")
                .resize((_TAG_BADGE_SIZE, _TAG_BADGE_SIZE), Image.Resampling.LANCZOS)
            )
        except Exception:
            badge_img = None

    badge_w = (_TAG_BADGE_SIZE + _TAG_PAD_X) if badge_img else 0
    tw = chain.width(tag_text)
    w = _TAG_PAD_X + badge_w + tw + _TAG_PAD_X

    pill = Image.new("RGBA", (w, _TAG_H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pill)
    pd.rounded_rectangle(
        (0, 0, w - 1, _TAG_H - 1),
        radius=_TAG_RADIUS,
        fill=(255, 255, 255, 18),
        outline=(255, 255, 255, 36),
        width=1,
    )

    cx = _TAG_PAD_X
    if badge_img:
        by = (_TAG_H - _TAG_BADGE_SIZE) // 2
        pill.paste(badge_img, (cx, by), badge_img)
        cx += _TAG_BADGE_SIZE + _TAG_PAD_X

    text_y = (_TAG_H - _FS_TAG) // 2 - 1
    chain.draw(pd, (cx, text_y), tag_text, _COLOR_USERNAME)

    base.paste(pill, (x, y), pill)
    return w + _TAG_GAP


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        if not para.strip():
            lines.append("")
            continue
        cur = ""
        for word in para.split(" "):
            test = f"{cur} {word}".strip() if cur else word
            if _font_width(font, test) <= max_width:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                    cur = ""
                # Word itself too wide (e.g. CJK with no spaces) — break char by char
                if _font_width(font, word) > max_width:
                    for ch in word:
                        test = cur + ch
                        if _font_width(font, test) <= max_width:
                            cur = test
                        else:
                            if cur:
                                lines.append(cur)
                            cur = ch
                else:
                    cur = word
        if cur:
            lines.append(cur)
    return lines or [""]


# ── Main renderer ─────────────────────────────────────────────────────────────


def _render_sync(
    avatar_bytes: bytes | None,
    display_name: str,
    timestamp_str: str,
    content: str,
    role_color: tuple[int, int, int] | None,
    server_tag: tuple[str, bytes | None] | None,
    deco_bytes: bytes | None = None,
) -> bytes:
    font_name = _load_font(_MEDIUM_PATHS, _FS_NAME)
    font_time = _load_font(_REGULAR_PATHS, _FS_TIME)
    font_measure = _load_font(_REGULAR_PATHS, _FS_CONTENT)  # single font for wrap measurement
    chain_content = _FontChain(_FS_CONTENT, _REGULAR_PATHS)
    chain_tag = _FontChain(_FS_TAG, _REGULAR_PATHS)

    max_content_w = _IMG_WIDTH - _CONTENT_X - _PAD_LEFT
    lines = _wrap_text(content or "(無文字內容)", font_measure, max_content_w)

    content_h = len(lines) * _LINE_H
    total_h = _PAD_TOP + max(_HEADER_H + _CONTENT_GAP + content_h, _AVATAR_SIZE) + _PAD_BOTTOM

    img = Image.new("RGBA", (_IMG_WIDTH, total_h), _BG + (255,))
    draw = ImageDraw.Draw(img)

    if avatar_bytes:
        try:
            av = _make_circle_avatar(avatar_bytes, _AVATAR_SIZE)
            ax, ay = _PAD_LEFT, _PAD_TOP
            img.paste(av, (ax, ay), av)
            if deco_bytes:
                try:
                    deco = (
                        Image.open(io.BytesIO(deco_bytes))
                        .convert("RGBA")
                        .resize((_DECO_SIZE, _DECO_SIZE), Image.Resampling.LANCZOS)
                    )
                    offset = (_DECO_SIZE - _AVATAR_SIZE) // 2
                    img.paste(deco, (ax - offset, ay - offset), deco)
                except Exception as e:
                    LOGGER.debug("Decoration render failed: %s", e)
                    draw.ellipse(
                        (ax, ay, ax + _AVATAR_SIZE - 1, ay + _AVATAR_SIZE - 1),
                        outline=(0, 0, 0, 80),
                        width=2,
                    )
            else:
                draw.ellipse(
                    (ax, ay, ax + _AVATAR_SIZE - 1, ay + _AVATAR_SIZE - 1),
                    outline=(0, 0, 0, 80),
                    width=2,
                )
        except Exception as e:
            LOGGER.debug("Avatar render failed: %s", e)

    name_color = role_color or _COLOR_USERNAME
    draw.text(
        (_CONTENT_X, _HEADER_BASELINE), display_name, font=font_name, fill=name_color, anchor="ls"
    )
    name_w = _font_width(font_name, display_name)

    tag_x = _CONTENT_X + name_w + _TAG_GAP
    tag_y = _PAD_TOP + (_HEADER_H - _TAG_H) // 2
    if server_tag:
        tag_w = _draw_server_tag(img, tag_x, tag_y, server_tag[0], server_tag[1], chain_tag)
    else:
        tag_w = 0

    ts_x = tag_x + tag_w + (2 if not server_tag else 0)
    draw.text(
        (ts_x, _HEADER_BASELINE), timestamp_str, font=font_time, fill=_COLOR_TIMESTAMP, anchor="ls"
    )

    y = _PAD_TOP + _HEADER_H + _CONTENT_GAP
    for line in lines:
        chain_content.draw(draw, (_CONTENT_X, y), line, _COLOR_CONTENT)
        y += _LINE_H

    # Rounded corners: punch a mask into the alpha channel, then save as RGBA PNG.
    # Discord renders transparent corners against its own background.
    mask = Image.new("L", (_IMG_WIDTH, total_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, _IMG_WIDTH - 1, total_h - 1), radius=_CORNER_RADIUS, fill=255
    )
    img.putalpha(mask)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


# ── Async entry point ─────────────────────────────────────────────────────────


async def _fetch_bytes(url: str | None) -> bytes | None:
    if not url:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as e:
        LOGGER.warning("HTTP fetch failed %s: %s", url, e)
    return None


async def render_message_image(
    avatar_url: str | None,
    display_name: str,
    timestamp_str: str,
    content: str,
    role_color: tuple[int, int, int] | None = None,
    server_tag: tuple[str, str | None] | None = None,
    decoration_url: str | None = None,
) -> bytes:
    """Render a Discord-style message card and return PNG bytes."""
    avatar_bytes, badge_bytes, deco_bytes = await asyncio.gather(
        _fetch_bytes(avatar_url),
        _fetch_bytes(server_tag[1] if server_tag else None),
        _fetch_bytes(decoration_url),
    )
    resolved_tag: tuple[str, bytes | None] | None = (
        (server_tag[0], badge_bytes) if server_tag else None
    )
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        _render_sync,
        avatar_bytes,
        display_name,
        timestamp_str,
        content,
        role_color,
        resolved_tag,
        deco_bytes,
    )
