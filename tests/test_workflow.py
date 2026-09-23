"""Round trips, exact fit, legacy records, verdict evidence and non-destructive keys."""
import base64
import io
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from cryptography.hazmat.primitives import serialization

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import app
from stego import comparison, crypto_utils, image_lsb, payload, pipeline
from stego.bitstream import StegoStream


def png(array):
    out = io.BytesIO()
    Image.fromarray(array).save(out, format="PNG")
    return out.getvalue()


def wav(samples=32000, width=2):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(16000)
        w.writeframes((np.sin(np.arange(samples) / 31) * 2000).astype("<i2" if width == 2 else "<i4").tobytes())
    return out.getvalue()


@pytest.fixture
def keys(tmp_path, monkeypatch):
    monkeypatch.setattr(crypto_utils, "KEY_DIR", tmp_path)
    monkeypatch.setattr(crypto_utils, "PRIVATE_KEY_PATH", tmp_path / "private_key.pem")
    monkeypatch.setattr(crypto_utils, "PUBLIC_KEY_PATH", tmp_path / "public_key.pem")
    crypto_utils.generate_keypair()
    return crypto_utils.public_key_pem()


@pytest.fixture(scope="module")
def covers():
    return {"image": png(np.random.default_rng(4).integers(0, 256, (128, 128, 3), dtype=np.uint8)),
            "audio": wav()}


def encode_args(kind, cover, **changes):
    args = dict(cover_type=kind, cover_bytes=cover, payload_type="text", data=b"Hello Bob",
        filename=None, mime="text/plain", num_lsb=1, start_mode="manual", manual_offset=100,
        passphrase=None, media_id="TEST-001", team_metadata={"team": "P3-6"},
        stego_out_name="test.png" if kind == "image" else "test.wav")
    args.update(changes)
    return args


def decode_args(args, stego, public):
    return {k: args[k] for k in ("cover_type", "num_lsb", "start_mode", "manual_offset", "passphrase")} | {
        "stego_bytes": stego, "public_key_pem": public}


@pytest.mark.parametrize("kind", ["image", "audio"])
@pytest.mark.parametrize("algorithm", ["SHA-256", "SHA-512"])
@pytest.mark.parametrize("depth", range(1, 9))
def test_all_depths_and_hashes(kind, algorithm, depth, covers, keys):
    args = encode_args(kind, covers[kind], num_lsb=depth, hash_algorithm=algorithm)
    enc = pipeline.encode(**args)
    dec = pipeline.decode(**decode_args(args, enc.stego_bytes, keys))
    assert dec.verdict == "Authentic", dec.detail
    assert dec.data == args["data"]
    assert dec.evidence["hash_algorithm"] == algorithm
    assert len(dec.evidence["expected_payload_hash"]) == (64 if algorithm == "SHA-256" else 128)


@pytest.mark.parametrize("kind,content_type", [("image", "audio"), ("audio", "image")])
def test_binary_cross_media(kind, content_type, covers, keys):
    data = wav(40) if content_type == "audio" else png(np.zeros((8, 8, 3), dtype=np.uint8))
    args = encode_args(kind, covers[kind], payload_type=content_type, data=data,
                       filename="content.wav" if content_type == "audio" else "content.png")
    enc = pipeline.encode(**args)
    dec = pipeline.decode(**decode_args(args, enc.stego_bytes, keys))
    assert dec.verdict == "Authentic"
    assert dec.data == data and dec.payload_type == content_type


def test_exact_fit_includes_field_padding(keys):
    built = payload.build_container(b"abc", "text", "ID", None, "text/plain", {}, b"x" * 32,
                                    settings={"num_lsb": 3})
    units = built.required_units(3)
    arr = np.zeros(units, dtype=np.uint8)
    payload.write_container(StegoStream(arr, 0, 3), built)
    with pytest.raises(ValueError, match="does not fit"):
        payload.write_container(StegoStream(np.zeros(units-1, dtype=np.uint8), 0, 3), built)
    assert units * 3 >= len(built.raw) * 8


@pytest.mark.parametrize("algorithm", ["SHA-256", "SHA-512"])
def test_preflight_matches_output(algorithm, covers, keys):
    args = encode_args("image", covers["image"], num_lsb=3, hash_algorithm=algorithm)
    review = pipeline.prepare(**{k:v for k,v in args.items() if k != "stego_out_name"})
    enc = pipeline.encode(**args)
    assert review["required_units"] == enc.required_units
    assert review["container_size_bytes"] == enc.container_size_bytes
    assert review["fits"] and len(review["choices"]) == 8


def test_sha512_passphrase_location_does_not_depend_on_unknown_hash(covers, keys):
    args = encode_args("image", covers["image"], num_lsb=4, hash_algorithm="SHA-512",
                       start_mode="passphrase", passphrase="alice-bob-demo")
    enc = pipeline.encode(**args)
    assert pipeline.decode(**decode_args(args, enc.stego_bytes, keys)).verdict == "Authentic"
    bad = decode_args(args, enc.stego_bytes, keys) | {"passphrase": "different"}
    dec = pipeline.decode(**bad)
    assert dec.verdict == "Payload Missing"
    assert "may be wrong" in dec.detail


def test_version_one_still_readable(covers, keys):
    carrier = image_lsb.load_image_carrier(covers["image"])
    depth = 3
    meta = json.dumps({"cover_hash": crypto_utils.stable_cover_hash(carrier.array, depth).hex(),
                       "mime": "text/plain"}).encode()
    data = b"legacy file"
    h = crypto_utils.sha256(data)
    sig = crypto_utils.sign(h + crypto_utils.sha256(meta))
    parts = [b"STG1", b"\x01", b"\x00", len(meta).to_bytes(2,"big"), meta, h,
             len(sig).to_bytes(2,"big"), sig, len(data).to_bytes(4,"big"), data]
    stream = StegoStream(carrier.array, 100, depth)
    for part in parts:
        stream.write(part)
    args = encode_args("image", covers["image"], num_lsb=depth)
    dec = pipeline.decode(**decode_args(args, image_lsb.carrier_to_png_bytes(carrier), keys))
    assert dec.verdict == "Authentic" and dec.data == data
    assert dec.evidence["container_version"] == 1


def test_api_negative_cases_have_same_evidence_schema(covers, keys):
    client = app.test_client()
    form = {"cover_type":"image", "num_lsb":"3", "start_mode":"manual", "manual_offset":"100",
            "payload_type":"text", "payload_text":"Signed content", "hash_algorithm":"SHA-512"}
    response = client.post("/api/encode", data=form | {"cover_file": (io.BytesIO(covers["image"]),"cover.png")})
    assert response.status_code == 200, response.json
    stego = base64.b64decode(response.json["stego_base64"])
    def verify(data, **extra):
        return client.post("/api/decode", data=form | {"public_key_pem":keys.decode(),
            "stego_file":(io.BytesIO(data),"received.png")} | extra).json
    good = verify(stego)
    assert good["verdict"] == "Authentic"
    wrong = verify(stego, public_key_pem=crypto_utils.generate_decoy_public_key_pem().decode())
    missing = verify(stego, manual_offset="1000")
    no_key = verify(stego, public_key_pem="")
    assert wrong["verdict"] == "Signature Invalid"
    assert missing["verdict"] == "Payload Missing"
    assert no_key["verdict"] == "Cannot Verify"
    assert no_key["evidence"]["checks"]["extraction"] == "Not run"
    for mode, reason in [("payload","PAYLOAD_HASH_MISMATCH"),("cover","COVER_HASH_MISMATCH")]:
        tamper = client.post("/api/demo/tamper", data=form | {"tamper_mode":mode,
            "stego_file":(io.BytesIO(stego),"stego.png")})
        assert tamper.status_code == 200, tamper.json
        result = verify(base64.b64decode(tamper.json["stego_base64"]))
        assert result["verdict"] == "Tampered" and result["evidence"]["reason_code"] == reason
        assert set(result["evidence"]) == set(good["evidence"])
    for result in [wrong, missing, no_key]:
        assert set(result["evidence"]) == set(good["evidence"])
        assert set(result["evidence"]["checks"]) == set(good["evidence"]["checks"])


def test_key_generation_and_import_preserve_original(keys):
    old_private = crypto_utils.PRIVATE_KEY_PATH.read_bytes()
    old_public = crypto_utils.PUBLIC_KEY_PATH.read_bytes()
    client = app.test_client()
    first = client.get("/api/keys").json["keys"]
    fresh = client.post("/api/keys/generate").json
    assert fresh["key_id"] != first[0]["fingerprint"]
    assert crypto_utils.PRIVATE_KEY_PATH.read_bytes() == old_private
    assert crypto_utils.PUBLIC_KEY_PATH.read_bytes() == old_public
    imported = client.post("/api/keys/import", data={"key_file":(io.BytesIO(old_private),"demo.pem")})
    assert imported.status_code == 200
    assert len(client.get("/api/keys").json["keys"]) == 3
    assert "private" not in fresh and "private_key_pem" not in fresh
    assert client.get("/api/keys/public?key_id=../../escape").status_code != 200


def test_comparison_measurements(covers, keys):
    args = encode_args("image", covers["image"])
    enc = pipeline.encode(**args)
    result = comparison.compare("image", covers["image"], enc.stego_bytes)
    assert 0 < result["changed_percent"] < 100
    assert result["max_absolute_difference"] == 1
    assert set(result["histograms"]) == {"R","G","B"}
    assert sum(result["histograms"]["R"]["before"]) == 128 * 128
    same = comparison.compare("audio", covers["audio"], covers["audio"])
    assert same["mse"] == 0 and same["psnr_db"] is None
    assert same["waveforms"]["before"] == same["waveforms"]["after"]


def test_api_rejects_unagreed_combination(covers, keys):
    result = app.test_client().post("/api/encode", data={"cover_type":"image", "num_lsb":"1",
        "cover_file":(io.BytesIO(covers["image"]),"image.png"), "payload_type":"image",
        "payload_file":(io.BytesIO(covers["image"]),"payload.png")})
    assert result.status_code == 400


def test_audio_32_bit(covers, keys):
    args = encode_args("audio", wav(width=4), num_lsb=8, hash_algorithm="SHA-512")
    enc = pipeline.encode(**args)
    assert pipeline.decode(**decode_args(args, enc.stego_bytes, keys)).verdict == "Authentic"


def test_async_verdict_keeps_filename_and_schema(covers, keys):
    client = app.test_client()
    data = {"cover_type":"image", "num_lsb":"1", "start_mode":"manual",
            "manual_offset":"100", "public_key_pem":keys.decode()}
    sync = client.post("/api/decode", data=data | {"stego_file":(io.BytesIO(covers["image"]),"plain.png")}).json
    response = client.post("/api/decode?mode=async", data=data | {"stego_file":(io.BytesIO(covers["image"]),"plain.png")})
    job = response.json["job_id"]
    for _ in range(200):
        response = client.get("/api/jobs/" + job).json
        if response["status"] != "pending":
            break
        time.sleep(.01)
    assert response["status"] == "done"
    result = response["result"]
    assert result["evidence"]["filename"] == "plain.png"
    assert set(result["evidence"]) == set(sync["evidence"])


def test_preflight_rejects_nonobject_metadata(covers, keys):
    with pytest.raises(ValueError, match="JSON object"):
        pipeline.prepare("image", covers["image"], b"x", team_metadata=[])
