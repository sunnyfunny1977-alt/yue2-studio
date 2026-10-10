"""Transkribiert den Gesang eines Songs mit Whisper (für Remakes)."""
import gc

from audio_utils import load_mono
from settings import CONFIG


def transcribe(path):
    """Gibt den erkannten Text zeilenweise (eine Zeile je Whisper-Segment) zurück."""
    import torch
    from transformers import pipeline

    audio = load_mono(path, 16000)
    asr = pipeline("automatic-speech-recognition", model=CONFIG["whisper_model"],
                   dtype=torch.float16, device="cuda")
    try:
        result = asr({"raw": audio, "sampling_rate": 16000}, chunk_length_s=30, batch_size=8,
                     return_timestamps=True, generate_kwargs={"task": "transcribe"})
    finally:
        del asr
        gc.collect()
        torch.cuda.empty_cache()
    lines = [c["text"].strip() for c in result.get("chunks", []) if c.get("text", "").strip()]
    # Whisper halluziniert in Instrumentalpassagen gern Wiederholungen – direkte Dubletten > 3 kürzen.
    cleaned, run = [], 0
    for line in lines:
        run = run + 1 if cleaned and cleaned[-1] == line else 0
        if run < 3:
            cleaned.append(line)
    return "\n".join(cleaned) or result.get("text", "").strip()
