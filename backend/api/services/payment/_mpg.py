"""NewebPay MPG crypto (AES-256-CBC + SHA-256 TradeSha).

Pure functions, no I/O. Ported verbatim from the old donation_router helpers;
validated by tests/api/test_payment_mpg.py.
"""

from __future__ import annotations

import hashlib

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise ValueError("Empty data cannot be unpadded")
    pad_len = data[-1]
    if pad_len == 0 or pad_len > 16:
        raise ValueError(f"Invalid PKCS7 padding length: {pad_len}")
    if len(data) < pad_len:
        raise ValueError("Data shorter than padding length")
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        raise ValueError("Invalid PKCS7 padding bytes")
    return data[:-pad_len]


def aes_encrypt(plaintext: str, hash_key: str, hash_iv: str) -> str:
    """AES-256-CBC encrypt -> lowercase hex (NewebPay TradeInfo)."""
    padded = pkcs7_pad(plaintext.encode("utf-8"))
    cipher = Cipher(algorithms.AES(hash_key.encode("utf-8")), modes.CBC(hash_iv.encode("utf-8")))
    enc = cipher.encryptor()
    return (enc.update(padded) + enc.finalize()).hex()


def aes_decrypt(hex_data: str, hash_key: str, hash_iv: str) -> str:
    """AES-256-CBC decrypt from lowercase hex (NewebPay webhook TradeInfo)."""
    cipher = Cipher(algorithms.AES(hash_key.encode("utf-8")), modes.CBC(hash_iv.encode("utf-8")))
    dec = cipher.decryptor()
    padded = dec.update(bytes.fromhex(hex_data)) + dec.finalize()
    return pkcs7_unpad(padded).decode("utf-8")


def trade_sha256(trade_info_hex: str, hash_key: str, hash_iv: str) -> str:
    """SHA-256 of ``HashKey={key}&{trade_info}&HashIV={iv}`` -> UPPERCASE hex."""
    raw = f"HashKey={hash_key}&{trade_info_hex}&HashIV={hash_iv}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
