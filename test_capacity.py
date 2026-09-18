"""Tests for the carrier capacity calculator.

These are written to prove the arithmetic holds generically (across a range of
carrier sizes and all bit depths 1-8) rather than for one fixed sample file,
because the application must handle any PNG or WAV supplied at demo time.
"""

import pytest

from capacity import (
    CapacityExceededError,
    CapacityReport,
    InvalidCapacityInputError,
    PackageOverhead,
    calculate_capacity,
    require_capacity,
)


# --- exact-fit and boundary behaviour --------------------------------------


def test_exact_fit_is_accepted():
    # 1000 units * 1 bit = 1000 bits; minus 64 bootstrap = 936 bits = 117 bytes.
    report = calculate_capacity(
        total_units=1000,
        num_lsb=1,
        reserved_bootstrap_bits=64,
        payload_bytes=117,
    )
    assert report.available_bytes == 117
    assert report.fits is True
    assert report.remaining_bytes == 0
    assert report.shortfall_bytes == 0


def test_one_byte_over_capacity_is_rejected():
    report = calculate_capacity(
        total_units=1000,
        num_lsb=1,
        reserved_bootstrap_bits=64,
        payload_bytes=118,
    )
    assert report.fits is False
    assert report.shortfall_bytes == 1
    assert report.remaining_bytes == 0


def test_one_byte_under_capacity_leaves_one_byte_free():
    report = calculate_capacity(
        total_units=1000,
        num_lsb=1,
        reserved_bootstrap_bits=64,
        payload_bytes=116,
    )
    assert report.fits is True
    assert report.remaining_bytes == 1


# --- generic scaling across bit depths and carrier sizes -------------------


@pytest.mark.parametrize("num_lsb", [1, 2, 3, 4, 5, 6, 7, 8])
def test_all_supported_bit_depths_are_accepted(num_lsb):
    report = calculate_capacity(
        total_units=10_000,
        num_lsb=num_lsb,
        reserved_bootstrap_bits=64,
        payload_bytes=0,
    )
    expected_bits = 10_000 * num_lsb - 64
    assert report.available_bytes == expected_bits // 8


def test_higher_bit_depth_gives_more_capacity():
    common = dict(total_units=10_000, reserved_bootstrap_bits=64, payload_bytes=0)
    low = calculate_capacity(num_lsb=1, **common)
    high = calculate_capacity(num_lsb=8, **common)
    assert high.available_bytes > low.available_bytes


@pytest.mark.parametrize("eligible_units", [1, 500, 10_000, 5_000_000])
def test_capacity_scales_with_carrier_size(eligible_units):
    report = calculate_capacity(
        total_units=eligible_units,
        num_lsb=1,
        reserved_bootstrap_bits=0,
        payload_bytes=0,
    )
    assert report.available_bytes == eligible_units // 8


# --- overhead handling ------------------------------------------------------


def test_overhead_reduces_remaining_space():
    overhead = PackageOverhead(frame_header_bytes=8, signature_bytes=64)
    report = calculate_capacity(
        total_units=8000,
        num_lsb=1,
        reserved_bootstrap_bits=0,
        payload_bytes=100,
        overhead=overhead,
    )
    assert report.available_bytes == 1000
    assert report.overhead_bytes == 72
    assert report.required_bytes == 172
    assert report.remaining_bytes == 828


def test_omitted_overhead_treats_package_as_payload_only():
    report = calculate_capacity(
        total_units=8000,
        num_lsb=1,
        reserved_bootstrap_bits=0,
        payload_bytes=100,
    )
    assert report.overhead_bytes == 0
    assert report.required_bytes == 100


def test_encryption_overhead_counts_toward_required():
    signed_only = calculate_capacity(
        total_units=8000, num_lsb=1, reserved_bootstrap_bits=0,
        payload_bytes=100, overhead=PackageOverhead(signature_bytes=64),
    )
    encrypted = calculate_capacity(
        total_units=8000, num_lsb=1, reserved_bootstrap_bits=0,
        payload_bytes=100,
        overhead=PackageOverhead(signature_bytes=64, encryption_overhead_bytes=28),
    )
    assert encrypted.required_bytes == signed_only.required_bytes + 28


# --- unavailable prefix (e.g. manual start location) ------------------------


def test_unavailable_prefix_reduces_usable_bits():
    without_prefix = calculate_capacity(
        total_units=8000, num_lsb=1, reserved_bootstrap_bits=0,
        payload_bytes=0,
    )
    with_prefix = calculate_capacity(
        total_units=8000, num_lsb=1, reserved_bootstrap_bits=0,
        payload_bytes=0, unavailable_prefix_bits=800,
    )
    assert with_prefix.available_bytes == without_prefix.available_bytes - 100


def test_reservations_exceeding_carrier_clamp_to_zero():
    report = calculate_capacity(
        total_units=10,
        num_lsb=1,
        reserved_bootstrap_bits=64,
        payload_bytes=0,
    )
    assert report.usable_bits == 0
    assert report.available_bytes == 0
    assert report.fits is True  # a zero-byte payload fits a zero-byte carrier


# --- input validation -------------------------------------------------------


@pytest.mark.parametrize("bad_bits", [0, 9, -1, 16])
def test_bit_depth_outside_1_to_8_is_rejected(bad_bits):
    with pytest.raises(InvalidCapacityInputError):
        calculate_capacity(
            total_units=1000, num_lsb=bad_bits,
            reserved_bootstrap_bits=0, payload_bytes=0,
        )


def test_negative_eligible_units_is_rejected():
    with pytest.raises(InvalidCapacityInputError):
        calculate_capacity(
            total_units=-1, num_lsb=1,
            reserved_bootstrap_bits=0, payload_bytes=0,
        )


def test_negative_payload_is_rejected():
    with pytest.raises(InvalidCapacityInputError):
        calculate_capacity(
            total_units=1000, num_lsb=1,
            reserved_bootstrap_bits=0, payload_bytes=-5,
        )


@pytest.mark.parametrize("bad_num_lsb", [2.5, True])  # float path, and the bool special case
def test_non_integer_num_lsb_is_rejected(bad_num_lsb):
    # 2.5 passes a plain 1 <= x <= 8 range check and makes every derived size a
    # float; True is an int subclass that would silently mean 1.
    with pytest.raises(InvalidCapacityInputError):
        calculate_capacity(
            total_units=1000, num_lsb=bad_num_lsb,
            reserved_bootstrap_bits=0, payload_bytes=0,
        )


def test_non_integer_sizes_are_rejected():
    for field in ("total_units", "reserved_bootstrap_bits", "payload_bytes",
                  "unavailable_prefix_bits"):
        args = dict(total_units=1000, num_lsb=1, reserved_bootstrap_bits=0,
                    payload_bytes=0)
        args[field] = 10.5
        with pytest.raises(InvalidCapacityInputError):
            calculate_capacity(**args)


def test_numpy_integers_are_accepted():
    # A carrier adapter may hand over a NumPy integer; that is a whole number
    # and must not be mistaken for a bad input.
    np = pytest.importorskip("numpy")
    report = calculate_capacity(
        total_units=np.int64(8000), num_lsb=np.int32(1),
        reserved_bootstrap_bits=np.int64(0), payload_bytes=np.int64(100),
    )
    assert report.available_bytes == 1000
    assert isinstance(report.available_bytes, int)
    assert isinstance(report.usable_bits, int)


def test_non_integer_overhead_component_is_rejected():
    with pytest.raises(InvalidCapacityInputError):
        calculate_capacity(
            total_units=1000, num_lsb=1, reserved_bootstrap_bits=0,
            payload_bytes=0, overhead=PackageOverhead(signature_bytes=64.5),
        )


def test_negative_overhead_component_is_rejected():
    with pytest.raises(InvalidCapacityInputError):
        calculate_capacity(
            total_units=1000, num_lsb=1, reserved_bootstrap_bits=0,
            payload_bytes=0, overhead=PackageOverhead(signature_bytes=-64),
        )


# --- fail-closed guard ------------------------------------------------------


def test_require_capacity_returns_report_when_it_fits():
    report = require_capacity(
        total_units=1000, num_lsb=1,
        reserved_bootstrap_bits=64, payload_bytes=100,
    )
    assert isinstance(report, CapacityReport)
    assert report.fits is True


def test_require_capacity_raises_when_it_does_not_fit():
    with pytest.raises(CapacityExceededError) as exc_info:
        require_capacity(
            total_units=1000, num_lsb=1,
            reserved_bootstrap_bits=64, payload_bytes=200,
        )
    # the report travels with the exception so callers can show a breakdown
    assert exc_info.value.report.shortfall_bytes > 0
    assert "short by" in str(exc_info.value)