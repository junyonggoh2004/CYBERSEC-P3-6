"""Command-line interface for steg_analysis.py."""

import argparse
import json
from dataclasses import asdict

from steg_analysis import AnalysisError, analyse_file


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run chi-square LSB steganalysis on a PNG or PCM WAV file."
    )
    parser.add_argument("file", help="PNG or uncompressed PCM WAV to analyse")
    parser.add_argument("--block-size", type=int, default=4096,
                        help="carrier values per statistical block (default: 4096)")
    parser.add_argument("--max-lsb", type=int, default=8,
                        help="highest LSB depth to test, 1..8 (default: 8)")
    parser.add_argument("--threshold", type=float, default=0.99,
                        help="p-value that flags a block (default: 0.99)")
    parser.add_argument("--no-packet-search", action="store_true",
                        help="run only blind chi-square analysis")
    parser.add_argument("--json", action="store_true",
                        help="print machine-readable JSON")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = analyse_file(
            args.file, block_size=args.block_size, max_lsb=args.max_lsb,
            threshold=args.threshold, search_packets=not args.no_packet_search,
        )
    except (AnalysisError, OSError) as error:
        print(f"Analysis failed: {error}")
        return 2

    if args.json:
        print(json.dumps(asdict(result), indent=2))
        return 0

    print(f"File: {result.path}")
    print(f"Carrier: {result.kind}, {result.carrier_count:,} values")
    print(f"Verdict: {result.verdict} ({result.confidence} confidence)")
    print("\nChi-square results:")
    print("LSBs  flagged/tested  fraction   max p-value  longest run")
    for item in result.depth_results:
        print(
            f"{item.lsb_count:>4}  "
            f"{item.suspicious_blocks:>7}/{item.blocks_tested:<7}  "
            f"{item.suspicious_fraction:>7.1%}   "
            f"{item.maximum_p_value:>11.6f}  "
            f"{item.longest_suspicious_run:>11}"
        )
    if result.packet_evidence:
        print("\nSTEG1 packet evidence:")
        for item in result.packet_evidence:
            print(
                f"start={item.start:,}, LSBs={item.lsb_count}, "
                f"message_bytes={item.message_length:,}, "
                f"CRC={'valid' if item.crc_valid else 'invalid'}, "
                f"UTF-8={'valid' if item.utf8_valid else 'invalid'}"
            )
    else:
        print("\nNo intact STEG1 packet marker was found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

