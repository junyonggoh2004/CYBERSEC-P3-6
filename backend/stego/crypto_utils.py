"""
Hashing and RSA digital-signature helpers.

- SHA-256 is used for both the payload hash and the "stable cover hash".
- RSA-2048 with PKCS#1 v1.5 padding over SHA-256 is used for signing, via the
  `cryptography` library. Keys are PEM files under keys/.

Design note on the "stable cover hash" (see pipeline.py step 2 of the spec):
LSB embedding necessarily changes the low-order bits of the cover, so hashing
the *whole* stego file can never match a hash of the *original* cover. To
still let a verifier detect tampering of the visible/audible content (as
opposed to the hidden payload itself), we hash the cover with its lowest
`num_lsb` bits masked to zero. That masked view is identical before and
after legitimate embedding, so any mismatch at verification time means the
non-hidden part of the file was altered after signing.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

KEY_DIR = Path(__file__).resolve().parent.parent / "keys"
PRIVATE_KEY_PATH = KEY_DIR / "private_key.pem"
PUBLIC_KEY_PATH = KEY_DIR / "public_key.pem"


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def stable_cover_hash(carrier: np.ndarray, num_lsb: int) -> bytes:
    # Invert a small positive, already-typed value rather than casting a
    # negative Python int into an unsigned dtype (numpy >= 2 raises
    # OverflowError on the latter).
    keep_mask = np.array((1 << num_lsb) - 1, dtype=carrier.dtype)
    clear_mask = ~keep_mask
    masked = carrier & clear_mask
    return sha256(masked.tobytes())


def ensure_key_dir() -> None:
    KEY_DIR.mkdir(parents=True, exist_ok=True)


def generate_keypair(overwrite: bool = False) -> tuple[Path, Path]:
    ensure_key_dir()
    if not overwrite and PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return PRIVATE_KEY_PATH, PUBLIC_KEY_PATH

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    PRIVATE_KEY_PATH.write_bytes(private_bytes)
    PUBLIC_KEY_PATH.write_bytes(public_bytes)
    return PRIVATE_KEY_PATH, PUBLIC_KEY_PATH


def load_private_key():
    if not PRIVATE_KEY_PATH.exists():
        generate_keypair()
    data = PRIVATE_KEY_PATH.read_bytes()
    return serialization.load_pem_private_key(data, password=None)


def load_public_key(public_key_pem: bytes | None = None):
    if public_key_pem is not None:
        return serialization.load_pem_public_key(public_key_pem)
    if not PUBLIC_KEY_PATH.exists():
        generate_keypair()
    return serialization.load_pem_public_key(PUBLIC_KEY_PATH.read_bytes())


def public_key_pem() -> bytes:
    if not PUBLIC_KEY_PATH.exists():
        generate_keypair()
    return PUBLIC_KEY_PATH.read_bytes()


def generate_decoy_public_key_pem() -> bytes:
    """A throwaway keypair's public key - never persisted, used only so the
    GUI can demonstrate the 'Signature Invalid' verdict by verifying against
    a syntactically valid but wrong key, without disturbing the real one."""
    decoy = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return decoy.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def sign(data: bytes, private_key=None) -> bytes:
    private_key = private_key or load_private_key()
    return private_key.sign(data, padding.PKCS1v15(), hashes.SHA256())


def verify(data: bytes, signature: bytes, public_key=None) -> bool:
    public_key = public_key or load_public_key()
    try:
        public_key.verify(signature, data, padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception:
        return False
