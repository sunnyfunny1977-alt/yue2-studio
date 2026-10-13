"""Audio mit ffmpeg dekodieren und Metadaten (Tags, Cover) mit ffprobe lesen – MP3, FLAC, WAV, M4A, OGG …"""
import base64
import json
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


# Tag-Namen verschiedener Formate (ID3, Vorbis, MP4) auf einheitliche Schlüssel abbilden.
_TAG_ALIASES = {
    "title": ("title",),
    "artist": ("artist", "performer"),
    "album": ("album",),
    "album_artist": ("album_artist", "albumartist", "album artist"),
    "year": ("date", "year", "originaldate", "tdrc", "tyer"),
    "genre": ("genre",),
    "track": ("track", "tracknumber"),
    "composer": ("composer",),
}


def read_tags(path):
    """Liest Titel, Interpret, Album usw. sowie technische Daten und ein eingebettetes Cover.

    Gibt ein Dict zurück; fehlende Felder fehlen einfach. Ohne ffprobe oder bei Fehlern: {}.
    """
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not path:
        return {}
    cmd = [ffprobe, "-v", "error", "-show_entries",
           "format=duration,bit_rate,format_name:format_tags:stream=index,codec_type,codec_name,sample_rate,"
           "channels,bit_rate:stream_tags:stream_disposition=attached_pic", "-of", "json", str(path)]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        return {}
    try:
        data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except ValueError:
        return {}
    fmt, streams = data.get("format", {}), data.get("streams", [])
    # Tags können am Container (MP3/FLAC/M4A) oder am Audio-Stream (OGG/Opus) hängen.
    raw = {}
    for stream in streams:
        if stream.get("codec_type") == "audio":
            raw.update({k.lower(): v for k, v in (stream.get("tags") or {}).items()})
    raw.update({k.lower(): v for k, v in (fmt.get("tags") or {}).items()})
    info = {}
    for key, aliases in _TAG_ALIASES.items():
        for alias in aliases:
            value = str(raw.get(alias, "")).strip()
            if value:
                info[key] = value
                break
    if "year" in info:
        info["year"] = info["year"][:4]
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    info["codec"] = (audio.get("codec_name") or fmt.get("format_name", "")).upper()
    if audio.get("sample_rate"):
        info["sample_rate"] = int(audio["sample_rate"])
    if audio.get("channels"):
        info["channels"] = int(audio["channels"])
    bitrate = audio.get("bit_rate") or fmt.get("bit_rate")
    if bitrate:
        info["bitrate_kbps"] = round(int(bitrate) / 1000)
    if fmt.get("duration"):
        info["duration"] = float(fmt["duration"])
    cover = next((s for s in streams if (s.get("disposition") or {}).get("attached_pic")), None)
    if cover is not None:
        info["cover"] = _read_cover(path, cover["index"])
        if not info["cover"]:
            info.pop("cover")
    return info


def _read_cover(path, stream_index):
    """Eingebettetes Cover als verkleinertes JPEG (data-URI) für die Anzeige."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return ""
    cmd = [ffmpeg, "-nostdin", "-v", "error", "-i", str(path), "-map", f"0:{stream_index}", "-frames:v", "1",
           "-vf", "scale=320:320:force_original_aspect_ratio=decrease", "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(proc.stdout).decode("ascii")
