import io
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import app  # noqa: E402
from stego import audio_analysis, pipeline  # noqa: E402

RATE = 44100


def wav(samples, width=2, channels=1):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(RATE)
        w.writeframes(np.asarray(samples).astype(np.int16 if width == 2 else np.int32).tobytes())
    return out.getvalue()


def speech_like(seconds=6, seed=3):
    """Filtered noise with pauses: many neighbouring samples close in value."""
    rng = np.random.default_rng(seed)
    n = RATE * seconds
    t = np.arange(n) / RATE
    x = np.convolve(rng.normal(size=n), np.hanning(60), "same") * np.abs(np.sin(2 * np.pi * 3 * t)) ** 2
    return np.round(x / np.abs(x).max() * 16000)


def encode(cover, share, num_lsb=1):
    capacity = pipeline.capacity_check("audio", cover, num_lsb, "manual", 100).capacity_bytes
    data = np.random.default_rng(5).integers(0, 256, int(capacity * share) - 900, dtype=np.uint8).tobytes()
    return pipeline.encode(cover_type="audio", cover_bytes=cover, payload_type="file", data=data,
                           filename="x.bin", mime="application/octet-stream", num_lsb=num_lsb,
                           start_mode="manual", manual_offset=100, passphrase=None, media_id="T",
                           team_metadata={}, stego_out_name="s.wav").stego_bytes


def test_pair_counts_hand_vector():
    # Pairs (2,3) (3,2) (2,5) (5,4): traces floor(v/2)-floor(u/2) = 0, 0, 1, 0.
    counts = audio_analysis.pair_counts(np.array([2, 3, 2, 5, 4]))
    first, second = counts  # pairs at even positions: (2,3), (2,5); odd: (3,2), (5,4)
    zero = audio_analysis.MAX_TRACE + 1
    assert first[0][zero] == 1 and first[1][zero] == 1      # (2,3): even->odd, trace 0
    assert first[0][zero + 1] == 1 and first[1][zero + 1] == 1  # (2,5): even->odd, trace 1
    assert second[0][zero] == 2 and second[2][zero] == 2     # (3,2), (5,4): odd->even, trace 0
    assert counts.sum() == 4 * 2  # every pair counted in T and in exactly one of B / C


def test_clean_audio_is_not_flagged():
    report = audio_analysis.analyse_audio(wav(speech_like()))
    assert abs(report["spa"]["estimate"]) < 0.05
    assert report["combined"]["category"] == "Low indication"


@pytest.mark.parametrize("share", [0.25, 0.5, 1.0])
def test_estimates_share_of_encoder_payload(share):
    report = audio_analysis.analyse_audio(encode(wav(speech_like()), share))
    assert report["spa"]["estimate"] == pytest.approx(share, abs=0.08)
    assert report["combined"]["category"] == "High indication"
    assert report["estimated_hidden_bytes_at_1_lsb"] > 0


def test_time_map_locates_contiguous_payload():
    segments = audio_analysis.analyse_audio(encode(wav(speech_like()), 0.5))["segments"]
    first, second = segments[:len(segments) // 2], segments[len(segments) // 2:]
    assert min(s["estimate"] for s in first) > 0.5
    assert max(s["estimate"] for s in second) < 0.2


def test_loud_noise_is_inconclusive_not_a_false_alarm():
    loud = np.round(np.random.default_rng(1).normal(size=RATE * 3) * 8000)
    report = audio_analysis.analyse_audio(wav(np.clip(loud, -32768, 32767)))
    assert report["combined"]["category"] == "Inconclusive"


def test_stereo_and_32_bit_are_supported():
    x = speech_like(3)
    stereo = audio_analysis.analyse_audio(wav(np.column_stack([x, x[::-1]]).ravel(), channels=2))
    assert [c["channel"] for c in stereo["channels"]] == [1, 2]
    wide = audio_analysis.analyse_audio(wav(x * 65536, width=4))
    assert wide["media"]["sample_width_bits"] == 32 and wide["combined"]["category"] in ("Inconclusive", "Low indication")


def test_threshold_validation():
    result = {"estimate": 0.5, "standard_error": 0.01, "ci95": [0.48, 0.52]}
    assert audio_analysis.combine(result)["category"] == "High indication"
    with pytest.raises(ValueError):
        audio_analysis.combine(result, {"min_rate": 2, "max_standard_error": 0.1})


def test_api_routes_by_file_type():
    client = app.test_client()
    png = (ROOT / "samples" / "cover_image.png").read_bytes()
    image = client.post("/api/analyse", data={"media_file": (io.BytesIO(png), "a.png")}).json
    assert "chi_square" in image["scores"]
    legacy = client.post("/api/analyse", data={"image_file": (io.BytesIO(png), "a.png")})
    assert legacy.status_code == 200
    audio = client.post("/api/analyse", data={"media_file": (io.BytesIO(wav(speech_like(2))), "a.wav")}).json
    assert audio["method"] == "sample_pair_analysis" and audio["media"]["kind"] == "audio"
    junk = client.post("/api/analyse", data={"media_file": (io.BytesIO(b"hello"), "x.bin")})
    assert junk.status_code == 400


def test_api_analyses_video_audio_track():
    video = (ROOT / "samples" / "cover_video.mp4").read_bytes()
    report = app.test_client().post("/api/analyse", data={"media_file": (io.BytesIO(video), "clip.mp4")}).json
    assert report["media"]["kind"] == "video" and report["media"]["video"]["has_audio"]
    assert report["combined"]["category"] == "Low indication"


def test_likelihood_follows_the_evidence():
    from stego import spa
    clean = spa.hidden_data_likelihood(0.0, 0.005, "image")
    heavy = spa.hidden_data_likelihood(0.3, 0.005, "image")
    no_evidence = spa.hidden_data_likelihood(0.4, 3.0, "audio")
    assert clean["probability"] < 0.05 and clean["band"] == "Unlikely"
    assert heavy["probability"] > 0.999 and heavy["band"] == "Likely"
    assert no_evidence["probability"] == pytest.approx(0.5, abs=0.05) and no_evidence["band"] == "Uncertain"
    rising = [spa.hidden_data_likelihood(e, 0.01, "image")["probability"] for e in (0.0, 0.02, 0.04, 0.08)]
    assert rising == sorted(rising)
    assert spa.hidden_data_likelihood(None, None, "audio")["probability"] is None


def test_reports_include_likelihood():
    clean = audio_analysis.analyse_audio(wav(speech_like()))["likelihood"]
    stego = audio_analysis.analyse_audio(encode(wav(speech_like()), 0.5))["likelihood"]
    assert clean["probability"] < 0.2 and stego["probability"] > 0.99
    from stego import analysis
    png = (ROOT / "samples" / "cover_image.png").read_bytes()
    report = analysis.analyse_png(png)
    assert report["likelihood"]["probability"] < 0.2
    assert report["spa"]["status"] == "ok" and "spa" in report["channels"]["R"]
