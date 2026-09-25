"""Versioned signed records. V1 remains readable; V2 supports SHA-256/SHA-512.
Each field rounds up to whole carrier units, matching the original wire layout.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field

from . import crypto_utils
from .bitstream import StegoStream

MAGIC = b"STG1"
VERSION = 2
PAYLOAD_TYPE_TEXT, PAYLOAD_TYPE_FILE, PAYLOAD_TYPE_AUDIO = 0, 1, 2
PAYLOAD_TYPE_NAMES = {0: "text", 1: "file", 2: "audio", 3: "image", 4: "video"}
PAYLOAD_TYPE_CODES = {v: k for k, v in PAYLOAD_TYPE_NAMES.items()}


class VerificationError(Exception):
    def __init__(self, verdict, message, reason_code="MALFORMED_PACKAGE"):
        super().__init__(message)
        self.verdict, self.message, self.reason_code = verdict, message, reason_code


@dataclass
class BuiltContainer:
    raw: bytes
    parts: list
    metadata: dict
    payload_hash_hex: str
    signature_hex: str

    def required_units(self, num_lsb):
        return sum((len(part) * 8 + num_lsb - 1) // num_lsb for part in self.parts)


def build_container(data, payload_type, media_id, filename, mime, team_metadata,
                    cover_stable_hash, private_key=None, hash_algorithm="SHA-256",
                    settings=None) -> BuiltContainer:
    crypto_utils.hash_algorithm(hash_algorithm)
    if not isinstance(team_metadata, dict):
        raise ValueError("Team metadata must be a JSON object.")
    private_key = private_key or crypto_utils.load_private_key()
    metadata = {
        "media_id": media_id or f"MEDIA-{uuid.uuid4().hex[:8]}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "nonce": os.urandom(8).hex(), "filename": filename or "",
        "mime": mime or "application/octet-stream", "team": team_metadata,
        "cover_hash": cover_stable_hash.hex(), "hash_algorithm": hash_algorithm,
        "payload_type": payload_type, "content_size_bytes": len(data),
        "signer_fingerprint": crypto_utils.fingerprint(private_key),
        "signature_algorithm": "RSA-PKCS1v1.5", "settings": settings or {},
    }
    meta_bytes = json.dumps(metadata, separators=(",", ":")).encode("utf-8")
    if len(meta_bytes) > 65535:
        raise ValueError("Metadata block too large.")
    payload_hash = crypto_utils.digest(data, hash_algorithm)
    signature = crypto_utils.sign(payload_hash + crypto_utils.digest(meta_bytes, hash_algorithm),
                                  private_key, hash_algorithm)
    parts = [MAGIC, bytes([VERSION]), bytes([PAYLOAD_TYPE_CODES[payload_type]]),
             len(meta_bytes).to_bytes(2, "big"), meta_bytes, payload_hash,
             len(signature).to_bytes(2, "big"), signature, len(data).to_bytes(4, "big"), data]
    return BuiltContainer(b"".join(parts), parts, metadata, payload_hash.hex(), signature.hex())


def write_container(stream: StegoStream, container: BuiltContainer):
    required = container.required_units(stream.num_lsb)
    available = len(stream.carrier) - stream.start_index - stream.pos_units
    if required > available:
        raise ValueError(f"Payload does not fit: package needs {required} carrier units "
                         f"including field padding; only {available} are available. "
                         "Increase LSB depth, reduce content, or change cover/start location.")
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
    evidence: dict = field(default_factory=dict)


def read_and_verify(stream, cover_stable_hash, public_key=None,
                    wrong_start_location_hint=False, cover_hash_factory=None):
    try:
        if stream.read(4) != MAGIC:
            raise VerificationError("Payload Missing",
                "No recognised payload at these settings. The start location or LSB depth "
                "may be wrong, the header may be damaged, or no supported payload is present.",
                "NO_RECOGNISED_PAYLOAD")
        version = stream.read(1)[0]
        if version not in (1, 2):
            raise ValueError(f"Unsupported container version {version}.")
        type_code = stream.read(1)[0]
        if type_code not in PAYLOAD_TYPE_NAMES:
            raise ValueError("Unknown payload type.")
        meta_bytes = stream.read(int.from_bytes(stream.read(2), "big"))
        metadata = json.loads(meta_bytes.decode("utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("Verification record must be an object.")
        algorithm = metadata.get("hash_algorithm", "SHA-256") if version == 2 else "SHA-256"
        payload_hash = stream.read(crypto_utils.hash_algorithm(algorithm).digest_size)
        signature = stream.read(int.from_bytes(stream.read(2), "big"))
        data_len = int.from_bytes(stream.read(4), "big")
        data = stream.read(data_len)
    except (ValueError, UnicodeDecodeError, IndexError) as exc:
        raise VerificationError("Cannot Verify", f"Malformed or truncated package: {exc}") from exc

    signature_valid = crypto_utils.verify(payload_hash + crypto_utils.digest(meta_bytes, algorithm),
                                           signature, public_key, algorithm)
    actual_payload = crypto_utils.digest(data, algorithm).hex()
    actual_cover = (cover_hash_factory(algorithm, version) if cover_hash_factory
                    else cover_stable_hash).hex()
    payload_match = actual_payload == payload_hash.hex()
    cover_match = actual_cover == metadata.get("cover_hash")
    settings = metadata.get("settings", {})
    record_match = version == 1 or (metadata.get("payload_type") == PAYLOAD_TYPE_NAMES[type_code]
        and metadata.get("content_size_bytes") == data_len
        and isinstance(settings, dict) and settings.get("num_lsb") == stream.num_lsb)
    if not signature_valid:
        verdict, reason = "Signature Invalid", "SIGNATURE_INVALID"
        detail = "The supplied public key does not validate the record. The key may be wrong, or the signature/record may have changed."
    elif not record_match:
        verdict, reason = "Tampered", "SIGNED_SETTINGS_MISMATCH"
        detail = "Package type, length or LSB depth differs from its signed record."
    elif not payload_match:
        verdict, reason = "Tampered", "PAYLOAD_HASH_MISMATCH"
        detail = "Recovered content differs from the hash in the valid signed record."
    elif not cover_match:
        verdict, reason = "Tampered", "COVER_HASH_MISMATCH"
        detail = "The stable carrier representation differs from the valid signed record."
    else:
        verdict, reason = "Authentic", "ALL_CHECKS_PASSED"
        detail = "The signature, content hash and stable cover hash pass under the supplied public key."
    evidence = {"reason_code": reason, "container_version": version,
        "hash_algorithm": algorithm, "expected_payload_hash": payload_hash.hex(),
        "actual_payload_hash": actual_payload, "expected_cover_hash": metadata.get("cover_hash"),
        "actual_cover_hash": actual_cover, "signature_hex": signature.hex(),
        "signature_algorithm": f"RSA-PKCS1v1.5 / {algorithm}", "record_match": record_match,
        "record_trust": "Signature verified" if signature_valid else "Unverified"}
    return ParsedResult(verdict, PAYLOAD_TYPE_NAMES[type_code], metadata, data,
                        payload_match, signature_valid, cover_match, detail, evidence)
