"""ECPay-family CheckMacValue (CMV-SHA256 / CMV-MD5).

Pure functions, no I/O — validated against the official test vectors in
``.claude/skills/ecpay/guides/13-checkmacvalue.md`` (see tests/api/test_payment_cmv.py).

Algorithm (from the ECPay PHP SDK ``CheckMacValueService::generate``):
  1. drop any existing CheckMacValue
  2. sort keys case-insensitively
  3. build ``HashKey={key}&k1=v1&k2=v2&...&HashIV={iv}``
  4. ECPay URL-encode: quote_plus -> ~ to %7e -> lowercase -> restore .NET chars
  5. SHA-256 (or MD5) -> UPPERCASE hex
"""

from __future__ import annotations

import hashlib
import hmac
import urllib.parse

# .NET's HttpUtility leaves these unescaped; PHP urlencode escapes them, so the
# SDK restores them after encoding. We match the SDK.
_DOTNET_RESTORE: tuple[tuple[str, str], ...] = (
    ("%2d", "-"),
    ("%5f", "_"),
    ("%2e", "."),
    ("%21", "!"),
    ("%2a", "*"),
    ("%28", "("),
    ("%29", ")"),
)


def ecpay_url_encode(raw: str) -> str:
    """ECPay's bespoke URL encoding used only for CheckMacValue."""
    encoded = urllib.parse.quote_plus(raw)
    encoded = encoded.lower()
    for old, new in _DOTNET_RESTORE:
        encoded = encoded.replace(old, new)
    return encoded


def build_check_mac_value(
    params: dict[str, str],
    hash_key: str,
    hash_iv: str,
    *,
    method: str = "sha256",
) -> str:
    """Compute the CheckMacValue for *params* (UPPERCASE hex)."""
    filtered = {k: v for k, v in params.items() if k != "CheckMacValue"}
    sorted_pairs = sorted(filtered.items(), key=lambda kv: kv[0].lower())
    raw = (
        f"HashKey={hash_key}&"
        + "&".join(f"{k}={v}" for k, v in sorted_pairs)
        + f"&HashIV={hash_iv}"
    )
    encoded = ecpay_url_encode(raw)
    digest = hashlib.md5 if method == "md5" else hashlib.sha256
    return digest(encoded.encode("utf-8")).hexdigest().upper()


def verify_check_mac_value(
    params: dict[str, str],
    hash_key: str,
    hash_iv: str,
    *,
    method: str = "sha256",
) -> bool:
    """Constant-time check of the CheckMacValue carried in *params*."""
    received = params.get("CheckMacValue", "")
    calculated = build_check_mac_value(params, hash_key, hash_iv, method=method)
    return hmac.compare_digest(received.upper(), calculated)
