"""
Verification-payload container format (FR3) and its signing/verification
logic (FR4, FR9, FR10).

Wire format (all integers big-endian; written/read sequentially through a
StegoStream so every field can have variable length):

  MAGIC            4 bytes   b"STG1"
  VERSION          1 byte
  PAYLOAD_TYPE     1 byte    0=text, 1=file, 2=audio
  META_LEN         2 bytes   (16-bit)  length of the metadata JSON block
  META             META_LEN bytes, UTF-8 JSON: media_id, timestamp, nonce,
                             filename, mime, team metadata, and cover_hash
                             (the cover's stable/LSB-masked SHA-256 at embed
                             time - see crypto_utils.stable_cover_hash)
  PAYLOAD_HASH     32 bytes  SHA-256 of DATA
  SIG_LEN          2 bytes   (16-bit)  length of SIGNATURE
  SIGNATURE        SIG_LEN bytes  RSA-2048 signature over (PAYLOAD_HASH ||
                             sha256(META)) - META already carries cover_hash,
                             so tampering the cover after signing is caught
                             by comparing cover_hash to a fresh recomputation
                             (see read_and_verify), while tampering META
                             itself is caught by the signature.
  DATA_LEN         4 bytes   (32-bit)  length of DATA - deliberately 32-bit
                             so a payload can exceed 64KB (e.g. an embedded
                             MP3), while the smaller header fields above use
                             a 16-bit length since they are always small.
  DATA             DATA_LEN bytes  the actual hidden content

The 32-bit DATA_LEN together with the 16-bit META_LEN/SIG_LEN is the "16-bit
and 32-bit" length-field flexibility called for in the spec: short,
predictable header fields stay compact (16-bit) while the user payload
itself is free to be large (32-bit, up to 4GB, bounded in practice by cover
capacity).
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass

from . import crypto_utils
from .bitstream import StegoStream

MAGIC = b"STG1"
VERSION = 1

PAYLOAD_TYPE_TEXT = 0
PAYLOAD_TYPE_FILE = 1
PAYLOAD_TYPE_AUDIO = 2

PAYLOAD_TYPE_NAMES = {PAYLOAD_TYPE_TEXT: "text", PAYLOAD_TYPE_FILE: "file", PAYLOAD_TYPE_AUDIO: "audio"}
PAYLOAD_TYPE_CODES = {v: k for k, v in PAYLOAD_TYPE_NAMES.items()}


class VerificationError(Exception):
    """Raised for well-defined verification failures; caught by pipeline.py
    and turned into a verdict rather than an HTTP 500."""

    def __init__(self, verdict: str, message: str):
        super().__init__(message)
        self.verdict = verdict
        self.message = message


@dataclass
class BuiltContainer:
    raw: bytes
    parts: list  # the same fields as `raw`, but kept separate - see write_container()
    metadata: dict
    payload_hash_hex: str
    signature_hex: str


def build_container(
    data: bytes,
    payload_type: str,
    media_id: str,
    filename: str | None,
    mime: str | None,
    team_metadata: dict,
    cover_stable_hash: bytes,
    private_key=None,
) -> BuiltContainer:
    type_code = PAYLOAD_TYPE_CODES[payload_type]
    metadata = {
        "media_id": media_id or f"MEDIA-{uuid.uuid4().hex[:8]}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "nonce": os.urandom(8).hex(),
        "filename": filename or "",
        "mime": mime or "application/octet-stream",
        "team": team_metadata or {},
        # Stable hash of the cover (LSBs masked out) at embed time. Because
        # this travels *inside* the signed metadata, an attacker cannot
        # quietly update it to match a tampered cover without also breaking
        # the signature - see read_and_verify() below.
        "cover_hash": cover_stable_hash.hex(),
    }
    meta_bytes = json.dumps(metadata, separators=(",", ":")).encode("utf-8")
    if len(meta_bytes) > 0xFFFF:
        raise ValueError("Metadata block too large.")

    payload_hash = crypto_utils.sha256(data)
    signed_message = payload_hash + crypto_utils.sha256(meta_bytes)
    signature = crypto_utils.sign(signed_message, private_key)
    if len(signature) > 0xFFFF:
        raise ValueError("Signature unexpectedly large.")

    parts = [
        MAGIC,
        bytes([VERSION]),
        bytes([type_code]),
        len(meta_bytes).to_bytes(2, "big"),
        meta_bytes,
        payload_hash,
        len(signature).to_bytes(2, "big"),
        signature,
        len(data).to_bytes(4, "big"),
        data,
    ]
    return BuiltContainer(
        raw=b"".join(parts),
        parts=parts,
        metadata=metadata,
        payload_hash_hex=payload_hash.hex(),
        signature_hex=signature.hex(),
    )


def write_container(stream: StegoStream, container: BuiltContainer) -> None:
    total_len = len(container.raw)
    capacity = stream.capacity_bytes()
    if total_len > capacity:
        raise ValueError(
            f"Payload does not fit: container needs {total_len} bytes but only "
            f"{capacity} bytes are available from the selected start location "
            f"(cover size / LSB depth / start offset too small for this payload)."
        )
    # Written field-by-field (matching read_and_verify()'s read granularity
    # exactly) rather than as one contiguous blob. When num_lsb doesn't evenly
    # divide 8 (e.g. 3, 5, 6, 7), each field's last carrier unit only holds a
    # fractional number of payload bits and gets zero-padded; that padding
    # must land in the same place on read as it did on write, which only
    # happens if both sides split the stream into the same fields.
    for part in container.parts:
        stream.write(part)


@dataclass
class ParsedResult:
    verdict: str
    payload_type: str
    metadata: dict
    data: bytes
    payload_hash_match: bool
    signature_valid: bool
    cover_hash_match: bool
    detail: str


def read_and_verify(
    stream: StegoStream,
    cover_stable_hash: bytes,
    public_key=None,
    wrong_start_location_hint: bool = False,
) -> ParsedResult:
    try:
        magic = stream.read(4)
    except ValueError as exc:
        raise VerificationError("Cannot Verify", str(exc)) from exc

    if magic != MAGIC:
        verdict = "Wrong Start Location" if wrong_start_location_hint else "Payload Missing"
        raise VerificationError(
            verdict,
            "No valid payload signature found at the given start location. "
            "Either the start location/passphrase is wrong, or nothing was ever embedded there.",
        )

    try:
        version = stream.read(1)[0]
        type_code = stream.read(1)[0]
        if type_code not in PAYLOAD_TYPE_NAMES:
            raise VerificationError("Cannot Verify", f"Unknown payload type code {type_code}.")
        meta_len = int.from_bytes(stream.read(2), "big")
        meta_bytes = stream.read(meta_len)
        metadata = json.loads(meta_bytes.decode("utf-8"))
        payload_hash = stream.read(32)
        sig_len = int.from_bytes(stream.read(2), "big")
        signature = stream.read(sig_len)
        data_len = int.from_bytes(stream.read(4), "big")
        data = stream.read(data_len)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, IndexError) as exc:
        raise VerificationError(
            "Cannot Verify",
            f"Container is malformed or truncated at the given start location ({exc}).",
        ) from exc

    # 1) Authenticity: does the signature verify against (payload_hash, metadata)
    #    exactly as they were embedded? This is independent of what the cover
    #    looks like today - it only certifies "this hash+metadata pair was
    #    signed by the holder of the private key".
    signed_message = payload_hash + crypto_utils.sha256(meta_bytes)
    signature_valid = crypto_utils.verify(signed_message, signature, public_key)

    # 2) Payload integrity: does the extracted DATA still match the hash that
    #    was signed? A mismatch here means the hidden data itself was
    #    corrupted/edited after embedding, even if the signature (which only
    #    covers the *hash*, not the data) still verifies.
    payload_hash_match = crypto_utils.sha256(data) == payload_hash

    # 3) Cover integrity: does the cover's stable (LSB-masked) hash today
    #    match the one that was signed inside the metadata? A mismatch means
    #    the visible/audible content was altered after signing, independent
    #    of the hidden payload.
    embedded_cover_hash = metadata.get("cover_hash")
    cover_hash_match = embedded_cover_hash == cover_stable_hash.hex()

    if not signature_valid:
        verdict = "Signature Invalid"
        detail = (
            "The digital signature does not verify against the supplied public key. This means "
            "either the wrong key pair was used, or the signed hash/metadata was tampered with."
        )
    elif not payload_hash_match:
        verdict = "Tampered"
        detail = "The extracted payload's hash does not match the signed hash - the hidden data was altered after embedding."
    elif not cover_hash_match:
        verdict = "Tampered"
        detail = (
            "The payload itself is intact and correctly signed, but the cover file's "
            "visible/audible content has changed since signing (stable-hash mismatch)."
        )
    else:
        verdict = "Authentic"
        detail = "Hash matches, signature verifies, and the cover's stable hash is unchanged since signing."

    return ParsedResult(
        verdict=verdict,
        payload_type=PAYLOAD_TYPE_NAMES[type_code],
        metadata=metadata,
        data=data,
        payload_hash_match=payload_hash_match,
        signature_valid=signature_valid,
        cover_hash_match=cover_hash_match,
        detail=detail,
    )
