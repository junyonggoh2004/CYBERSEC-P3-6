"""Independent arithmetic oracles, edge cases, API and crypto review tests."""
import io
import math
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from stego import analysis, crypto_utils, pipeline
from app import app


def png(array):
    output = io.BytesIO()
    Image.fromarray(array).save(output, format="PNG")
    return output.getvalue()


def test_chi_square_hand_vector():
    # Counts [12,8], [6,14], [10,10]: 4/10 + 16/10 + 0 = 2; df=2.
    values = np.repeat(np.arange(6, dtype=np.uint8), [12, 8, 6, 14, 10, 10])
    result = analysis.chi_square(values)
    assert result["statistic"] == pytest.approx(2)
    assert result["degrees_of_freedom"] == 2
    assert result["score"] == pytest.approx(math.exp(-1))
    assert result["even_counts"][:3] == [12, 6, 10]
    assert result["odd_counts"][:3] == [8, 14, 10]


@pytest.mark.parametrize("values", [[], [0], [0] * 100, [0, 1, 2, 3]])
def test_chi_insufficient(values):
    result = analysis.chi_square(np.array(values, dtype=np.uint8))
    assert result["score"] is None


def test_chi_equal_and_unequal_pairs():
    balanced = np.repeat(np.arange(256, dtype=np.uint8), 10)
    assert analysis.chi_square(balanced)["score"] == 1
    unbalanced = np.repeat(np.arange(0, 256, 2, dtype=np.uint8), 20)
    assert analysis.chi_square(unbalanced)["score"] < 1e-100


def scalar_counts(groups, mask):
    counts = dict(regular=0, singular=0, unusable=0)
    for row in groups.tolist():
        transformed = []
        for value, operation in zip(row, mask):
            if operation == 1:
                value += 1 if value % 2 == 0 else -1
            elif operation == -1:
                value += -1 if value % 2 == 0 else 1
            transformed.append(value)
        before = sum(abs(a - b) for a, b in zip(row, row[1:]))
        after = sum(abs(a - b) for a, b in zip(transformed, transformed[1:]))
        counts["regular" if after > before else "singular" if after < before else "unusable"] += 1
    return counts


def test_rs_hand_vectors_and_boundaries():
    # Positive f: 0->2 (R), 2->0 (S), 3->3 (U).
    groups = np.array([[0, 0, 0, 0], [0, 1, 1, 0], [0, 1, 2, 3]], dtype=np.uint8)
    assert analysis.rs_counts(groups) == dict(regular=1, singular=1, unusable=1)
    # Inverse f: 0->2, 2->4, 3->5, so all three are regular.
    assert analysis.rs_counts(groups, (0, -1, -1, 0)) == dict(regular=3, singular=0, unusable=0)
    edges = np.array([[0, 0, 255, 255], [255, 255, 255, 255]], dtype=np.uint8)
    assert analysis.rs_counts(edges, (0, -1, -1, 0)) == scalar_counts(edges, (0, -1, -1, 0))


@pytest.mark.parametrize("mask", [(0, 1, 1, 0), (0, -1, -1, 0), (1, -1, 0, 1)])
def test_rs_independent_random_oracle(mask):
    groups = np.random.default_rng(120).integers(0, 256, (2000, 4), dtype=np.uint8)
    original = groups.copy()
    assert analysis.rs_counts(groups, mask) == scalar_counts(groups, mask)
    np.testing.assert_array_equal(groups, original)


def test_rs_row_boundaries_and_tiny():
    image = np.arange(35, dtype=np.uint8).reshape(5, 7)
    result = analysis.rs_analysis(image)
    assert result["groups"] == 5
    assert result["discarded_values"] == 15
    assert result["score"] is None
    assert analysis.rs_analysis(np.zeros((4, 3), dtype=np.uint8))["groups"] == 0


def test_alpha_exclusion_and_windows():
    rgb = np.random.default_rng(19).integers(0, 256, (64, 67, 3), dtype=np.uint8)
    rgba = np.concatenate([rgb, np.zeros((64, 67, 1), dtype=np.uint8)], axis=2)
    first = analysis.analyse_png(png(rgb), 256)
    second = analysis.analyse_png(png(rgba), 256)
    assert first["channels"] == second["channels"]
    for channel in first["channels"].values():
        assert sum(w["sample_count"] for w in channel["windows"]) == 64 * 67
        assert channel["windows"][-1]["stop"] == 64 * 67


def test_grayscale_and_constant():
    result = analysis.analyse_png(png(np.zeros((100, 100), dtype=np.uint8)))
    assert list(result["channels"]) == ["L"]
    assert result["combined"]["category"] == "Inconclusive"


@pytest.mark.parametrize("chi,rs,expected", [(1, .1, "High indication"), (0, 0, "Low indication"), (1, 0, "Inconclusive"), (None, .1, "Inconclusive")])
def test_combination(chi, rs, expected):
    assert analysis.combine(chi, rs)["category"] == expected


def test_rejects_invalid_inputs(monkeypatch):
    for data in (b"", b"not a png"):
        with pytest.raises(ValueError):
            analysis.analyse_png(data)
    data = png(np.zeros((10, 10, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        analysis.analyse_png(data, 0)
    with pytest.raises(ValueError):
        analysis.chi_square(np.array([-1]))
    with pytest.raises(ValueError):
        analysis.combine(1, 1, {"chi_square": float("nan"), "rs": .1})
    monkeypatch.setattr(analysis, "MAX_PIXELS", 99)
    with pytest.raises(ValueError, match="million"):
        analysis.analyse_png(data)


def test_api_sync_async_and_errors():
    client = app.test_client()
    data = png(np.random.default_rng(1).integers(0, 256, (64, 64, 3), dtype=np.uint8))
    assert client.post("/api/analyse").status_code == 400
    assert client.post("/api/analyse", data={"image_file": (io.BytesIO(b"bad"), "bad.png")}).status_code == 400
    result = client.post("/api/analyse", data={"image_file": (io.BytesIO(data), "sample.png")})
    assert result.status_code == 200
    assert "verdict" not in result.json
    job = client.post("/api/analyse?mode=async", data={"image_file": (io.BytesIO(data), "sample.png")}).json["job_id"]
    for _ in range(200):
        response = client.get(f"/api/jobs/{job}")
        if response.json["status"] != "pending":
            break
        time.sleep(.01)
    assert response.json["status"] == "done"
    assert response.json["result"]["scores"] == result.json["scores"]
    assert client.get(f"/api/jobs/{job}").status_code == 404


def test_crypto_signature_review():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signature = crypto_utils.sign(b"Kim review", key)
    assert crypto_utils.verify(b"Kim review", signature, key.public_key())
    assert not crypto_utils.verify(b"changed", signature, key.public_key())
    assert not crypto_utils.verify(b"Kim review", signature, other.public_key())
    altered = bytes([signature[0] ^ 1]) + signature[1:]
    assert not crypto_utils.verify(b"Kim review", altered, key.public_key())


@pytest.mark.parametrize("bits", range(1, 9))
def test_pipeline_roundtrip_and_analysis_no_mutation(bits, monkeypatch):
    # Keys only in memory: do not create or rotate the user's PEM files.
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(crypto_utils, "load_private_key", lambda: key)
    monkeypatch.setattr(crypto_utils, "load_public_key", lambda *_: key.public_key())
    cover = png(np.random.default_rng(7).integers(0, 256, (100, 100, 3), dtype=np.uint8))
    encoded = pipeline.encode(cover_type="image", cover_bytes=cover,
        payload_type="text", data=b"Kim integration", filename=None, mime="text/plain",
        num_lsb=bits, start_mode="manual", manual_offset=24, passphrase=None,
        media_id="kim-test", team_metadata={}, stego_out_name="test.png")
    analysis.analyse_png(encoded.stego_bytes)
    result = pipeline.decode(cover_type="image", stego_bytes=encoded.stego_bytes,
        num_lsb=bits, start_mode="manual", manual_offset=24, passphrase=None, public_key_pem=None)
    assert result.verdict == "Authentic"
    assert result.data == b"Kim integration"
