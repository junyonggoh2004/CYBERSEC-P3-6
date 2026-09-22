"""
Start-location selection and protection (FR7 / spec section 7 step 5 & 7).

Two modes are supported, chosen in the GUI:

  "manual"     - the user types/clicks an exact carrier-unit offset. Simple
                 and transparent for demoing the mechanics, but the offset
                 itself must then be shared out-of-band (e.g. told to the
                 verifier) since nothing in the stego file reveals it -
                 guessing it is a brute-force search over the whole capacity.

  "passphrase" - the offset is *derived*, never stored anywhere, from
                 HMAC-SHA256(passphrase, stable_cover_hash) mod capacity.
                 The stable hash used for location derivation always uses SHA-256,
                 independently of the selected content hash. Both parties can
                 derive it before reading the embedded record. This is not
                 encryption: an attacker may still scan candidate offsets.
                 Weak passphrases can also be guessed. Cover changes may change
                 the derived offset and prevent extraction altogether.

An unreadable marker cannot prove the location was wrong. The decoder reports
Payload Missing with an explanation of wrong settings, corruption or absence.

"""
from __future__ import annotations

import hashlib
import hmac

# Leave head-room so short covers still have room for the container header
# even when the derived offset lands late in the carrier.
_MIN_RESERVED_UNITS = 64


def derive_offset(passphrase: str, cover_stable_hash: bytes, capacity_units: int) -> int:
    if capacity_units <= 0:
        raise ValueError("Cover has no usable capacity.")
    usable = max(1, capacity_units - min(_MIN_RESERVED_UNITS, capacity_units // 2))
    digest = hmac.new(passphrase.encode("utf-8"), cover_stable_hash, hashlib.sha256).digest()
    value = int.from_bytes(digest[:8], "big")
    return value % usable


def resolve_start_index(
    mode: str,
    capacity_units: int,
    cover_stable_hash: bytes,
    manual_offset: int | None = None,
    passphrase: str | None = None,
) -> int:
    mode = (mode or "manual").lower()
    if mode == "passphrase":
        if not passphrase:
            raise ValueError("A passphrase is required for passphrase-derived start location.")
        return derive_offset(passphrase, cover_stable_hash, capacity_units)
    if mode == "manual":
        offset = int(manual_offset or 0)
        if offset < 0 or offset >= capacity_units:
            raise ValueError(
                f"Manual start location {offset} is outside the cover's range (0..{capacity_units - 1})."
            )
        return offset
    raise ValueError(f"Unknown start-location mode: {mode!r}")
