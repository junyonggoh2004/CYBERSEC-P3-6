"""
Ties bitstream/payload/crypto/start_location together into the two
operations the API (app.py) actually calls: encode() and decode(), plus a
capacity_check() used by the GUI's live capacity/fit indicator.

This module knows nothing about Flask or HTTP - it only deals in bytes and
plain dicts/dataclasses, so it is directly unit-testable (see tests/).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import audio_lsb, crypto_utils, image_lsb, payload, start_location, video_lsb
from .bitstream import StegoStream, capacity_units, validate_num_lsb
from .payload import VerificationError
from .video_lsb import VideoError

SUPPORTED_COVER_TYPES = ("image", "audio", "video")


class StegoError(Exception):
    """Generic, user-facing error (bad input, capacity, unsupported format)."""


def _load_carrier(cover_type: str, cover_bytes: bytes):
    if cover_type == "image":
        return image_lsb.load_image_carrier(cover_bytes)
    if cover_type == "audio":
        return audio_lsb.load_audio_carrier(cover_bytes)
    raise StegoError(f"Unknown cover_type {cover_type!r}, expected 'image' or 'audio'.")


def _carrier_array(cover_type: str, carrier):
    return carrier.array


def _describe(cover_type: str, carrier) -> dict:
    return image_lsb.describe(carrier) if cover_type == "image" else audio_lsb.describe(carrier)


def _resolve_start(
    cover_type: str,
    carrier,
    num_lsb: int,
    start_mode: str,
    manual_offset: int | None,
    passphrase: str | None,
) -> tuple[int, bytes]:
    """Returns (start_index, cover_stable_hash). cover_stable_hash is over the
    *whole* carrier as it stands right now (pre-embedding at encode time,
    post-extraction at decode time), masking num_lsb bits - see
    crypto_utils.stable_cover_hash."""
    arr = _carrier_array(cover_type, carrier)
    stable_hash = crypto_utils.stable_cover_hash(arr, num_lsb)
    cap_units = capacity_units(arr, 0)
    start_index = start_location.resolve_start_index(
        start_mode, cap_units, stable_hash, manual_offset=manual_offset, passphrase=passphrase
    )
    return start_index, stable_hash


@dataclass
class CapacityInfo:
    cover_type: str
    total_units: int
    num_lsb: int
    start_index: int
    capacity_bytes: int
    cover_info: dict = field(default_factory=dict)


def _capacity_check_core(
    cover_type: str,
    cover_bytes: bytes,
    num_lsb: int,
    start_mode: str = "manual",
    manual_offset: int | None = 0,
    passphrase: str | None = None,
) -> CapacityInfo:
    num_lsb = validate_num_lsb(num_lsb)
    carrier = _load_carrier(cover_type, cover_bytes)
    arr = _carrier_array(cover_type, carrier)
    start_index, _ = _resolve_start(cover_type, carrier, num_lsb, start_mode, manual_offset, passphrase)
    cap_bytes = ((len(arr) - start_index) * num_lsb) // 8
    return CapacityInfo(
        cover_type=cover_type,
        total_units=len(arr),
        num_lsb=num_lsb,
        start_index=start_index,
        capacity_bytes=max(0, cap_bytes),
        cover_info=_describe(cover_type, carrier),
    )


@dataclass
class EncodeResult:
    stego_bytes: bytes
    stego_filename: str
    mime: str
    start_index: int
    num_lsb: int
    metadata: dict
    payload_hash_hex: str
    signature_hex: str
    container_size_bytes: int
    capacity_bytes: int
    cover_info: dict


def _encode_core(
    cover_type: str,
    cover_bytes: bytes,
    payload_type: str,
    data: bytes,
    filename: str | None,
    mime: str | None,
    num_lsb: int,
    start_mode: str,
    manual_offset: int | None,
    passphrase: str | None,
    media_id: str,
    team_metadata: dict,
    stego_out_name: str,
) -> EncodeResult:
    num_lsb = validate_num_lsb(num_lsb)
    if payload_type not in payload.PAYLOAD_TYPE_CODES:
        raise StegoError(f"Unknown payload_type {payload_type!r}.")

    carrier = _load_carrier(cover_type, cover_bytes)
    arr = _carrier_array(cover_type, carrier)

    try:
        start_index, stable_hash = _resolve_start(
            cover_type, carrier, num_lsb, start_mode, manual_offset, passphrase
        )
    except ValueError as exc:
        raise StegoError(str(exc)) from exc

    built = payload.build_container(
        data=data,
        payload_type=payload_type,
        media_id=media_id,
        filename=filename,
        mime=mime,
        team_metadata=team_metadata,
        cover_stable_hash=stable_hash,
    )

    stream = StegoStream(arr, start_index, num_lsb)
    cap_bytes = stream.capacity_bytes()
    try:
        payload.write_container(stream, built)
    except ValueError as exc:
        raise StegoError(str(exc)) from exc

    if cover_type == "image":
        stego_bytes = image_lsb.carrier_to_png_bytes(carrier)
        out_mime = "image/png"
    else:
        stego_bytes = audio_lsb.carrier_to_wav_bytes(carrier)
        out_mime = "audio/wav"

    return EncodeResult(
        stego_bytes=stego_bytes,
        stego_filename=stego_out_name,
        mime=out_mime,
        start_index=start_index,
        num_lsb=num_lsb,
        metadata=built.metadata,
        payload_hash_hex=built.payload_hash_hex,
        signature_hex=built.signature_hex,
        container_size_bytes=len(built.raw),
        capacity_bytes=cap_bytes,
        cover_info=_describe(cover_type, carrier),
    )


@dataclass
class DecodeResult:
    verdict: str
    detail: str
    payload_type: str | None
    metadata: dict | None
    data: bytes | None
    payload_hash_match: bool | None
    signature_valid: bool | None
    cover_hash_match: bool | None
    start_index: int | None
    cover_info: dict


def _decode_core(
    cover_type: str,
    stego_bytes: bytes,
    num_lsb: int,
    start_mode: str,
    manual_offset: int | None,
    passphrase: str | None,
    public_key_pem: bytes | None,
) -> DecodeResult:
    empty = dict(
        payload_type=None,
        metadata=None,
        data=None,
        payload_hash_match=None,
        signature_valid=None,
        cover_hash_match=None,
    )

    try:
        num_lsb = validate_num_lsb(num_lsb)
        carrier = _load_carrier(cover_type, stego_bytes)
    except Exception as exc:  # malformed/unsupported file - never crash the server
        return DecodeResult(verdict="Cannot Verify", detail=str(exc), start_index=None, cover_info={}, **empty)

    arr = _carrier_array(cover_type, carrier)
    cover_info = _describe(cover_type, carrier)

    try:
        start_index, stable_hash = _resolve_start(
            cover_type, carrier, num_lsb, start_mode, manual_offset, passphrase
        )
    except ValueError as exc:
        return DecodeResult(verdict="Wrong Start Location", detail=str(exc), start_index=None, cover_info=cover_info, **empty)

    try:
        public_key = crypto_utils.load_public_key(public_key_pem) if public_key_pem else None
    except Exception as exc:
        return DecodeResult(verdict="Cannot Verify", detail=f"Invalid public key: {exc}", start_index=start_index, cover_info=cover_info, **empty)

    stream = StegoStream(arr, start_index, num_lsb)

    try:
        result = payload.read_and_verify(
            stream,
            cover_stable_hash=stable_hash,
            public_key=public_key,
            wrong_start_location_hint=(start_mode == "passphrase"),
        )
    except VerificationError as exc:
        return DecodeResult(verdict=exc.verdict, detail=exc.message, start_index=start_index, cover_info=cover_info, **empty)
    except Exception as exc:  # belt-and-braces: any unexpected parse error becomes "Cannot Verify"
        return DecodeResult(verdict="Cannot Verify", detail=str(exc), start_index=start_index, cover_info=cover_info, **empty)

    return DecodeResult(
        verdict=result.verdict,
        detail=result.detail,
        payload_type=result.payload_type,
        metadata=result.metadata,
        data=result.data,
        payload_hash_match=result.payload_hash_match,
        signature_valid=result.signature_valid,
        cover_hash_match=result.cover_hash_match,
        start_index=start_index,
        cover_info=cover_info,
    )


# --------------------------------------------------------------------------
# Video cover objects (optional challenge): hide the payload in the video's
# *audio track* by delegating to the exact same audio pipeline above, with an
# ffmpeg demux/remux step on either side. See video_lsb.py for why.
# --------------------------------------------------------------------------
def _mark_as_video(info: dict) -> dict:
    info = dict(info)
    info["embedded_in"] = "audio_track"
    return info


def capacity_check(
    cover_type: str,
    cover_bytes: bytes,
    num_lsb: int,
    start_mode: str = "manual",
    manual_offset: int | None = 0,
    passphrase: str | None = None,
) -> CapacityInfo:
    if cover_type != "video":
        return _capacity_check_core(cover_type, cover_bytes, num_lsb, start_mode, manual_offset, passphrase)

    try:
        wav_bytes, video_info = video_lsb.extract_audio_track(cover_bytes)
    except VideoError as exc:
        raise StegoError(str(exc)) from exc

    info = _capacity_check_core("audio", wav_bytes, num_lsb, start_mode, manual_offset, passphrase)
    info.cover_type = "video"
    info.cover_info = _mark_as_video({**video_info, **info.cover_info})
    return info


def encode(
    cover_type: str,
    cover_bytes: bytes,
    payload_type: str,
    data: bytes,
    filename: str | None,
    mime: str | None,
    num_lsb: int,
    start_mode: str,
    manual_offset: int | None,
    passphrase: str | None,
    media_id: str,
    team_metadata: dict,
    stego_out_name: str,
) -> EncodeResult:
    if cover_type != "video":
        return _encode_core(
            cover_type, cover_bytes, payload_type, data, filename, mime, num_lsb,
            start_mode, manual_offset, passphrase, media_id, team_metadata, stego_out_name,
        )

    try:
        wav_bytes, video_info = video_lsb.extract_audio_track(cover_bytes)
    except VideoError as exc:
        raise StegoError(str(exc)) from exc

    result = _encode_core(
        "audio", wav_bytes, payload_type, data, filename, mime, num_lsb,
        start_mode, manual_offset, passphrase, media_id, team_metadata, "stego_audio_track.wav",
    )

    try:
        stego_video_bytes = video_lsb.remux_with_new_audio(cover_bytes, result.stego_bytes)
    except VideoError as exc:
        raise StegoError(str(exc)) from exc

    result.stego_bytes = stego_video_bytes
    result.stego_filename = stego_out_name
    result.mime = "video/x-matroska"
    result.cover_info = _mark_as_video({**video_info, **result.cover_info})
    return result


def decode(
    cover_type: str,
    stego_bytes: bytes,
    num_lsb: int,
    start_mode: str,
    manual_offset: int | None,
    passphrase: str | None,
    public_key_pem: bytes | None,
) -> DecodeResult:
    if cover_type != "video":
        return _decode_core(cover_type, stego_bytes, num_lsb, start_mode, manual_offset, passphrase, public_key_pem)

    try:
        wav_bytes, video_info = video_lsb.extract_audio_track(stego_bytes)
    except VideoError as exc:
        return DecodeResult(
            verdict="Cannot Verify", detail=str(exc), payload_type=None, metadata=None, data=None,
            payload_hash_match=None, signature_valid=None, cover_hash_match=None, start_index=None, cover_info={},
        )

    result = _decode_core("audio", wav_bytes, num_lsb, start_mode, manual_offset, passphrase, public_key_pem)
    result.cover_info = _mark_as_video({**video_info, **result.cover_info})
    return result
