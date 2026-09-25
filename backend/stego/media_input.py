"""Decode uploaded covers to lossless carriers before embedding."""
import tempfile
import wave
from pathlib import Path

from . import audio_lsb, image_lsb, video_lsb

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}
AUDIO_EXTENSIONS = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac', '.aif', '.aiff'}


def normalise(data, kind, filename):
    extension = Path(filename or '').suffix.lower()
    if extension not in (IMAGE_EXTENSIONS if kind == 'image' else AUDIO_EXTENSIONS):
        raise ValueError('Choose a supported image or audio extension.')
    if kind == 'image':
        return image_lsb.carrier_to_png_bytes(image_lsb.load_image_carrier(data))
    try:
        audio_lsb.load_audio_carrier(data)
        return data
    except (ValueError, EOFError, wave.Error) as exc:
        wav_error = exc
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / ('source' + extension)
        target = Path(folder) / 'carrier.wav'
        source.write_bytes(data)
        try:
            video_lsb._run_ffmpeg(['-nostdin', '-i', str(source), '-map', '0:a:0', '-vn', '-c:a', 'pcm_s32le', str(target)])
        except video_lsb.VideoError as exc:
            if extension == '.wav' and isinstance(wav_error, ValueError):
                # Keep the WAV reader's specific explanation (not a WAV, cut off, ...).
                raise wav_error from exc
            raise ValueError('Cannot decode this audio file. Choose a valid supported audio file.') from exc
        return target.read_bytes()
