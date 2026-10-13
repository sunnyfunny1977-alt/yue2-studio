"""Speichert einen generierten Song als MP3 oder FLAC plus Info-Textdatei (in der Oberflächensprache)."""
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from i18n import t
from lyrics_tools import fmt_duration, sanitize_filename

FORMATS = {"MP3": ".mp3", "FLAC": ".flac"}
LABEL_WIDTH = 18


def _write_mp3(audio, sr, target):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(t("err.ffmpeg_missing"))
    pcm = np.clip(audio, -1, 1)
    pcm = (pcm * 32767).astype("<i2")
    channels = 1 if pcm.ndim == 1 else pcm.shape[1]
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(sr), "-ac", str(channels),
           "-i", "pipe:0", "-codec:a", "libmp3lame", "-b:a", "320k", str(target)]
    proc = subprocess.run(cmd, input=pcm.tobytes(), capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(t("err.mp3_failed", e=proc.stderr.decode(errors="replace")))


def _row(key, value):
    return f"{t(key) + ':':<{LABEL_WIDTH}}{value}"


def _describe_source(tags):
    """„Titel – Interpret (Album, Jahr, Genre)“ aus den Tags des Original-Songs."""
    head = " – ".join(x for x in (tags.get("title"), tags.get("artist") or tags.get("album_artist")) if x)
    extra = ", ".join(x for x in (tags.get("album"), tags.get("year"), tags.get("genre")) if x)
    text = f"{head} ({extra})" if head and extra else head or extra
    return text or "-"


def build_info_text(info, audio_files, seconds):
    mode = info.get("mode", "new")
    cfg = info.get("cfg_scale")
    cfg_text = t("txt.cfg_default", v=info.get("cfg_default", "")) if cfg is None else cfg
    truncated = ", ".join(f"{t('trunc.' + k)}: {t('txt.yes') if v else t('txt.no')}"
                          for k, v in (info.get("truncated") or {}).items())
    formats = " | ".join(t("txt.fmt_mp3") if f.suffix.lower() == ".mp3" else t("txt.fmt_flac") for f in audio_files)
    lines = [
        _row("txt.title", info.get("title", "")),
        _row("txt.files", ", ".join(f.name for f in audio_files)),
        _row("txt.saved", f"{datetime.now():%Y-%m-%d %H:%M:%S}"),
        _row("txt.created", info.get("created", "")),
        _row("txt.mode", t("mode.remake_plain") if mode == "remake" else t("mode.new_plain")),
        _row("txt.length", f"{fmt_duration(seconds)} min ({seconds:.1f} s)"),
        _row("txt.format", formats),
        "",
        t("txt.sec_gen"),
        _row("txt.model", info.get("model", "")),
        _row("txt.vae", info.get("vae", "")),
        _row("txt.cot", info.get("cot", "")),
        _row("txt.seed", info.get("seed", "")),
        _row("txt.cfg", cfg_text),
        _row("txt.max_tokens", f"{info.get('max_tokens', '')} (≈ {int(info.get('max_tokens', 0)) // 25} s)"),
        _row("txt.truncated", truncated),
        _row("txt.render", f"{info.get('gen_seconds', 0):.0f} s"),
        _row("txt.gpu", (info.get("gpu") or "-") + (f" · {t('txt.lowvram')}" if info.get("low_vram") else "")),
        "",
        t("txt.sec_llm"),
        _row("txt.llm", info.get("llm_model", "")),
        _row("txt.language", info.get("language", "")),
        t("txt.idea"),
        info.get("idea", "") or "-",
        "",
        t("txt.sec_style"),
        info.get("style", ""),
        "",
        t("txt.sec_lyrics"),
        info.get("lyrics", ""),
    ]
    if mode == "remake":
        lm = info.get("lyrics_mode")
        lines += ["", t("txt.sec_source"),
                  _row("txt.source", info.get("source_file", "")),
                  _row("txt.original", _describe_source(info.get("source_tags") or {})),
                  _row("txt.lyrics_mode", t(f"lm.{lm}") if lm else ""),
                  "", t("txt.transcript"), info.get("transcript", "") or "-",
                  "", t("txt.abc_used"), info.get("abc", "") or "-"]
    elif info.get("abc"):
        lines += ["", t("txt.abc_planned"), info["abc"]]
    return "\n".join(lines) + "\n"


def save_song(audio, sr, name, fmt, out_dir, info, overwrite=False):
    """Schreibt <Name>.<mp3|flac> und <Name>.txt. Gibt beide Pfade zurück."""
    if fmt not in FORMATS:
        raise ValueError(f"Unknown format: {fmt}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = sanitize_filename(name)
    audio_file = out_dir / f"{stem}{FORMATS[fmt]}"
    text_file = out_dir / f"{stem}.txt"
    if not overwrite:
        existing = [audio_file.name] if audio_file.exists() else []
        # Die TXT darf ersetzt werden, wenn sie zum selben Song gehört (z. B. erst MP3, dann FLAC).
        # Erkannt am Erstellungszeitpunkt – unabhängig von der Sprache der vorhandenen TXT.
        created = info.get("created", "")
        if text_file.exists() and not (created and created in text_file.read_text(encoding="utf-8", errors="replace")):
            existing.append(text_file.name)
        if existing:
            raise FileExistsError(t("err.exists", files=", ".join(existing)))
    if fmt == "FLAC":
        sf.write(audio_file, audio, sr, subtype="PCM_24")
    else:
        _write_mp3(audio, sr, audio_file)
    seconds = len(audio) / sr
    audio_files = [out_dir / f"{stem}{ext}" for ext in FORMATS.values() if (out_dir / f"{stem}{ext}").exists()]
    text_file.write_text(build_info_text(info, audio_files, seconds), encoding="utf-8")
    return audio_file, text_file
