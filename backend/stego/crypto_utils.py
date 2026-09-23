"""
Hashing and RSA digital-signature helpers.

- SHA-256 (default) or SHA-512 is used for payload and stable cover hashing.
- RSA with PKCS#1 v1.5 padding and the selected hash is used for signing, via the
  `cryptography` library. Keys are PEM files under keys/.

Design note on the "stable cover hash" (see pipeline.py step 2 of the spec):
LSB embedding necessarily changes the low-order bits of the cover, so hashing
the *whole* stego file can never match a hash of the *original* cover. To
still let a verifier detect tampering of the visible/audible content (as
opposed to the hidden payload itself), we hash the cover with its lowest
`num_lsb` bits masked to zero. V2 also binds carrier properties. That masked view is identical before and
after legitimate embedding, so any mismatch at verification time means the
non-hidden part of the file was altered after signing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import numpy as np
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

KEY_DIR = Path(__file__).resolve().parent.parent / "keys"
PRIVATE_KEY_PATH = KEY_DIR / "private_key.pem"
PUBLIC_KEY_PATH = KEY_DIR / "public_key.pem"


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def hash_algorithm(name="SHA-256"):
    if name not in ("SHA-256", "SHA-512"):
        raise ValueError("Hash algorithm must be SHA-256 or SHA-512.")
    return hashes.SHA256() if name == "SHA-256" else hashes.SHA512()


def digest(data: bytes, algorithm="SHA-256") -> bytes:
    return hashlib.new(hash_algorithm(algorithm).name, data).digest()


def stable_cover_hash(carrier: np.ndarray, num_lsb: int, algorithm="SHA-256", context=None) -> bytes:
    # Invert a small positive, already-typed value rather than casting a
    # negative Python int into an unsigned dtype (numpy >= 2 raises
    # OverflowError on the latter).
    keep_mask = np.array((1 << num_lsb) - 1, dtype=carrier.dtype)
    clear_mask = ~keep_mask
    masked = carrier & clear_mask
    prefix = json.dumps(context, sort_keys=True, separators=(",", ":")).encode() if context else b""
    return digest(prefix + masked.tobytes(), algorithm)


def ensure_key_dir() -> None:
    KEY_DIR.mkdir(parents=True, exist_ok=True)


def generate_keypair(overwrite: bool = False) -> tuple[Path, Path]:
    ensure_key_dir()
    if not overwrite and PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return PRIVATE_KEY_PATH, PUBLIC_KEY_PATH

    # Legacy callers may request rotation. Archive the existing pair first.
    if PRIVATE_KEY_PATH.exists():
        save_keypair(load_private_key())
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


def sign(data: bytes, private_key=None, algorithm="SHA-256") -> bytes:
    private_key = private_key or load_private_key()
    return private_key.sign(data, padding.PKCS1v15(), hash_algorithm(algorithm))


def verify(data: bytes, signature: bytes, public_key=None, algorithm="SHA-256") -> bool:
    public_key = public_key or load_public_key()
    try:
        public_key.verify(signature, data, padding.PKCS1v15(), hash_algorithm(algorithm))
        return True
    except Exception:
        return False


def fingerprint(key) -> str:
    if isinstance(key, rsa.RSAPrivateKey):
        key = key.public_key()
    if not isinstance(key, rsa.RSAPublicKey):
        raise ValueError("An RSA key is required.")
    return hashlib.sha256(key.public_bytes(serialization.Encoding.DER,
                          serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()


def key_description(key, key_id=None):
    public = key.public_key() if isinstance(key, rsa.RSAPrivateKey) else key
    fp = fingerprint(public)
    return {"key_id": key_id or fp, "fingerprint": fp, "bits": public.key_size,
            "public_key_pem": public.public_bytes(serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")}


def save_keypair(key):
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
        raise ValueError("Import an RSA private key of at least 2048 bits.")
    key_id = fingerprint(key)
    directory = KEY_DIR / "saved"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / (key_id + ".pem")
    if not destination.exists():
        destination.write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return key_description(key)


def signing_key(key_id=None):
    if not key_id or key_id == "legacy":
        return load_private_key()
    if not re.fullmatch(r"[0-9a-f]{64}", key_id):
        raise ValueError("Invalid signing key identifier.")
    path = KEY_DIR / "saved" / (key_id + ".pem")
    if not path.exists():
        raise ValueError("Signing key not found.")
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def list_signing_keys():
    # Derive the public half from the private key; do not rewrite a user's PEM.
    result = [key_description(load_private_key(), "legacy")]
    for path in sorted((KEY_DIR / "saved").glob("*.pem")):
        key = signing_key(path.stem)
        result.append(key_description(key))
    return result


def new_signing_key():
    return save_keypair(rsa.generate_private_key(public_exponent=65537, key_size=2048))
