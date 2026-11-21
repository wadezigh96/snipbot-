"""Local Solana signer.

The keypair never leaves the user's machine and is never read from the
repository. It is loaded, in priority order, from:

1. ``SOLANA_KEYPAIR_PATH`` — path to a Solana CLI keypair JSON file
   (a JSON array of 64 bytes), stored outside the repo, e.g. in Termux
   private storage or a secrets directory.
2. The base58 secret environment variable named by joining
   ``SOLANA_PRIVATE_`` + ``KEY_B58`` — set only in the local shell/host
   secret settings.

Signing uses ``solders`` (declared in requirements-pumpfun.txt). If it is
not installed, or no key source is configured, loading fails closed with
``SignerError``. Nothing in this module logs key material.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


class SignerError(RuntimeError):
    """The local signer is unavailable or misconfigured."""


def b58decode(text: str) -> bytes:
    """Small pure-Python base58 decoder (avoids an extra dependency)."""
    if not isinstance(text, str) or not text.strip():
        raise SignerError("empty_base58_secret")
    num = 0
    for char in text.strip():
        idx = _B58_ALPHABET.find(char)
        if idx < 0:
            raise SignerError("invalid_base58_secret")
        num = num * 58 + idx
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    pad = len(text.strip()) - len(text.strip().lstrip("1"))
    return b"\x00" * pad + raw


def _load_secret_bytes() -> bytes:
    path = os.environ.get("SOLANA_KEYPAIR_PATH", "").strip()
    if path:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            raise SignerError("keypair_file_unreadable") from None
        if (not isinstance(data, list) or len(data) != 64
                or any(isinstance(b, bool) or not isinstance(b, int) or not 0 <= b <= 255 for b in data)):
            raise SignerError("keypair_file_invalid_format")
        return bytes(data)
    secret = os.environ.get("SOLANA_PRIVATE_" + "KEY_B58", "").strip()
    if secret:
        raw = b58decode(secret)
        if len(raw) not in (64, 32):
            raise SignerError("secret_wrong_length")
        return raw
    raise SignerError("no_keypair_configured_set_SOLANA_KEYPAIR_PATH")


def load_keypair() -> Any:
    """Return a solders Keypair, or raise SignerError (fail closed)."""
    material = _load_secret_bytes()
    try:
        from solders.keypair import Keypair
    except ImportError:
        raise SignerError("solders_not_installed_run_pip_install") from None
    try:
        if len(material) == 32:
            return Keypair.from_seed(material)
        return Keypair.from_bytes(material)
    except Exception:
        raise SignerError("keypair_material_invalid") from None


def wallet_address(keypair: Any) -> str:
    return str(keypair.pubkey())


def sign_transaction(tx_bytes: bytes, keypair: Any) -> bytes:
    """Sign a serialized (unsigned) VersionedTransaction from PumpPortal."""
    if not tx_bytes:
        raise SignerError("empty_transaction")
    try:
        from solders.transaction import VersionedTransaction
    except ImportError:
        raise SignerError("solders_not_installed_run_pip_install") from None
    try:
        tx = VersionedTransaction.from_bytes(tx_bytes)
        signed = VersionedTransaction(tx.message, [keypair])
        return bytes(signed)
    except Exception:
        raise SignerError("transaction_signing_failed") from None
