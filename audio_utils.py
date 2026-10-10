"""Audio mit ffmpeg dekodieren (unterstützt MP3, FLAC, WAV, M4A, OGG …)."""
import shutil
import subprocess

import numpy as np

from i18n import t


def load_mono(path, sr):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(t("err.ffmpeg_missing"))
    cmd = [ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
           "-f", "f32le", "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(t("err.audio_read", e=proc.stderr.decode(errors="replace")[:300]))
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()
