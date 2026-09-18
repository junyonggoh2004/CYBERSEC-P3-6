"""Carrier capacity calculation for LSB embedding.

Carrier- and algorithm-agnostic: takes unit counts and byte sizes, not files
or crypto constants. The caller passes in bootstrap/signature/encryption sizes
so this module never hardcodes them and works for both image and audio carriers.

Uses the same `num_lsb` / `start_index` naming as bitstream.py so it slots into
the existing pipeline without adapters.

    calculate_capacity() -> CapacityReport, never raises (use for the GUI display)
    require_capacity()   -> raises CapacityExceededError if it won't fit (use before embedding)
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral

MIN_LSB = 1
MAX_LSB = 8


class CapacityError(ValueError):
    """Base class for capacity errors."""


class InvalidCapacityInputError(CapacityError):
    """An input is invalid, e.g. num_lsb outside 1-8 or a negative size."""


class CapacityExceededError(CapacityError):
    """The package does not fit. Carries the report so the caller can show why."""

    def __init__(self, report: "CapacityReport") -> None:
        self.report = report
        super().__init__(
            f"Package of {report.required_bytes} bytes does not fit; "
            f"carrier holds {report.available_bytes} bytes "
            f"(short by {report.shortfall_bytes} bytes)."
        )


def _require_int(name: str, value: object) -> int:
    """Reject anything that is not a whole number, e.g. a float from a GUI field.

    Checked against numbers.Integral, so a NumPy integer handed over by a
    carrier adapter is fine while a float, string or bool is not: 2.5 LSBs is
    meaningless, and True is a flag rather than a count. Without this the range
    checks below pass 2.5 happily and every size derived from it comes out as a
    float.
    """
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise InvalidCapacityInputError(
            f"{name} must be a whole number "
            f"(got {value!r} of type {type(value).__name__})."
        )
    return int(value)


@dataclass(frozen=True)
class PackageOverhead:
    """Byte sizes of the non-payload parts of a package.

    Fields default to zero so a caller supplies only what applies (e.g. no
    encryption overhead in signed-only mode).
    """

    frame_header_bytes: int = 0
    signature_bytes: int = 0
    encryption_overhead_bytes: int = 0
    other_overhead_bytes: int = 0

    def total(self) -> int:
        return (
            self.frame_header_bytes
            + self.signature_bytes
            + self.encryption_overhead_bytes
            + self.other_overhead_bytes
        )

    def validate(self) -> None:
        for name, value in (
            ("frame_header_bytes", self.frame_header_bytes),
            ("signature_bytes", self.signature_bytes),
            ("encryption_overhead_bytes", self.encryption_overhead_bytes),
            ("other_overhead_bytes", self.other_overhead_bytes),
        ):
            if _require_int(name, value) < 0:
                raise InvalidCapacityInputError(f"{name} must not be negative (got {value}).")


@dataclass(frozen=True)
class CapacityReport:
    """Result of a capacity calculation. All sizes in bytes."""

    available_bytes: int
    required_bytes: int
    payload_bytes: int
    overhead_bytes: int
    usable_bits: int
    num_lsb: int
    total_units: int

    @property
    def fits(self) -> bool:
        return self.required_bytes <= self.available_bytes

    @property
    def remaining_bytes(self) -> int:
        """Free bytes after the package; 0 if it doesn't fit."""
        return max(self.available_bytes - self.required_bytes, 0)

    @property
    def shortfall_bytes(self) -> int:
        """Bytes the carrier is short by; 0 if it fits."""
        return max(self.required_bytes - self.available_bytes, 0)


def _validate_inputs(
    total_units: int,
    num_lsb: int,
    reserved_bootstrap_bits: int,
    unavailable_prefix_bits: int,
    payload_bytes: int,
) -> tuple[int, int, int, int, int]:
    """Check every input and return them as plain ints for the report."""
    total_units = _require_int("total_units", total_units)
    num_lsb = _require_int("num_lsb", num_lsb)
    reserved_bootstrap_bits = _require_int("reserved_bootstrap_bits", reserved_bootstrap_bits)
    unavailable_prefix_bits = _require_int("unavailable_prefix_bits", unavailable_prefix_bits)
    payload_bytes = _require_int("payload_bytes", payload_bytes)

    if total_units < 0:
        raise InvalidCapacityInputError(f"total_units must not be negative (got {total_units}).")
    if not (MIN_LSB <= num_lsb <= MAX_LSB):
        raise InvalidCapacityInputError(
            f"num_lsb must be between {MIN_LSB} and {MAX_LSB} (got {num_lsb})."
        )
    if reserved_bootstrap_bits < 0:
        raise InvalidCapacityInputError(f"reserved_bootstrap_bits must not be negative (got {reserved_bootstrap_bits}).")
    if unavailable_prefix_bits < 0:
        raise InvalidCapacityInputError(f"unavailable_prefix_bits must not be negative (got {unavailable_prefix_bits}).")
    if payload_bytes < 0:
        raise InvalidCapacityInputError(f"payload_bytes must not be negative (got {payload_bytes}).")

    return (total_units, num_lsb, reserved_bootstrap_bits,
            unavailable_prefix_bits, payload_bytes)


def calculate_capacity(
    total_units: int,
    num_lsb: int,
    reserved_bootstrap_bits: int,
    payload_bytes: int,
    overhead: PackageOverhead | None = None,
    unavailable_prefix_bits: int = 0,
) -> CapacityReport:
    """Report whether a package fits. Raises only on invalid input, not on overflow.

    Args:
        total_units: Usable carrier units (colour-channel bytes for images, PCM
            samples for audio). The carrier adapter computes this from the file.
        num_lsb: LSBs used per unit, 1-8.
        reserved_bootstrap_bits: Bits used by the fixed-location bootstrap. Owned
            by the frame design, so the caller supplies it.
        payload_bytes: Payload size before overhead.
        overhead: Non-payload component sizes; omit for a payload-only estimate.
        unavailable_prefix_bits: Leading capacity that can't be used, e.g. bits
            before a manual start location.
    """
    (total_units, num_lsb, reserved_bootstrap_bits, unavailable_prefix_bits,
     payload_bytes) = _validate_inputs(
        total_units, num_lsb, reserved_bootstrap_bits, unavailable_prefix_bits, payload_bytes)

    if overhead is None:
        overhead = PackageOverhead()
    overhead.validate()

    usable_bits = max(total_units * num_lsb - reserved_bootstrap_bits - unavailable_prefix_bits, 0)
    overhead_bytes = overhead.total()

    return CapacityReport(
        available_bytes=usable_bits // 8,
        required_bytes=payload_bytes + overhead_bytes,
        payload_bytes=payload_bytes,
        overhead_bytes=overhead_bytes,
        usable_bits=usable_bits,
        num_lsb=num_lsb,
        total_units=total_units,
    )


def require_capacity(
    total_units: int,
    num_lsb: int,
    reserved_bootstrap_bits: int,
    payload_bytes: int,
    overhead: PackageOverhead | None = None,
    unavailable_prefix_bits: int = 0,
) -> CapacityReport:
    """Like calculate_capacity, but raises CapacityExceededError if it won't fit.

    Used on the embedding path so an oversized package can't slip through.
    """
    report = calculate_capacity(
        total_units=total_units,
        num_lsb=num_lsb,
        reserved_bootstrap_bits=reserved_bootstrap_bits,
        payload_bytes=payload_bytes,
        overhead=overhead,
        unavailable_prefix_bits=unavailable_prefix_bits,
    )
    if not report.fits:
        raise CapacityExceededError(report)
    return report