"""Basic chi-square steganalysis for files produced by steg_app.py."""

from __future__ import annotations

import math
import struct
import wave
import zlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


MAGIC = b"STEG1"
HEADER = struct.Struct(">5sII")


class AnalysisError(Exception):
    """Raised when a carrier cannot be analysed."""


@dataclass(frozen=True)
class DepthResult:
    lsb_count: int
    blocks_tested: int
    suspicious_blocks: int
    suspicious_fraction: float
    maximum_p_value: float
    longest_suspicious_run: int


@dataclass(frozen=True)
class PacketEvidence:
    start: int
    lsb_count: int
    message_length: int
    crc_valid: bool
    utf8_valid: bool


@dataclass(frozen=True)
class AnalysisResult:
    path: str
    kind: str
    carrier_count: int
    block_size: int
    verdict: str
    confidence: str
    depth_results: tuple[DepthResult, ...]
    packet_evidence: tuple[PacketEvidence, ...]


def _gammaincc(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x), using stdlib math only."""
    if a <= 0 or x < 0:
        raise ValueError("a must be positive and x must be non-negative")
    if x == 0:
        return 1.0

    epsilon = 3e-14
    tiny = 1e-300
    iterations = 300

    if x < a + 1:
        term = total = 1.0 / a
        ap = a
        for _ in range(iterations):
            ap += 1
            term *= x / ap
            total += term
            if abs(term) < abs(total) * epsilon:
                break
        lower = total * math.exp(-x + a * math.log(x) - math.lgamma(a))
        return min(1.0, max(0.0, 1.0 - lower))

    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / max(b, tiny)
    h = d
    for i in range(1, iterations + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < epsilon:
            break
    upper = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return min(1.0, max(0.0, upper))


def _chi_square_p_value(values: bytes, lsb_count: int) -> float:
    """Test whether frequencies are equal inside 2**lsb_count value groups."""
    frequencies = [0] * 256
    for value in values:
        frequencies[value] += 1

    group_size = 1 << lsb_count
    statistic = 0.0
    degrees = 0
    for base in range(0, 256, group_size):
        group = frequencies[base:base + group_size]
        total = sum(group)
        if total == 0:
            continue
        expected = total / group_size
        statistic += sum((observed - expected) ** 2 / expected for observed in group)
        degrees += group_size - 1

    if degrees == 0:
        return 0.0
    return _gammaincc(degrees / 2.0, statistic / 2.0)


def _load_carriers(path: str | Path) -> tuple[str, bytes]:
    suffix = Path(path).suffix.lower()
    if suffix == ".png":
        with Image.open(path) as source:
            if source.format != "PNG":
                raise AnalysisError(
                    f"The .png file contains {source.format} data, not PNG data."
                )
            image = source.convert("RGB")
            return "PNG", image.tobytes()

    if suffix == ".wav":
        try:
            with wave.open(str(path), "rb") as source:
                params = source.getparams()
                if params.comptype != "NONE":
                    raise AnalysisError("Only uncompressed PCM WAV is supported.")
                if params.sampwidth not in (1, 2, 3, 4):
                    raise AnalysisError("Unsupported WAV sample width.")
                raw = source.readframes(params.nframes)
        except (wave.Error, EOFError) as error:
            raise AnalysisError(f"Invalid WAV file: {error}") from error
        if len(raw) % params.sampwidth:
            raise AnalysisError("Invalid/alignment-broken PCM data.")
        return "WAV", raw[::params.sampwidth]

    raise AnalysisError("Select a .png or .wav file.")


def _extract_bytes(carriers: bytes, start: int, lsb_count: int,
                   byte_count: int) -> bytes:
    needed_bits = byte_count * 8
    mask = (1 << lsb_count) - 1
    chunks = []
    collected = 0
    for value in carriers[start:]:
        chunks.append(f"{value & mask:0{lsb_count}b}")
        collected += lsb_count
        if collected >= needed_bits:
            break
    bits = "".join(chunks)[:needed_bits]
    if len(bits) != needed_bits:
        raise ValueError("Insufficient carrier data")
    return bytes(int(bits[i:i + 8], 2) for i in range(0, needed_bits, 8))


def find_steg_packets(carriers: bytes, max_lsb: int = 8) -> tuple[PacketEvidence, ...]:
    """Search for intact STEG1 packets at unknown starts and LSB depths."""
    magic_bits = "".join(f"{byte:08b}" for byte in MAGIC)
    evidence = []
    for lsb_count in range(1, max_lsb + 1):
        mask = (1 << lsb_count) - 1
        stream = "".join(f"{value & mask:0{lsb_count}b}" for value in carriers)
        position = stream.find(magic_bits)
        while position != -1:
            if position % lsb_count == 0:
                start = position // lsb_count
                try:
                    header = _extract_bytes(carriers, start, lsb_count, HEADER.size)
                    magic, length, expected_crc = HEADER.unpack(header)
                    available = ((len(carriers) - start) * lsb_count) // 8
                    if magic == MAGIC and HEADER.size + length <= available:
                        packet = _extract_bytes(
                            carriers, start, lsb_count, HEADER.size + length
                        )
                        data = packet[HEADER.size:]
                        evidence.append(PacketEvidence(
                            start=start,
                            lsb_count=lsb_count,
                            message_length=length,
                            crc_valid=(zlib.crc32(data) & 0xFFFFFFFF) == expected_crc,
                            utf8_valid=_is_utf8(data),
                        ))
                except (ValueError, struct.error):
                    pass
            position = stream.find(magic_bits, position + 1)
    return tuple(evidence)


def _is_utf8(data: bytes) -> bool:
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _analyse_depth(carriers: bytes, lsb_count: int,
                   block_size: int, threshold: float) -> DepthResult:
    p_values = []
    # Very small final blocks produce unstable statistics, so omit them.
    for offset in range(0, len(carriers), block_size):
        block = carriers[offset:offset + block_size]
        if len(block) >= max(256, block_size // 2):
            p_values.append(_chi_square_p_value(block, lsb_count))

    suspicious = [value >= threshold for value in p_values]
    longest = run = 0
    for flagged in suspicious:
        run = run + 1 if flagged else 0
        longest = max(longest, run)
    count = sum(suspicious)
    return DepthResult(
        lsb_count=lsb_count,
        blocks_tested=len(p_values),
        suspicious_blocks=count,
        suspicious_fraction=count / len(p_values) if p_values else 0.0,
        maximum_p_value=max(p_values, default=0.0),
        longest_suspicious_run=longest,
    )


def analyse_file(path: str | Path, block_size: int = 4096,
                 max_lsb: int = 8, threshold: float = 0.99,
                 search_packets: bool = True) -> AnalysisResult:
    """Analyse a PNG or PCM WAV and return statistical and packet evidence."""
    if block_size < 256:
        raise AnalysisError("Block size must be at least 256 carriers.")
    if not 1 <= max_lsb <= 8:
        raise AnalysisError("Maximum LSB count must be 1..8.")
    if not 0 < threshold < 1:
        raise AnalysisError("Threshold must be between 0 and 1.")

    kind, carriers = _load_carriers(path)
    depth_results = tuple(
        _analyse_depth(carriers, depth, block_size, threshold)
        for depth in range(1, max_lsb + 1)
    )
    packets = find_steg_packets(carriers, max_lsb) if search_packets else ()
    valid_packets = [item for item in packets if item.crc_valid and item.utf8_valid]

    if valid_packets:
        verdict = "STEG1 payload detected"
        confidence = "confirmed"
    else:
        strongest = max(depth_results, key=lambda item: item.suspicious_fraction)
        if (strongest.suspicious_fraction >= 0.30 and
                strongest.suspicious_blocks >= 2):
            verdict = "Strong statistical anomaly consistent with LSB embedding"
            confidence = "medium"
        elif (strongest.suspicious_fraction >= 0.12 or
              strongest.longest_suspicious_run >= 2):
            verdict = "LSB embedding possible"
            confidence = "medium"
        else:
            verdict = "No strong evidence of LSB embedding"
            confidence = "low"

    return AnalysisResult(
        path=str(path), kind=kind, carrier_count=len(carriers),
        block_size=block_size, verdict=verdict, confidence=confidence,
        depth_results=depth_results, packet_evidence=packets,
    )
