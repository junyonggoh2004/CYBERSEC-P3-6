import tempfile
import unittest
from pathlib import Path

from steg_analysis import AnalysisError, analyse_file
from steg_app import encode_png, encode_wav


class StegAnalysisTests(unittest.TestCase):
    def test_detects_png_outputs_at_all_lsb_depths(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "stego.png"
            for depth in range(1, 9):
                with self.subTest(depth=depth):
                    encode_png("sample_cover.png", output, "small secret", 37, depth)
                    result = analyse_file(output)
                    matches = [
                        item for item in result.packet_evidence
                        if item.start == 37 and item.lsb_count == depth
                        and item.crc_valid and item.utf8_valid
                    ]
                    self.assertTrue(matches)
                    self.assertEqual(result.confidence, "confirmed")

    def test_detects_wav_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "stego.wav"
            encode_wav("sample_cover.wav", output, "audio secret", 101, 3)
            result = analyse_file(output)
            self.assertEqual(result.kind, "WAV")
            self.assertTrue(any(
                item.start == 101 and item.lsb_count == 3 and item.crc_valid
                for item in result.packet_evidence
            ))

    def test_blind_chi_square_flags_a_large_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "stego.png"
            encode_png("sample_cover.png", output, "X" * 12000, 0, 1)
            result = analyse_file(output, search_packets=False)
            depth_one = result.depth_results[0]
            self.assertGreater(depth_one.suspicious_blocks, 0)

    def test_clean_cover_has_no_packet_confirmation(self):
        result = analyse_file("sample_cover.png")
        self.assertFalse(result.packet_evidence)
        self.assertNotEqual(result.confidence, "confirmed")

    def test_rejects_invalid_settings(self):
        with self.assertRaises(AnalysisError):
            analyse_file("sample_cover.png", block_size=100)


if __name__ == "__main__":
    unittest.main()
