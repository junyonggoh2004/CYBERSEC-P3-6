"""Tests for audio comparison metrics (AUD-003).

Values are checked against hand-calculable cases so a reviewer can verify the
maths independently, not just trust the code.
"""

import numpy as np
import pytest

import backend.stego.audio_metrics as m


def test_identical_signals_have_no_distortion():
    x = np.array([100, -200, 300, -400], dtype=np.int16)
    result = m.compare(x, x.copy())
    assert result.changed_samples == 0
    assert result.mse == 0.0
    assert result.snr_db == float("inf")


def test_changed_sample_count():
    cover = np.array([0, 0, 0, 0], dtype=np.int16)
    stego = np.array([1, 0, 1, 0], dtype=np.int16)  # two samples changed
    assert m.changed_sample_count(cover, stego) == 2


def test_mse_known_value():
    # diffs = [1, 2], squared = [1, 4], mean = 2.5
    cover = np.array([10, 20], dtype=np.int16)
    stego = np.array([11, 22], dtype=np.int16)
    assert m.mean_squared_error(cover, stego) == pytest.approx(2.5)


def test_mse_does_not_overflow_int16():
    # Difference of 65535 would overflow int16 if not promoted to float first.
    cover = np.array([32767], dtype=np.int16)
    stego = np.array([-32768], dtype=np.int16)
    expected = (32767.0 - (-32768.0)) ** 2
    assert m.mean_squared_error(cover, stego) == pytest.approx(expected)


def test_snr_known_value():
    # signal power = mean([100^2, 100^2]) = 10000
    # noise power  = mean([1^2, 1^2]) = 1
    # SNR = 10*log10(10000/1) = 40 dB
    cover = np.array([100, -100], dtype=np.int16)
    stego = np.array([101, -99], dtype=np.int16)
    assert m.snr_db(cover, stego) == pytest.approx(40.0, abs=1e-6)
    # a cover with real signal power is measured against itself, so this is a
    # true SNR and is shown without a qualifier
    result = m.compare(cover, stego)
    assert result.snr_reference == m.SNR_REFERENCE_SIGNAL
    assert result.snr_display == "40.0 dB"


def test_snr_infinite_when_identical():
    x = np.array([1, 2, 3], dtype=np.int16)
    assert m.snr_db(x, x.copy()) == float("inf")


def test_snr_silent_original_stays_finite():
    cover = np.zeros(4, dtype=np.int16)
    stego = np.array([1, 0, 0, 0], dtype=np.int16)
    # Should not raise or return inf; uses full-scale reference.
    value = m.snr_db(cover, stego)
    assert np.isfinite(value)


# --- the SNR reference must be reported, not silently substituted -----------


def test_silent_cover_is_labelled_as_not_a_true_snr():
    cover = np.zeros(4, dtype=np.int16)
    stego = np.array([1, 0, 0, 0], dtype=np.int16)
    value, reference = m.snr_db_with_reference(cover, stego)
    assert reference == m.SNR_REFERENCE_FULL_SCALE
    assert np.isfinite(value)

    display = m.compare(cover, stego).snr_display
    assert "full scale" in display
    assert "not a true SNR" in display


def test_silent_cover_reference_follows_the_sample_dtype():
    # The stand-in reference is full scale for the carrier's own dtype, so a
    # 32-bit cover is not measured against a 16-bit reference. Same noise, wider
    # dtype, so the int32 figure must be the larger of the two.
    noise = [1, 0, 0, 0]
    snr16 = m.snr_db(np.zeros(4, dtype=np.int16), np.array(noise, dtype=np.int16))
    snr32 = m.snr_db(np.zeros(4, dtype=np.int32), np.array(noise, dtype=np.int32))

    # int16 result is unchanged: full scale 32768, noise power 0.25.
    assert snr16 == pytest.approx(10.0 * np.log10(32768.0 ** 2 / 0.25), abs=1e-9)
    assert snr32 == pytest.approx(10.0 * np.log10(2147483648.0 ** 2 / 0.25), abs=1e-9)
    assert snr32 > snr16


def test_identical_signals_are_labelled_rather_than_printed_as_a_number():
    x = np.array([1, 2, 3], dtype=np.int16)
    result = m.compare(x, x.copy())
    assert result.snr_reference == m.SNR_REFERENCE_NONE
    assert result.snr_db == float("inf")
    assert "identical" in result.snr_display


def test_higher_bit_depth_lowers_snr():
    # More bits changed -> more noise -> lower SNR. Verified with the real carrier.
    import wav
    rng = np.random.default_rng(2)
    samples = rng.integers(-3000, 3000, size=2000, dtype=np.int16)
    carrier = wav.WavCarrier(
        info=wav.WavInfo(channels=1, sample_rate=44100, sample_width_bytes=2, frame_count=2000),
        samples=samples,
    )
    payload = b"x" * 100
    snr_1bit = m.snr_db(carrier.samples, wav.embed(carrier, payload, 1).samples)
    snr_8bit = m.snr_db(carrier.samples, wav.embed(carrier, payload, 8).samples)
    assert snr_1bit > snr_8bit


def test_mismatched_shapes_rejected():
    with pytest.raises(m.MetricsError):
        m.compare(np.array([1, 2], dtype=np.int16), np.array([1], dtype=np.int16))


def test_empty_rejected():
    with pytest.raises(m.MetricsError):
        m.compare(np.array([], dtype=np.int16), np.array([], dtype=np.int16))


def test_changed_fraction():
    cover = np.zeros(10, dtype=np.int16)
    stego = cover.copy()
    stego[:3] = 1
    result = m.compare(cover, stego)
    assert result.changed_fraction == pytest.approx(0.3)