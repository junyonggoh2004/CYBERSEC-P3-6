"""WAV carrier tests (AUD-001 validation, AUD-002 embed/extract).

Embedding goes through the shared bitstream module, so these tests also pin
the shared bit convention (MSB-first, zero-padded tail). The cross-compat
tests prove wav.py and bitstream/StegoStream can read each other's output,
which is what makes this carrier safe to wire into payload.py and pipeline.py.

Fixtures are generated in-memory, so no external sample files. Round trips go
through a real save/reopen to prove the on-disk file survives, not just the
array.
"""

import struct
import wave

import numpy as np
import pytest

import bitstream
import wav

HIGH_BYTE_MASK = 0xFF00


# --- fixtures ---------------------------------------------------------------


def _write_wav(path, samples_int16, channels, sample_rate=44100):
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(np.asarray(samples_int16, dtype="<i2").tobytes())


@pytest.fixture
def mono_path(tmp_path):
    path = str(tmp_path / "mono.wav")
    rng = np.random.default_rng(0)
    samples = rng.integers(-3000, 3000, size=2000, dtype=np.int16)
    _write_wav(path, samples, channels=1)
    return path


@pytest.fixture
def stereo_path(tmp_path):
    path = str(tmp_path / "stereo.wav")
    rng = np.random.default_rng(1)
    samples = rng.integers(-3000, 3000, size=4000, dtype=np.int16)  # 2000 frames * 2ch
    _write_wav(path, samples, channels=2)
    return path


# --- AUD-001: validation and enumeration ------------------------------------


def test_load_mono(mono_path):
    carrier = wav.load(mono_path)
    assert carrier.info.channels == 1
    assert carrier.info.sample_width_bytes == 2
    assert carrier.info.frame_count == 2000
    assert carrier.eligible_units == 2000


def test_load_stereo_counts_both_channels(stereo_path):
    carrier = wav.load(stereo_path)
    assert carrier.info.channels == 2
    assert carrier.info.frame_count == 2000
    assert carrier.eligible_units == 4000  # all samples, both channels


def test_signed_little_endian_interpretation(tmp_path):
    # -1 and 256 have distinctive little-endian byte patterns; check they decode.
    path = str(tmp_path / "known.wav")
    _write_wav(path, [-1, 256, 0, 32767, -32768], channels=1)
    carrier = wav.load(path)
    assert list(carrier.samples) == [-1, 256, 0, 32767, -32768]


def test_reject_8bit(tmp_path):
    path = str(tmp_path / "eightbit.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)  # 8-bit
        w.setframerate(44100)
        w.writeframes(bytes([1, 2, 3, 4]))
    with pytest.raises(wav.UnsupportedWavError):
        wav.load(path)


def test_reject_non_wav(tmp_path):
    path = str(tmp_path / "junk.wav")
    with open(path, "wb") as f:
        f.write(b"this is not a wav file")
    with pytest.raises(wav.UnsupportedWavError):
        wav.load(path)


def test_reject_24bit(tmp_path):
    path = str(tmp_path / "24bit.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(3)  # 24-bit
        w.setframerate(44100)
        w.writeframes(bytes(300))
    with pytest.raises(wav.UnsupportedWavError):
        wav.load(path)


def test_reject_empty_wav(tmp_path):
    path = str(tmp_path / "empty.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"")  # zero frames
    with pytest.raises(wav.UnsupportedWavError):
        wav.load(path)


def test_reject_truncated_pcm(tmp_path):
    # Header claims more frames than the data actually holds.
    path = str(tmp_path / "truncated.wav")
    block_align = 1 * 2
    fmt = struct.pack("<HHIIHH", 1, 1, 44100, 44100 * block_align, block_align, 16)
    declared_frames = 100
    actual_data = b"\x00\x00" * 10  # only 10 frames present
    body = (
        b"WAVE"
        + b"fmt " + len(fmt).to_bytes(4, "little") + fmt
        + b"data" + (declared_frames * 2).to_bytes(4, "little") + actual_data
    )
    with open(path, "wb") as f:
        f.write(b"RIFF" + len(body).to_bytes(4, "little") + body)
    with pytest.raises(wav.UnsupportedWavError):
        wav.load(path)


# --- AUD-002 / MED-FR: save preserves header --------------------------------


@pytest.mark.parametrize("channels,rate", [(1, 44100), (2, 48000), (1, 22050)])
def test_save_preserves_format(tmp_path, channels, rate):
    src = str(tmp_path / "src.wav")
    dst = str(tmp_path / "dst.wav")
    samples = np.arange(-500, 500, dtype=np.int16)
    _write_wav(src, samples, channels=channels, sample_rate=rate)

    carrier = wav.load(src)
    wav.save(carrier, dst)
    reopened = wav.load(dst)

    assert reopened.info == carrier.info
    assert np.array_equal(reopened.samples, carrier.samples)


def test_save_of_in_memory_carrier_is_readable(tmp_path):
    # In-memory carrier -> stdlib writer must still produce a valid WAV.
    dst = str(tmp_path / "synth.wav")
    samples = np.arange(-500, 500, dtype=np.int16)
    carrier = wav.WavCarrier(
        info=wav.WavInfo(channels=2, sample_rate=48000, sample_width_bytes=2,
                         frame_count=samples.size // 2),
        samples=samples,
    )
    wav.save(carrier, dst)

    with wave.open(dst, "rb") as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (2, 48000, 2)
        assert w.getnframes() == 500
    assert np.array_equal(wav.load(dst).samples, samples)


def test_save_rejects_partial_frame(tmp_path):
    # 9 samples over 2 channels is not a whole number of frames; writing it would
    # silently drop the last sample (and any payload bits in it).
    carrier = wav.WavCarrier(
        info=wav.WavInfo(channels=2, sample_rate=8000, sample_width_bytes=2, frame_count=5),
        samples=np.arange(9, dtype=np.int16),
    )
    with pytest.raises(ValueError):
        wav.save(carrier, str(tmp_path / "partial.wav"))


# --- AUD-002: embed / extract round trips -----------------------------------


@pytest.mark.parametrize("bits", [1, 2, 3, 4, 5, 6, 7, 8])
def test_round_trip_all_bit_depths(mono_path, tmp_path, bits):
    carrier = wav.load(mono_path)
    payload = b"P3-6 test payload for round trip"
    stego = wav.embed(carrier, payload, num_lsb=bits)

    out = str(tmp_path / f"stego_{bits}.wav")
    wav.save(stego, out)
    reopened = wav.load(out)

    recovered = wav.extract(reopened, byte_count=len(payload), num_lsb=bits)
    assert recovered == payload


def test_round_trip_stereo(stereo_path, tmp_path):
    carrier = wav.load(stereo_path)
    payload = b"stereo payload spanning both channels"
    stego = wav.embed(carrier, payload, num_lsb=2)
    out = str(tmp_path / "stego_stereo.wav")
    wav.save(stego, out)
    reopened = wav.load(out)
    assert wav.extract(reopened, len(payload), num_lsb=2) == payload


def test_embed_only_changes_low_byte(mono_path):
    # num_lsb <= 8 only ever touches the low byte; the high byte must not move.
    carrier = wav.load(mono_path)
    stego = wav.embed(carrier, b"x" * 50, num_lsb=8)
    orig_high = carrier.samples.astype(np.uint16) & HIGH_BYTE_MASK
    stego_high = stego.samples.astype(np.uint16) & HIGH_BYTE_MASK
    assert np.array_equal(orig_high, stego_high)


def test_embed_leaves_input_unmodified(mono_path):
    # bitstream.embed_bits mutates in place; wav.embed must hand it a copy.
    carrier = wav.load(mono_path)
    before = carrier.samples.copy()
    wav.embed(carrier, b"does not touch original", num_lsb=4)
    assert np.array_equal(carrier.samples, before)


def test_embed_at_nonzero_start(mono_path, tmp_path):
    carrier = wav.load(mono_path)
    payload = b"offset start location"
    stego = wav.embed(carrier, payload, num_lsb=2, start_index=100)
    out = str(tmp_path / "offset.wav")
    wav.save(stego, out)
    reopened = wav.load(out)
    assert wav.extract(reopened, len(payload), num_lsb=2, start_index=100) == payload


def test_embed_does_not_touch_samples_before_start(mono_path):
    carrier = wav.load(mono_path)
    stego = wav.embed(carrier, b"payload", num_lsb=3, start_index=250)
    assert np.array_equal(stego.samples[:250], carrier.samples[:250])


# --- AUD-002: capacity and input guards -------------------------------------


def test_oversized_payload_rejected(mono_path):
    carrier = wav.load(mono_path)
    too_big = b"x" * 5000  # 2000 samples * 1 bit = 250 bytes max
    with pytest.raises(wav.WavCapacityError):
        wav.embed(carrier, too_big, num_lsb=1)


def test_bad_bits_rejected(mono_path):
    carrier = wav.load(mono_path)
    for bad in (0, 9, -1):
        with pytest.raises(ValueError):
            wav.embed(carrier, b"x", num_lsb=bad)


def test_bad_start_rejected(mono_path):
    carrier = wav.load(mono_path)
    with pytest.raises(ValueError):
        wav.embed(carrier, b"x", num_lsb=1, start_index=999999)


def test_embed_negative_start_rejected(mono_path):
    carrier = wav.load(mono_path)
    with pytest.raises(ValueError):
        wav.embed(carrier, b"x", num_lsb=1, start_index=-1)


def test_extract_negative_byte_count_rejected(mono_path):
    carrier = wav.load(mono_path)
    with pytest.raises(ValueError):
        wav.extract(carrier, byte_count=-4, num_lsb=2)


def test_extract_bad_bits_rejected(mono_path):
    carrier = wav.load(mono_path)
    for bad in (0, 9, -1):
        with pytest.raises(ValueError):
            wav.extract(carrier, byte_count=4, num_lsb=bad)


def test_extract_too_many_bytes_rejected(mono_path):
    carrier = wav.load(mono_path)
    with pytest.raises(wav.WavCapacityError):
        wav.extract(carrier, byte_count=100000, num_lsb=1)


def test_extract_start_out_of_range_rejected(mono_path):
    carrier = wav.load(mono_path)
    with pytest.raises(ValueError):
        wav.extract(carrier, byte_count=1, num_lsb=1, start_index=10_000_000)


# --- AUD-002: boundary and empty-payload coverage ---------------------------


def test_exact_fit_embed_round_trip(tmp_path):
    # Payload sized to fill the carrier exactly at 1 LSB, so the last sample is
    # used to its final bit. Off-by-one errors surface here.
    frames = 800
    samples = np.arange(-frames // 2, frames // 2, dtype=np.int16)
    carrier = wav.WavCarrier(
        info=wav.WavInfo(channels=1, sample_rate=44100, sample_width_bytes=2,
                         frame_count=frames),
        samples=samples,
    )
    exact_bytes = (frames * 1) // 8  # 100 bytes fills 800 samples at 1 bit
    payload = bytes(range(256))[:exact_bytes]
    assert len(payload) == exact_bytes

    stego = wav.embed(carrier, payload, num_lsb=1)
    out = str(tmp_path / "exact.wav")
    wav.save(stego, out)
    assert wav.extract(wav.load(out), exact_bytes, num_lsb=1) == payload


def test_one_byte_over_exact_fit_rejected():
    frames = 800
    carrier = wav.WavCarrier(
        info=wav.WavInfo(channels=1, sample_rate=44100, sample_width_bytes=2,
                         frame_count=frames),
        samples=np.zeros(frames, dtype=np.int16),
    )
    too_big = bytes(101)  # capacity is exactly 100 bytes at 1 bit
    with pytest.raises(wav.WavCapacityError):
        wav.embed(carrier, too_big, num_lsb=1)


def test_embed_empty_payload_leaves_samples_unchanged(mono_path):
    carrier = wav.load(mono_path)
    stego = wav.embed(carrier, b"", num_lsb=2)
    assert np.array_equal(stego.samples, carrier.samples)


# --- Shared bit convention (bitstream.py is the source of truth) -------------


def test_known_vector_msb_first_grouping():
    # One byte 0xB4 = bits 1,0,1,1,0,1,0,0 at 2 LSBs over zeroed samples.
    # Groups (MSB-first within each sample): (1,0)=2, (1,1)=3, (0,1)=1, (0,0)=0.
    carrier = wav.WavCarrier(
        info=wav.WavInfo(channels=1, sample_rate=8000, sample_width_bytes=2,
                         frame_count=8),
        samples=np.zeros(8, dtype=np.int16),
    )
    stego = wav.embed(carrier, bytes([0xB4]), num_lsb=2)
    assert list(stego.samples[:4]) == [2, 3, 1, 0]
    assert list(stego.samples[4:]) == [0, 0, 0, 0]  # untouched beyond the span


@pytest.mark.parametrize("num_lsb", [3, 6, 7])  # 80 payload bits do not divide evenly
def test_final_sample_tail_is_zero_padded(num_lsb):
    # 10 bytes = 80 bits, not a whole number of samples at these depths.
    # embed_bits zero-pads the final sample, so all span * num_lsb low bits
    # get written, and that's what the stable hash (HSH-FR-003) has to
    # normalise. Pinned here so a silent format change breaks loudly.
    rng = np.random.default_rng(11)
    samples = rng.integers(-3000, 3000, size=500, dtype=np.int16)
    carrier = wav.WavCarrier(
        info=wav.WavInfo(channels=1, sample_rate=44100, sample_width_bytes=2,
                         frame_count=500),
        samples=samples,
    )
    payload = b"P3-6 demo!"
    assert len(payload) * 8 % num_lsb != 0  # otherwise the case proves nothing

    stego = wav.embed(carrier, payload, num_lsb=num_lsb)

    span = wav.embedded_sample_span(len(payload), num_lsb)
    assert wav.embedded_bit_slots(len(payload), num_lsb) == span * num_lsb

    last = span - 1
    payload_bits_in_last = len(payload) * 8 - last * num_lsb
    for bit_index in range(num_lsb - payload_bits_in_last):
        # Unused low bits of the final sample are the pad; they must be zero.
        assert (int(stego.samples[last]) >> bit_index) & 1 == 0, (
            f"pad bit {bit_index} of the final sample is not zero"
        )

    # Samples after the span are untouched.
    assert np.array_equal(stego.samples[span:], carrier.samples[span:])

    # And the payload still round-trips.
    assert wav.extract(stego, len(payload), num_lsb=num_lsb) == payload


# --- Integration: wav.py and bitstream.py must be bit-identical --------------


@pytest.mark.parametrize("num_lsb", [1, 2, 3, 5, 8])
def test_wav_embed_readable_by_raw_bitstream(mono_path, num_lsb):
    # What wav.embed writes, bitstream.extract_bits must read back unchanged;
    # this is what lets payload.py / pipeline.py consume our files.
    carrier = wav.load(mono_path)
    payload = b"cross-module compatibility"
    stego = wav.embed(carrier, payload, num_lsb=num_lsb, start_index=37)

    bits = bitstream.extract_bits(stego.samples, 37, num_lsb, len(payload) * 8)
    assert bitstream.bits_to_bytes(bits) == payload


@pytest.mark.parametrize("num_lsb", [1, 2, 3, 5, 8])
def test_raw_bitstream_embed_readable_by_wav_extract(mono_path, num_lsb):
    # And the reverse direction.
    carrier = wav.load(mono_path)
    payload = b"pipeline wrote this one"

    mutable = carrier.samples.copy()
    bitstream.embed_bits(mutable, 37, num_lsb, bitstream.bytes_to_bits(payload))
    stego = wav.WavCarrier(info=carrier.info, samples=mutable)

    assert wav.extract(stego, len(payload), num_lsb=num_lsb, start_index=37) == payload


def test_stego_stream_round_trip_through_saved_wav(mono_path, tmp_path):
    # StegoStream is how payload.py builds the container format, so this is
    # the closest thing to the real pipeline path: write, save, reopen, read.
    carrier = wav.load(mono_path)
    mutable = carrier.samples.copy()

    writer = bitstream.StegoStream(mutable, start_index=10, num_lsb=2)
    writer.write(b"HEAD")
    writer.write(b"body of the message")

    out = str(tmp_path / "stream.wav")
    wav.save(wav.WavCarrier(info=carrier.info, samples=mutable), out)
    reopened = wav.load(out)

    reader = bitstream.StegoStream(reopened.samples, start_index=10, num_lsb=2)
    assert reader.read(4) == b"HEAD"
    assert reader.read(19) == b"body of the message"


# --- NFR-REL-003: a failed save must not damage an existing file -------------


def test_save_rejects_frame_count_that_disagrees_with_samples(tmp_path):
    carrier = wav.WavCarrier(
        info=wav.WavInfo(channels=1, sample_rate=44100, sample_width_bytes=2,
                         frame_count=999_999),
        samples=np.zeros(100, dtype=np.int16),
    )
    with pytest.raises(ValueError):
        wav.save(carrier, str(tmp_path / "mismatch.wav"))


def test_interrupted_save_leaves_previous_file_intact(tmp_path, monkeypatch):
    dst = tmp_path / "keep.wav"
    samples = np.arange(-50, 50, dtype=np.int16)
    carrier = wav.WavCarrier(
        info=wav.WavInfo(channels=1, sample_rate=44100, sample_width_bytes=2,
                         frame_count=samples.size),
        samples=samples,
    )
    wav.save(carrier, str(dst))
    before = dst.read_bytes()

    def fail_midway(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(wav.wave, "open", fail_midway)
    with pytest.raises(OSError):
        wav.save(carrier, str(dst))

    assert dst.read_bytes() == before          # old file survived
    assert not list(tmp_path.glob("*.tmp"))    # no temp file left behind