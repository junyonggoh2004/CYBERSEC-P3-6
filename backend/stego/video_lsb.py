"""
Video cover-object support (optional challenge, spec section 8: "Video cover
object ... audio-track embedding").

Rather than touching video frames (which would require a lossless video
codec and a much larger, more fragile pipeline), this hides the payload in
the video's **audio track** using the exact same, already-tested
bitstream/payload/audio_lsb code as a plain WAV cover:

  encode: video -> [ffmpeg: demux audio as PCM16 WAV] -> normal audio LSB
          embed -> [ffmpeg: remux stego WAV back with the original video
          stream copied bit-for-bit, no re-encode] -> stego video

  decode: stego video -> [ffmpeg: demux audio as PCM16 WAV] -> normal audio
          LSB extract/verify

Because the video stream is always stream-copied (`-c:v copy`), its pixels
are never touched or re-encoded, so visual quality is completely unaffected.
The trade-off (see README "Limitations"): the video must already have an
audio track, and the stego audio must stay lossless, so the output is MP4
with FLAC audio (browser-playable), or Matroska (.mkv) with raw PCM when the
video codec can't go in MP4. ffmpeg itself is not a system requirement - it ships as a portable
binary via the `imageio-ffmpeg` pip package.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg

_FFMPEG_TIMEOUT_SECONDS = 180


class VideoError(Exception):
    """User-facing error for anything ffmpeg-related (bad file, no audio track, timeout)."""


def ffmpeg_path() -> str:
    """Path to the portable ffmpeg binary bundled by imageio-ffmpeg - exposed
    for scripts/make_samples.py, which needs it to synthesize a test video."""
    return imageio_ffmpeg.get_ffmpeg_exe()


def _ffmpeg_path() -> str:
    return ffmpeg_path()


def _run_ffmpeg(args: list[str]) -> str:
    """Runs ffmpeg with the given args (excluding the executable itself),
    returns stderr text (ffmpeg logs everything to stderr), and raises
    VideoError on failure or timeout - never lets a hung/broken subprocess
    take the server down with it."""
    cmd = [_ffmpeg_path(), "-hide_banner", "-y", *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise VideoError(
            f"ffmpeg took too long (> {_FFMPEG_TIMEOUT_SECONDS}s) and was aborted - the file may be too large for this demo."
        ) from exc
    except OSError as exc:
        raise VideoError(f"Could not run the bundled ffmpeg binary: {exc}") from exc

    stderr_text = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise VideoError(f"ffmpeg failed: {_last_useful_line(stderr_text)}")
    return stderr_text


def _last_useful_line(stderr_text: str) -> str:
    lines = [l.strip() for l in stderr_text.splitlines() if l.strip()]
    return lines[-1] if lines else "(no ffmpeg output captured)"


def probe_has_audio_and_info(video_path: str) -> dict:
    """Cheap probe using `ffmpeg -i` (no ffprobe binary is bundled): ffmpeg
    always prints an input's stream summary to stderr, even when we don't
    give it a real job to do, so we parse that text with a few regexes."""
    cmd = [_ffmpeg_path(), "-hide_banner", "-i", video_path]
    proc = subprocess.run(cmd, capture_output=True, timeout=_FFMPEG_TIMEOUT_SECONDS)
    text = proc.stderr.decode("utf-8", errors="replace")

    has_audio = bool(re.search(r"Stream .* Audio:", text))
    has_video = bool(re.search(r"Stream .* Video:", text))
    duration_match = re.search(r"Duration:\s*([\d:.]+)", text)
    resolution_match = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", text)

    if not has_video:
        raise VideoError("Could not find a video stream in this file - is it really a video?")

    return {
        "has_audio": has_audio,
        "has_video": has_video,
        "duration": duration_match.group(1) if duration_match else None,
        "width": int(resolution_match.group(1)) if resolution_match else None,
        "height": int(resolution_match.group(2)) if resolution_match else None,
    }


def extract_audio_track(video_bytes: bytes) -> tuple[bytes, dict]:
    """Returns (pcm16_wav_bytes, video_info). Raises VideoError if the video
    has no audio track at all (nothing to embed into)."""
    with tempfile.TemporaryDirectory(prefix="stego_video_") as tmpdir:
        in_path = Path(tmpdir) / "input.bin"
        out_path = Path(tmpdir) / "audio.wav"
        in_path.write_bytes(video_bytes)

        info = probe_has_audio_and_info(str(in_path))
        if not info["has_audio"]:
            raise VideoError(
                "This video has no audio track to embed a payload into. Choose a video that "
                "includes audio, or use an image/audio cover instead."
            )

        _run_ffmpeg(["-i", str(in_path), "-vn", "-acodec", "pcm_s16le", "-ar", "44100", str(out_path)])
        return out_path.read_bytes(), info


def container_of(video_bytes: bytes) -> tuple[str, str]:
    """(extension, MIME type) of a stego video written by remux_with_new_audio."""
    if video_bytes[4:8] == b"ftyp":
        return "mp4", "video/mp4"
    return "mkv", "video/x-matroska"


def remux_with_new_audio(original_video_bytes: bytes, new_audio_wav_bytes: bytes) -> bytes:
    """Stream-copies the original video track (untouched, no quality loss)
    into a new container together with the new stego audio track, which must
    be stored losslessly so the embedded LSBs survive the container write.

    Preferred: MP4 with FLAC audio. FLAC is lossless (every 16-bit sample
    decodes back bit-for-bit) and browsers play H.264 + FLAC MP4 with sound,
    so the stego video can be previewed on the page. Fallback: Matroska (.mkv)
    with raw PCM, for video codecs the MP4 muxer rejects (e.g. VP8, ProRes).
    Never AAC/MP3: lossy codecs destroy the hidden bits.

    Deliberately does NOT pass `-shortest`: that flag trims both streams to
    the length of the shorter one, and video/audio durations from encoders
    like AAC often differ from the raw PCM sample count by a handful of
    frames (encoder priming/padding). Trimming would silently truncate the
    tail of our audio track - exactly where part of the embedded container
    could be - corrupting the payload. Keeping the full audio track intact
    is worth the (inaudible, sub-frame) duration mismatch this can leave
    between the two streams."""
    with tempfile.TemporaryDirectory(prefix="stego_video_") as tmpdir:
        video_path = Path(tmpdir) / "input.bin"
        audio_path = Path(tmpdir) / "stego_audio.wav"
        video_path.write_bytes(original_video_bytes)
        audio_path.write_bytes(new_audio_wav_bytes)
        inputs = ["-i", str(video_path), "-i", str(audio_path), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy"]

        mp4_path = Path(tmpdir) / "output.mp4"
        try:
            _run_ffmpeg([*inputs, "-c:a", "flac", "-movflags", "+faststart", str(mp4_path)])
            return mp4_path.read_bytes()
        except VideoError:
            pass  # video codec not allowed in MP4: fall back to MKV

        mkv_path = Path(tmpdir) / "output.mkv"
        _run_ffmpeg([*inputs, "-c:a", "pcm_s16le", str(mkv_path)])
        return mkv_path.read_bytes()
