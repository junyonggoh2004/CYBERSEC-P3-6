"""
Flask backend for the steganographic image/audio integrity-verification tool
(INF2005 ACW1). Serves the single-page frontend and a small JSON API.

Every route is wrapped so a bad upload, wrong key, or malformed file returns
a structured JSON error instead of crashing the process ("no crashes"
requirement) - see the try/except in each handler plus the catch-all
errorhandler at the bottom.
"""
from __future__ import annotations

import base64
import json
import math
import mimetypes
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stego import analysis, audio_analysis, audio_metrics, comparison, crypto_utils, jobs, pipeline  # noqa: E402
from cryptography.hazmat.primitives import serialization
from stego import audio_lsb, image_lsb, payload, media_input, encryption, video_lsb
from stego.bitstream import StegoStream

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500MB - generous for demo audio/image/video files
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


@app.after_request
def prevent_stale_app_assets(response):
    # Python changes still require a server restart; always reload matching UI assets.
    response.headers["Cache-Control"] = "no-store"
    return response


# --------------------------------------------------------------------------
# Static frontend
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/favicon.ico")
def favicon():
    # No icon asset shipped - respond quietly instead of a 404/500 showing
    # up as a red error in the browser console during the demo.
    return "", 204


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _bad_request(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _int_or_none(value):
    if value is None or value == "":
        return None
    return int(value)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _guess_mime(filename: str | None, fallback: str = "application/octet-stream") -> str:
    if not filename:
        return fallback
    mime, _ = mimetypes.guess_type(filename)
    return mime or fallback


def _parse_common_fields(form):
    cover_type = form.get("cover_type", "").strip().lower()
    if cover_type not in pipeline.SUPPORTED_COVER_TYPES:
        raise ValueError("cover_type must be 'image', 'audio' or 'video'.")
    num_lsb = int(form.get("num_lsb", 1))
    start_mode = form.get("start_mode", "manual").strip().lower()
    manual_offset = _int_or_none(form.get("manual_offset"))
    passphrase = form.get("passphrase") or None
    return cover_type, num_lsb, start_mode, manual_offset, passphrase


# --------------------------------------------------------------------------
# Key management
# --------------------------------------------------------------------------
@app.post("/api/keys/generate")
def api_generate_keys():
    try:
        if request.form.get("role") == "bob":
            return jsonify(crypto_utils.replace_recipient_key())
        return jsonify(crypto_utils.new_signing_key())
    except Exception as exc:
        return _bad_request(f"Key generation failed: {exc}", 500)


@app.get("/api/keys/public")
def api_get_public_key():
    try:
        return jsonify(crypto_utils.key_description(crypto_utils.signing_key(request.args.get("key_id"))))
    except Exception as exc:
        return _bad_request(f"Could not load public key: {exc}", 500)


@app.get("/api/keys")
def api_keys():
    return jsonify({"keys": crypto_utils.list_signing_keys(),
                    "recipient": crypto_utils.key_description(crypto_utils.recipient_key())})


@app.post("/api/keys/export-private")
def api_export_private():
    key = crypto_utils.recipient_key() if request.form.get("role") == "bob" else crypto_utils.signing_key(request.form.get("key_id"))
    response = jsonify({"private_key_pem": crypto_utils.private_pem(key).decode()})
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/api/keys/import")
def api_import_key():
    try:
        upload = request.files.get("key_file")
        if upload is None:
            raise ValueError("Choose a PEM private key file.")
        raw = upload.read(32769)
        if len(raw) > 32768:
            raise ValueError("Key file is too large.")
        password = request.form.get("password")
        key = serialization.load_pem_private_key(raw, password.encode() if password else None)
        if request.form.get("role") == "bob":
            return jsonify(crypto_utils.replace_recipient_key(key))
        return jsonify(crypto_utils.save_keypair(key))
    except (ValueError, TypeError) as exc:
        return _bad_request(f"Key import failed: {exc}")


def _encryption_key(form):
    # Missing key selection uses the saved local demo recipient, never plaintext.
    pem = form.get("encryption_public_pem", crypto_utils.key_description(crypto_utils.recipient_key())["public_key_pem"]).strip()
    if not pem:
        raise ValueError("Supply Bob's public encryption key or load the saved demo key.")
    return pem.encode()


# Hidden-content files any cover can carry, keyed by payload type ("file" is a
# text document). Explicit MIME types: the OS registry guess is unreliable for
# formats such as .mkv on Windows.
CONTENT_MIME_TYPES = {
    "file": {".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv", ".json": "application/json"},
    "image": {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
              ".gif": "image/gif", ".bmp": "image/bmp",
              ".tif": "image/tiff", ".tiff": "image/tiff"},
    "audio": {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".flac": "audio/flac",
              ".m4a": "audio/mp4", ".aac": "audio/aac",
              ".aif": "audio/aiff", ".aiff": "audio/aiff"},
    "video": {".mp4": "video/mp4", ".m4v": "video/mp4", ".mkv": "video/x-matroska", ".mov": "video/quicktime",
              ".webm": "video/webm", ".avi": "video/x-msvideo"},
}


def _read_content(form, files, cover_type):
    kind = form.get("payload_type", "text")
    if kind == "text":
        text = form.get("payload_text", "")
        if not text:
            raise ValueError("Enter a text message.")
        return kind, text.encode("utf-8"), None, "text/plain"
    if kind not in CONTENT_MIME_TYPES:
        raise ValueError("Hidden content must be text, or a text, image, audio or video file.")
    upload = files.get("payload_file")
    if upload is None:
        raise ValueError("Choose a content file.")
    mime = CONTENT_MIME_TYPES[kind].get(Path(upload.filename or "").suffix.lower())
    if mime is None:
        raise ValueError(f"Choose a supported {'text' if kind == 'file' else kind} file.")
    data = upload.read()
    if not data:
        raise ValueError("Content file is empty.")
    return kind, data, upload.filename, mime


def _audio_metrics_json(metrics):
    """Cover-vs-stego distortion for a JSON response, or None when there is
    none. An infinite SNR (stego identical to the cover) is sent as null
    because Infinity is not valid JSON; snr_reference says why."""
    if metrics is None:
        return None
    return {
        "changed_sample_count": metrics.changed_samples,
        "total_samples": metrics.total_samples,
        "mse": metrics.mse,
        "snr_db": metrics.snr_db if math.isfinite(metrics.snr_db) else None,
        "snr_reference": metrics.snr_reference,
        "snr_display": metrics.snr_display,
        "max_sample_change": metrics.max_sample_change,
    }


def _cover_bytes(upload, cover_type):
    if upload is None:
        raise ValueError("Choose a cover file.")
    data = upload.read()
    if cover_type == "video":
        # Videos are demuxed to their audio track later; never re-encode them here.
        return data
    return media_input.normalise(data, cover_type, upload.filename)


@app.post("/api/prepare")
def api_prepare():
    try:
        form = request.form
        kind, depth, mode, offset, secret = _parse_common_fields(form)
        content_type, data, filename, mime = _read_content(form, request.files, kind)
        result = pipeline.prepare(kind, _cover_bytes(request.files.get("cover_file"), kind), data,
            payload_type=content_type, filename=filename, mime=mime, media_id=form.get("media_id", ""),
            team_metadata=json.loads(form.get("team_metadata") or "{}"), num_lsb=depth,
            start_mode=mode, manual_offset=offset, passphrase=secret,
            hash_algorithm=form.get("hash_algorithm", "SHA-256"), key_id=form.get("key_id"),
            encryption_public_pem=_encryption_key(form))
        return jsonify(result)
    except (ValueError, pipeline.StegoError) as exc:
        return _bad_request(str(exc))


@app.post("/api/compare")
def api_compare():
    try:
        kind = request.form.get("cover_type")
        if kind not in pipeline.SUPPORTED_COVER_TYPES:
            raise ValueError("Choose image, audio or video.")
        before = _cover_bytes(request.files.get("original_file"), kind)
        after = _cover_bytes(request.files.get("stego_file"), kind)
        if kind == "video":
            # Video payloads live in the audio track, so compare the two audio tracks.
            (before_wav, video_info), (after_wav, _) = pipeline.video_audio_track(before), pipeline.video_audio_track(after)
            result = comparison.compare("audio", before_wav, after_wav)
            result.update(cover_info={**video_info, **result["cover_info"], "embedded_in": "audio_track"},
                          original_size_bytes=len(before), stego_size_bytes=len(after))
        else:
            before_wav, after_wav = before, after
            result = comparison.compare(kind, before, after)
        if kind in ("audio", "video"):
            # Adds the SNR measured against the cover's own signal (with
            # silent/identical covers labelled) to the paired measurements.
            result["audio_metrics"] = _audio_metrics_json(audio_metrics.compare(
                audio_lsb.load_audio_carrier(before_wav).array,
                audio_lsb.load_audio_carrier(after_wav).array,
            ))
        return jsonify(result)
    except (ValueError, OSError, pipeline.StegoError) as exc:
        return _bad_request(str(exc))


@app.post("/api/demo/tamper")
def api_demo_tamper():
    """Make an in-memory demo copy; never overwrite the uploaded source."""
    try:
        kind, depth, mode, offset, secret = _parse_common_fields(request.form)
        data = _cover_bytes(request.files.get("stego_file"), kind)
        video_source = None
        if kind == "video":
            # Tamper with the audio track copy, then remux it with the original video stream.
            video_source, (data, _) = data, pipeline.video_audio_track(data)
            kind = "audio"
        carrier = pipeline._load_carrier(kind, data)
        index, _ = pipeline._resolve_start(kind, carrier, depth, mode, offset, secret)

        def modified_copy(detail):
            output = image_lsb.carrier_to_png_bytes(carrier) if kind == "image" else audio_lsb.carrier_to_wav_bytes(carrier)
            if video_source is not None:
                output = video_lsb.remux_with_new_audio(video_source, output)
            return jsonify({"stego_base64": _b64(output), "detail": detail})

        operation = request.form.get("tamper_mode")
        if operation == "payload":
            stream = StegoStream(carrier.array, index, depth)
            marker = stream.read(4)
            if marker == encryption.MAGIC:
                length = int.from_bytes(stream.read(4), "big")
                if length < 1 or length > stream.capacity_bytes():
                    raise ValueError("No valid encrypted package to modify.")
                # The body is one contiguous field; flip its last ciphertext byte.
                unit = index + stream.pos_units + ((length - 1) * 8 // depth)
                if unit >= len(carrier.array):
                    raise ValueError("Truncated encrypted package.")
                carrier.array[unit] ^= 1
                return modified_copy("Changed an encrypted package bit in a copy. Decryption should fail without releasing content.")
            if marker != payload.MAGIC:
                raise ValueError("No supported package at these extraction settings.")
            version = stream.read(1)[0]
            if version not in (1, 2):
                raise ValueError("Unsupported package version.")
            stream.read(1)
            record = json.loads(stream.read(int.from_bytes(stream.read(2), "big")))
            algorithm = record.get("hash_algorithm", "SHA-256") if version == 2 else "SHA-256"
            stream.read(crypto_utils.hash_algorithm(algorithm).digest_size)
            stream.read(int.from_bytes(stream.read(2), "big"))
            size = int.from_bytes(stream.read(4), "big")
            if size < 1 or size > stream.capacity_bytes():
                raise ValueError("No valid content to modify.")
            carrier.array[index + stream.pos_units] ^= 1
            detail = "Changed a content bit in a copy. The signed reference is unchanged; verify to demonstrate a payload-hash mismatch."
        elif operation == "cover":
            if kind == "image" and depth == 8:
                raise ValueError("All eight image-channel bits are excluded from the stable hash. Use depth 1-7 for this cover-integrity demonstration.")
            carrier.array[0] ^= 1 << depth
            detail = "Changed a protected cover bit in a copy. Manual extraction can show a cover-hash mismatch; a cover-derived location may instead become unreadable."
        else:
            raise ValueError("Choose payload or cover tampering.")
        return modified_copy(detail)
    except (ValueError, OSError, IndexError, pipeline.StegoError, video_lsb.VideoError) as exc:
        return _bad_request(str(exc))


@app.post("/api/keys/decoy")
def api_decoy_key():
    """Returns a fresh, throwaway public key (never persisted) so the GUI can
    demonstrate a 'Signature Invalid' negative case without disturbing the
    real key pair used elsewhere."""
    try:
        return jsonify({"public_key_pem": crypto_utils.generate_decoy_public_key_pem().decode("ascii")})
    except Exception as exc:
        return _bad_request(f"Could not generate decoy key: {exc}", 500)


# --------------------------------------------------------------------------
# Capacity check
# --------------------------------------------------------------------------
@app.post("/api/capacity")
def api_capacity():
    try:
        cover_type, num_lsb, start_mode, manual_offset, passphrase = _parse_common_fields(request.form)
        cover_file = request.files.get("cover_file")
        if cover_file is None:
            return _bad_request("cover_file is required.")
        info = pipeline.capacity_check(
            cover_type=cover_type,
            cover_bytes=_cover_bytes(cover_file, cover_type),
            num_lsb=num_lsb,
            start_mode=start_mode,
            manual_offset=manual_offset,
            passphrase=passphrase,
        )
        return jsonify(
            {
                "total_units": info.total_units,
                "num_lsb": info.num_lsb,
                "start_index": info.start_index,
                "capacity_bytes": info.capacity_bytes,
                "cover_info": info.cover_info,
            }
        )
    except (ValueError, pipeline.StegoError) as exc:
        return _bad_request(str(exc))
    except Exception as exc:
        return _bad_request(f"Could not read cover file: {exc}")


# --------------------------------------------------------------------------
# Encode
# --------------------------------------------------------------------------
@app.post("/api/encode")
def api_encode():
    try:
        form = request.form
        cover_type, num_lsb, start_mode, manual_offset, passphrase = _parse_common_fields(form)

        cover_file = request.files.get("cover_file")
        if cover_file is None:
            return _bad_request("cover_file is required.")

        payload_type, data, filename, mime = _read_content(form, request.files, cover_type)

        media_id = form.get("media_id", "")
        team_metadata_raw = form.get("team_metadata", "")
        try:
            team_metadata = json.loads(team_metadata_raw) if team_metadata_raw else {}
        except json.JSONDecodeError:
            return _bad_request("team_metadata must be valid JSON.")

        stego_ext = {"image": "png", "audio": "wav", "video": "mkv"}[cover_type]
        stego_out_name = f"stego_{cover_type}.{stego_ext}"

        result = pipeline.encode(
            cover_type=cover_type,
            cover_bytes=_cover_bytes(cover_file, cover_type),
            payload_type=payload_type,
            data=data,
            filename=filename,
            mime=mime,
            num_lsb=num_lsb,
            start_mode=start_mode,
            manual_offset=manual_offset,
            passphrase=passphrase,
            media_id=media_id,
            team_metadata=team_metadata,
            stego_out_name=stego_out_name,
            hash_algorithm=form.get("hash_algorithm", "SHA-256"),
            key_id=form.get("key_id"),
            encryption_public_pem=_encryption_key(form),
        )

        return jsonify(
            {
                "stego_base64": _b64(result.stego_bytes),
                "stego_filename": result.stego_filename,
                "mime": result.mime,
                "start_index": result.start_index,
                "num_lsb": result.num_lsb,
                "metadata": result.metadata,
                "payload_hash_hex": result.payload_hash_hex,
                "signature_hex": result.signature_hex,
                "container_size_bytes": result.container_size_bytes,
                "capacity_bytes": result.capacity_bytes,
                "cover_info": result.cover_info,
                "public_key_pem": crypto_utils.key_description(crypto_utils.signing_key(form.get("key_id")))["public_key_pem"],
                "required_units": result.required_units,
            }
        )
    except pipeline.StegoError as exc:
        return _bad_request(str(exc))
    except ValueError as exc:
        return _bad_request(str(exc))
    except Exception as exc:
        return _bad_request(f"Encoding failed: {exc}", 500)


# --------------------------------------------------------------------------
# Decode (sync + async)
# --------------------------------------------------------------------------
def _run_decode(cover_type, stego_bytes, num_lsb, start_mode, manual_offset, passphrase, public_key_pem, filename=None, decryption_private_pem=None):
    result = pipeline.decode(
        cover_type=cover_type,
        stego_bytes=stego_bytes,
        num_lsb=num_lsb,
        start_mode=start_mode,
        manual_offset=manual_offset,
        passphrase=passphrase,
        public_key_pem=public_key_pem,
        decryption_private_pem=decryption_private_pem,
    )
    if result.metadata is not None and result.evidence["checks"]["decryption"] == "Not applicable":
        result.verdict = "Cannot Verify"
        result.detail = "This is a signed-only file. Encryption is required; recreate it in Protect using Bob's public encryption key."
        result.data = None
        result.evidence["reason_code"] = "ENCRYPTION_REQUIRED"
        result.evidence["decryption_status"] = "Required but absent"
        result.evidence["checks"]["decryption"] = "Required but absent"
        result.evidence["next_step"] = "Recreate this file in Protect; encryption is required."
    payload_out = None
    data_filename = None
    data_mime = None
    if result.data is not None:
        payload_out = _b64(result.data)
        meta = result.metadata or {}
        data_filename = meta.get("filename") or None
        data_mime = meta.get("mime") or None
    result.evidence["filename"] = filename

    return {
        "verdict": result.verdict,
        "detail": result.detail,
        "payload_type": result.payload_type,
        "metadata": result.metadata,
        "data_base64": payload_out,
        "data_filename": data_filename,
        "data_mime": data_mime,
        "payload_hash_match": result.payload_hash_match,
        "signature_valid": result.signature_valid,
        "cover_hash_match": result.cover_hash_match,
        "start_index": result.start_index,
        "cover_info": result.cover_info,
        "evidence": result.evidence,
    }


@app.post("/api/decode")
def api_decode():
    try:
        form = request.form
        cover_type, num_lsb, start_mode, manual_offset, passphrase = _parse_common_fields(form)
        stego_file = request.files.get("stego_file")
        if stego_file is None:
            return _bad_request("stego_file is required.")
        stego_bytes = stego_file.read()

        public_key_pem_str = form.get("public_key_pem") or None
        public_key_pem = public_key_pem_str.encode("utf-8") if public_key_pem_str else b""

        mode = request.args.get("mode", "sync").strip().lower()
        if form.get("use_saved_bob", "on") == "on":
            private_pem = crypto_utils.private_pem(crypto_utils.recipient_key())
        else:
            upload = request.files.get("decryption_private_file")
            if upload is None:
                raise ValueError("Choose Bob's private encryption key file.")
            raw = upload.read(32769)
            if len(raw) > 32768:
                raise ValueError("Key file is too large.")
            password = form.get("decryption_password")
            key = serialization.load_pem_private_key(raw, password.encode() if password else None)
            private_pem = crypto_utils.private_pem(key)
        args = (cover_type, stego_bytes, num_lsb, start_mode, manual_offset, passphrase, public_key_pem, stego_file.filename, private_pem)

        if mode == "async":
            job_id = jobs.submit(_run_decode, *args)
            return jsonify({"job_id": job_id})

        if mode != "sync":
            return _bad_request("mode must be 'sync' or 'async'.")

        return jsonify(_run_decode(*args))
    except (ValueError, pipeline.StegoError) as exc:
        return _bad_request(str(exc))
    except Exception as exc:
        return _bad_request(f"Decoding failed: {exc}", 500)


@app.get("/api/jobs/<job_id>")
def api_job_status(job_id):
    job = jobs.get(job_id)
    if job is None:
        return _bad_request("Unknown or expired job id.", 404)
    if job.status == "pending":
        return jsonify({"status": "pending"})
    if job.status == "error":
        jobs.pop(job_id)
        return jsonify({"status": "error", "error": job.error})
    result = job.result
    jobs.pop(job_id)
    return jsonify({"status": "done", "result": result})


def _analyse_video(data: bytes) -> dict:
    wav_bytes, video_info = pipeline.video_audio_track(data)
    return audio_analysis.analyse_audio(wav_bytes, source_bytes=data, video_info=video_info)


@app.post("/api/analyse")
def api_analyse():
    """Independent statistics; never change the verification verdict. PNGs get
    chi-square and RS; WAVs and video audio tracks get sample-pair analysis."""
    try:
        upload = request.files.get("media_file") or request.files.get("image_file")
        if upload is None:
            upload = next(iter(request.files.values()), None)
        if upload is None:
            return _bad_request("Upload a file to analyse.")
        mode = request.args.get("mode", "sync")
        if mode not in ("sync", "async"):
            return _bad_request("mode must be 'sync' or 'async'.")
        head = upload.stream.read(12)
        upload.stream.seek(0)
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            data = upload.read(analysis.MAX_FILE_BYTES + 1)
            window = int(request.form.get("window_size", 65536))
            if not data or len(data) > analysis.MAX_FILE_BYTES:
                return _bad_request(f"Upload a nonempty PNG of at most {analysis.MAX_FILE_BYTES // (1024 * 1024)} MiB.")
            if not 256 <= window <= 1_000_000:
                return _bad_request("Window size must be 256-1000000 channel values.")
            task, args = analysis.analyse_png, (data, window)
        elif head[:4] == b"RIFF" and head[8:12] == b"WAVE":
            task, args = audio_analysis.analyse_audio, (upload.read(),)
        elif Path(upload.filename or "").suffix.lower() in CONTENT_MIME_TYPES["video"]:
            task, args = _analyse_video, (upload.read(),)
        else:
            return _bad_request("Upload a PNG image, a PCM WAV file, or a video with an audio track.")
        if mode == "async":
            return jsonify({"job_id": jobs.submit(task, *args)})
        return jsonify(task(*args))
    except (ValueError, pipeline.StegoError) as exc:
        return _bad_request(str(exc))


# --------------------------------------------------------------------------
# Safety net: never let an unhandled exception show a raw traceback / crash
# --------------------------------------------------------------------------
@app.errorhandler(Exception)
def handle_uncaught(exc):
    # HTTPException (404 for an unknown route/favicon, 405 for a wrong verb,
    # 413 for a too-large upload, ...) already carries the right status code
    # and a sensible message - only genuinely unexpected exceptions should be
    # flattened into a generic 500.
    if isinstance(exc, HTTPException):
        return jsonify({"error": exc.description}), exc.code
    return jsonify({"error": f"Unexpected server error: {exc}"}), 500


if __name__ == "__main__":
    crypto_utils.generate_keypair(overwrite=False)  # ensure a keypair exists on first run
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
