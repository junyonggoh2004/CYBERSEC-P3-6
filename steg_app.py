
import math
import struct
import wave
import zlib
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image

MAGIC = b"STEG1"
HEADER = struct.Struct(">5sII")  # magic, UTF-8 byte length, CRC32
HEADER_SIZE = HEADER.size

class StegError(Exception):
    pass

def build_packet(message: str) -> bytes:
    """str -> framed bytes: MAGIC + length + CRC32 + UTF-8 text."""
    data = message.encode("utf-8")
    crc = zlib.crc32(data) & 0xFFFFFFFF
    return HEADER.pack(MAGIC, len(data), crc) + data

def _bits(data: bytes) -> str:
    return "".join(f"{b:08b}" for b in data)

def embed_packet(raw, carrier_count, mapper, packet, start=0, lsb_count=1):
    """Embed packet bytes into selected LSBs of mapped carrier bytes."""
    if not 1 <= lsb_count <= 8:
        raise StegError("LSB count must be 1..8.")
    if not 0 <= start < carrier_count:
        raise StegError("Start location is outside the carrier.")

    bits = _bits(packet)
    capacity_bits = (carrier_count - start) * lsb_count
    if len(bits) > capacity_bits:
        raise StegError(
            f"Payload needs {math.ceil(len(bits)/8)} bytes, "
            f"but only {capacity_bits//8} bytes fit."
        )

    mask = (1 << lsb_count) - 1
    clear_mask = 0xFF ^ mask
    pos = 0

    for carrier_index in range(start, carrier_count):
        if pos >= len(bits):
            break
        chunk = bits[pos:pos + lsb_count].ljust(lsb_count, "0")
        raw_index = mapper(carrier_index)
        raw[raw_index] = (raw[raw_index] & clear_mask) | int(chunk, 2)
        pos += lsb_count
    return raw

def extract_bytes(raw, carrier_count, mapper, start, lsb_count, byte_count):
    """Extract byte_count bytes from carrier LSBs."""
    if not 1 <= lsb_count <= 8:
        raise StegError("LSB count must be 1..8.")
    if not 0 <= start < carrier_count:
        raise StegError("Start location is outside the carrier.")

    needed_bits = byte_count * 8
    if needed_bits > (carrier_count - start) * lsb_count:
        raise StegError("Not enough carrier data to extract requested bytes.")

    mask = (1 << lsb_count) - 1
    out = []
    collected = 0
    for carrier_index in range(start, carrier_count):
        out.append(f"{raw[mapper(carrier_index)] & mask:0{lsb_count}b}")
        collected += lsb_count
        if collected >= needed_bits:
            break

    bit_string = "".join(out)[:needed_bits]
    return bytes(int(bit_string[i:i+8], 2) for i in range(0, needed_bits, 8))

def decode_packet(raw, carrier_count, mapper, start=0, lsb_count=1) -> str:
    """Extract header, then full packet; verify marker/CRC; return UTF-8 text."""
    header = extract_bytes(raw, carrier_count, mapper, start, lsb_count, HEADER_SIZE)
    magic, length, expected_crc = HEADER.unpack(header)
    if magic != MAGIC:
        raise StegError("No STEG1 payload found. Check start location and LSB count.")

    packet = extract_bytes(
        raw, carrier_count, mapper, start, lsb_count, HEADER_SIZE + length
    )
    data = packet[HEADER_SIZE:]
    actual_crc = zlib.crc32(data) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        raise StegError("CRC check failed; payload is damaged or settings are wrong.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise StegError("Extracted payload is not valid UTF-8.") from e

def _load_png(path, *, allow_conversion=False):
    with Image.open(path) as source:
        if source.format != "PNG" and not allow_conversion:
            raise StegError(
                f"Decoding requires PNG image data; this file contains {source.format}. "
                "Select the exported stego PNG file."
            )
        if source.mode not in ("RGB", "RGBA"):
            has_alpha = "A" in source.getbands() or "transparency" in source.info
            image = source.convert("RGBA" if has_alpha else "RGB")
        else:
            image = source.copy()

    channels = 4 if image.mode == "RGBA" else 3
    raw = bytearray(image.tobytes())
    carrier_count = image.width * image.height * 3  # RGB only; skip alpha

    if channels == 3:
        mapper = lambda i: i
    else:
        def mapper(i):
            pixel, channel = divmod(i, 3)
            return pixel * 4 + channel
    return image, raw, carrier_count, mapper

def encode_png(input_path, output_path, message, start=0, lsb_count=1):
    """Cover image + text/settings -> new lossless stego PNG file."""
    image, raw, count, mapper = _load_png(input_path, allow_conversion=True)
    embed_packet(raw, count, mapper, build_packet(message), start, lsb_count)
    Image.frombytes(image.mode, image.size, bytes(raw)).save(output_path, "PNG")

def decode_png(input_path, start=0, lsb_count=1) -> str:
    """Stego PNG + settings -> hidden text."""
    _, raw, count, mapper = _load_png(input_path)
    return decode_packet(raw, count, mapper, start, lsb_count)

def _load_wav(path):
    with wave.open(str(path), "rb") as wf:
        params = wf.getparams()
        if params.comptype != "NONE":
            raise StegError("Only uncompressed PCM WAV is supported.")
        if params.sampwidth not in (1, 2, 3, 4):
            raise StegError("Unsupported WAV sample width.")
        raw = bytearray(wf.readframes(params.nframes))

    width = params.sampwidth
    if len(raw) % width:
        raise StegError("Invalid/alignment-broken PCM data.")

    carrier_count = len(raw) // width
    mapper = lambda i: i * width  # WAV PCM is little-endian: low byte first
    return params, raw, carrier_count, mapper

def encode_wav(input_path, output_path, message, start=0, lsb_count=1):
    """PCM WAV path + text/settings -> new stego WAV file."""
    params, raw, count, mapper = _load_wav(input_path)
    embed_packet(raw, count, mapper, build_packet(message), start, lsb_count)
    with wave.open(str(output_path), "wb") as wf:
        wf.setparams(params)
        wf.writeframes(bytes(raw))

def decode_wav(input_path, start=0, lsb_count=1) -> str:
    """Stego PCM WAV + settings -> hidden text."""
    _, raw, count, mapper = _load_wav(input_path)
    return decode_packet(raw, count, mapper, start, lsb_count)

def carrier_info(path, start, lsb_count):
    suffix = Path(path).suffix.lower()
    if suffix == ".png":
        _, _, count, _ = _load_png(path, allow_conversion=True)
        kind, unit = "PNG", "RGB channel values"
    elif suffix == ".wav":
        _, _, count, _ = _load_wav(path)
        kind, unit = "WAV", "PCM samples"
    else:
        raise StegError("Select a .png or .wav file.")

    if not 0 <= start < count:
        raise StegError(f"Start must be 0..{count-1}.")
    usable = max(0, ((count - start) * lsb_count) // 8 - HEADER_SIZE)
    return kind, unit, count, usable

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PNG / WAV LSB Steganography")
        self.geometry("760x600")
        self.file_var = tk.StringVar()
        self.start_var = tk.StringVar(value="0")
        self.lsb_var = tk.IntVar(value=1)
        self.info_var = tk.StringVar(value="Select a PNG or PCM WAV file.")
        self.status_var = tk.StringVar(value="Ready.")
        self._ui()

    def _ui(self):
        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="PNG / WAV LSB Steganography",
                  font=("TkDefaultFont", 16, "bold")).pack(anchor="w")
        ttk.Label(f, text="Simple educational encoder/decoder for PNG and PCM WAV.",
                  wraplength=710).pack(anchor="w", pady=(4, 12))

        row = ttk.LabelFrame(f, text="1. File", padding=10)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.file_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse...", command=self.browse).pack(side="left", padx=(8,0))

        opt = ttk.LabelFrame(f, text="2. Settings", padding=10)
        opt.pack(fill="x", pady=10)
        ttk.Label(opt, text="LSBs (1–8):").grid(row=0, column=0, sticky="w")
        sp = ttk.Spinbox(opt, from_=1, to=8, textvariable=self.lsb_var, width=6,
                         command=self.refresh)
        sp.grid(row=0, column=1, padx=(8,25))
        ttk.Label(opt, text="Start carrier index:").grid(row=0, column=2, sticky="w")
        en = ttk.Entry(opt, textvariable=self.start_var, width=14)
        en.grid(row=0, column=3, padx=(8,0))
        sp.bind("<KeyRelease>", lambda e: self.refresh())
        en.bind("<KeyRelease>", lambda e: self.refresh())
        ttk.Label(opt, textvariable=self.info_var, wraplength=690).grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(8,0)
        )

        msg = ttk.LabelFrame(f, text="3. Hidden text", padding=10)
        msg.pack(fill="both", expand=True)
        self.text = tk.Text(msg, wrap="word", height=15)
        self.text.pack(fill="both", expand=True)

        buttons = ttk.Frame(f)
        buttons.pack(fill="x", pady=10)
        ttk.Button(buttons, text="Encode → Save Stego File",
                   command=self.encode).pack(side="left")
        ttk.Button(buttons, text="Decode Selected File",
                   command=self.decode).pack(side="left", padx=8)
        ttk.Button(buttons, text="Clear Text",
                   command=lambda: self.text.delete("1.0", "end")).pack(side="left")

        ttk.Separator(f).pack(fill="x", pady=(2,8))
        ttk.Label(f, textvariable=self.status_var, wraplength=710).pack(anchor="w")

    def settings(self):
        try:
            start, lsb = int(self.start_var.get()), int(self.lsb_var.get())
        except ValueError:
            raise StegError("Start and LSB count must be integers.")
        if start < 0 or not 1 <= lsb <= 8:
            raise StegError("Start must be >= 0 and LSB count must be 1..8.")
        return start, lsb

    def browse(self):
        path = filedialog.askopenfilename(
            filetypes=[("PNG/WAV", "*.png *.wav"), ("PNG", "*.png"),
                       ("WAV", "*.wav"), ("All files", "*.*")]
        )
        if path:
            self.file_var.set(path)
            self.refresh()

    def refresh(self):
        path = self.file_var.get().strip()
        if not path:
            return
        try:
            start, lsb = self.settings()
            kind, unit, count, usable = carrier_info(path, start, lsb)
            self.info_var.set(
                f"{kind}: {count:,} usable {unit}; about {usable:,} payload bytes "
                f"available from start {start:,} at {lsb} LSB(s)."
            )
        except Exception as e:
            self.info_var.set(str(e))

    def encode(self):
        try:
            path = self.file_var.get().strip()
            if not path:
                raise StegError("Select a file first.")
            start, lsb = self.settings()
            message = self.text.get("1.0", "end-1c")
            suffix = Path(path).suffix.lower()

            if suffix == ".png":
                out = filedialog.asksaveasfilename(
                    defaultextension=".png", filetypes=[("PNG", "*.png")],
                    initialfile=Path(path).stem + "_stego.png"
                )
                if not out: return
                encode_png(path, out, message, start, lsb)
            elif suffix == ".wav":
                out = filedialog.asksaveasfilename(
                    defaultextension=".wav", filetypes=[("WAV", "*.wav")],
                    initialfile=Path(path).stem + "_stego.wav"
                )
                if not out: return
                encode_wav(path, out, message, start, lsb)
            else:
                raise StegError("Select a .png or .wav file.")

            self.status_var.set(f"Encoded successfully: {out}")
            messagebox.showinfo("Success", "Stego file saved.")
        except Exception as e:
            self.status_var.set(f"Encoding failed: {e}")
            messagebox.showerror("Encoding failed", str(e))

    def decode(self):
        try:
            path = self.file_var.get().strip()
            if not path:
                raise StegError("Select a file first.")
            start, lsb = self.settings()
            suffix = Path(path).suffix.lower()

            if suffix == ".png":
                message = decode_png(path, start, lsb)
            elif suffix == ".wav":
                message = decode_wav(path, start, lsb)
            else:
                raise StegError("Select a .png or .wav file.")

            self.text.delete("1.0", "end")
            self.text.insert("1.0", message)
            self.status_var.set(f"Decoded successfully (start={start}, LSBs={lsb}).")
        except Exception as e:
            self.status_var.set(f"Decoding failed: {e}")
            messagebox.showerror("Decoding failed", str(e))

if __name__ == "__main__":
    App().mainloop()
