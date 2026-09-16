import tempfile
import unittest
from pathlib import Path

from PIL import Image

from steg_app import StegError, carrier_info, decode_png, encode_png


class PngExportTests(unittest.TestCase):
    def test_webp_with_png_extension_exports_real_png(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "cover.png"
            output = Path(directory) / "stego.png"
            Image.new("RGB", (64, 64), (50, 100, 150)).save(source, "WEBP")
            original = source.read_bytes()

            kind, _, count, usable = carrier_info(source, 7, 3)
            self.assertEqual(kind, "PNG")
            self.assertEqual(count, 64 * 64 * 3)
            self.assertGreater(usable, 0)
            encode_png(source, output, "Hidden text \u2713", start=7, lsb_count=3)

            with Image.open(output) as image:
                self.assertEqual(image.format, "PNG")
            self.assertEqual(decode_png(output, 7, 3), "Hidden text \u2713")
            self.assertEqual(source.read_bytes(), original)
            with self.assertRaisesRegex(StegError, "contains WEBP"):
                decode_png(source)

    def test_png_modes_round_trip_and_preserve_alpha(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "cover.png"
            output = Path(directory) / "stego.png"
            for mode in ("RGB", "RGBA", "P", "L", "LA", "1", "I;16"):
                cover = Image.new(mode, (64, 64))
                cover.save(source, "PNG")
                for lsb in range(1, 9):
                    with self.subTest(mode=mode, lsb=lsb):
                        encode_png(source, output, "Hidden text", 7, lsb)
                        self.assertEqual(decode_png(output, 7, lsb), "Hidden text")
                        if "A" in cover.getbands():
                            with Image.open(output) as result:
                                self.assertEqual(
                                    result.getchannel("A").tobytes(),
                                    cover.getchannel("A").tobytes(),
                                )


if __name__ == "__main__":
    unittest.main()
