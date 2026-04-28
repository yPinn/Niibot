"""Unit tests for twitch.components.ai — pure utility functions.

Covers:
- _to_flat_pinyin: Chinese → concatenated tone-less pinyin
- _scan_response: dual-layer (substring + pinyin) content filter
- _load_chat_filter: JSON load with FileNotFoundError / parse-error fallback
"""

import json
from unittest.mock import patch

from twitch.components.ai import (
    _FALLBACK_PINYIN,
    _FALLBACK_SUBSTRINGS,
    _load_chat_filter,
    _normalize_pinyin,
    _scan_response,
    _to_flat_pinyin,
)


class TestNormalizePinyin:
    def test_l_to_n(self):
        assert _normalize_pinyin("lige") == "nige"

    def test_no_change_when_no_match(self):
        assert _normalize_pinyin("heigui") == "heigui"

    def test_already_normalized(self):
        assert _normalize_pinyin("nige") == "nige"


class TestToFlatPinyin:
    def test_homophone_slur(self):
        # 逆哥 (逆=ní) is phonetically identical to 尼哥
        assert _to_flat_pinyin("逆哥") == "nige"

    def test_copernicus_not_nige(self):
        # 哥白尼 → gebaini — must NOT contain "nige"
        result = _to_flat_pinyin("哥白尼")
        assert result == "gebaini"
        assert "nige" not in result

    def test_english_passthrough(self):
        assert _to_flat_pinyin("hello") == "hello"

    def test_output_is_lowercase(self):
        result = _to_flat_pinyin("你好")
        assert result == result.lower()


class TestScanResponse:
    def test_clean_text_returns_none(self):
        assert _scan_response("今天天氣很好") is None

    def test_english_clean_returns_none(self):
        assert _scan_response("Who proposed heliocentrism? Copernicus.") is None

    def test_layer1_nige_blocked(self):
        assert _scan_response("你是尼哥嗎") == "尼哥"

    def test_layer1_heigui_blocked(self):
        assert _scan_response("那個黑鬼說什麼") == "黑鬼"

    def test_layer2_nige_homophone_blocked(self):
        # 逆哥 (逆=ní) → "nige"; not in _FALLBACK_SUBSTRINGS so only caught by pinyin layer
        assert _scan_response("你是逆哥嗎") == "pinyin:nige"

    def test_layer2_heigui_homophone_blocked(self):
        # 黑龜 (黑=hēi, 龜=guī) → "heigui"
        assert _scan_response("黑龜跑很快") == "pinyin:heigui"

    def test_layer2_fuzzy_ln_confusion_blocked(self):
        # 哩哥 (哩=lǐ) → "lige" → normalized → "nige"
        assert _scan_response("你是哩哥嗎") == "pinyin:nige"

    def test_copernicus_not_blocked(self):
        # 哥白尼 → gebaini, no match at either layer
        assert _scan_response("哥白尼提出了日心說") is None

    def test_empty_pinyin_list_skips_conversion(self):
        # When _FLAGGED_PINYIN is empty, pinyin conversion is skipped entirely;
        # 逆哥 would normally match the pinyin layer but passes with empty list
        with patch("twitch.components.ai._FLAGGED_PINYIN", []):
            assert _scan_response("你是逆哥") is None


class TestLoadChatFilter:
    def test_fallback_when_file_missing(self, tmp_path):
        with patch("twitch.components.ai._CHAT_FILTER_PATH", tmp_path / "nonexistent.json"):
            substrings, pinyin = _load_chat_filter()
        assert substrings == _FALLBACK_SUBSTRINGS
        assert pinyin == _FALLBACK_PINYIN

    def test_loads_custom_rules(self, tmp_path):
        data = {"substrings": ["壞詞"], "pinyin": ["huaci"]}
        f = tmp_path / "chat_filter.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        with patch("twitch.components.ai._CHAT_FILTER_PATH", f):
            substrings, pinyin = _load_chat_filter()
        assert substrings == ["壞詞"]
        assert pinyin == ["huaci"]

    def test_fallback_on_invalid_json(self, tmp_path):
        f = tmp_path / "chat_filter.json"
        f.write_text("not valid json {{", encoding="utf-8")
        with patch("twitch.components.ai._CHAT_FILTER_PATH", f):
            substrings, pinyin = _load_chat_filter()
        assert substrings == _FALLBACK_SUBSTRINGS
        assert pinyin == _FALLBACK_PINYIN

    def test_fallback_for_missing_keys(self, tmp_path):
        # JSON exists but has no "substrings" or "pinyin" keys
        f = tmp_path / "chat_filter.json"
        f.write_text(json.dumps({}), encoding="utf-8")
        with patch("twitch.components.ai._CHAT_FILTER_PATH", f):
            substrings, pinyin = _load_chat_filter()
        assert substrings == _FALLBACK_SUBSTRINGS
        assert pinyin == _FALLBACK_PINYIN
