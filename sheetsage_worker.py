"""Läuft in .venv-sheetsage2: transkribiert die Melodie eines Songs zu ABC (ohne Akkorde).

Aufruf: python sheetsage_worker.py <audio> <output_dir> <model_dir>
Letzte stdout-Zeile: JSON {"abc": ..., "warnings": [...]} oder {"error": ...}
"""
import json
import sys
from pathlib import Path

from audio_utils import load_mono

SR = 24000


def sync_remote_code(model_dir):
    """Transformers kopiert bei trust_remote_code nur importierte Module in den Modul-Cache.
    SheetSage2 liest weitere Quelldateien per Pfad – daher alle .py-Dateien spiegeln."""
    import shutil
    from transformers.utils import HF_MODULES_CACHE

    src = Path(model_dir)
    dst = Path(HF_MODULES_CACHE) / "transformers_modules" / src.name
    dst.mkdir(parents=True, exist_ok=True)
    for py in src.glob("*.py"):
        target = dst / py.name
        if not target.exists() or target.read_bytes() != py.read_bytes():
            shutil.copy2(py, target)


def main():
    audio_path, output_dir, model_dir = sys.argv[1:4]
    try:
        import torch
        from transformers import AutoModel

        # Selbst dekodieren und als Array übergeben: umgeht torchaudios FFmpeg-Shared-Libs unter Windows.
        audio = load_mono(audio_path, SR)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        sync_remote_code(model_dir)
        model = AutoModel.from_pretrained(model_dir, trust_remote_code=True).eval().to(device)
        result = model.transcribe(
            audio, sampling_rate=SR, output_dir=output_dir,
            prompts=("timestamp", "downbeat_meter", "structure", "key", "melody_full"),
            dtype="bf16" if device == "cuda" else "fp32", melody_only=True,
        )
        abc = result.get("abc")
        if result.get("abc_error") or not abc:
            raise RuntimeError(f"Keine verwendbare Melodie-Partitur: {result.get('abc_error')}")
        out = {"abc": abc, "warnings": [str(w) for w in result.get("warnings", [])]}
    except Exception as exc:  # Fehler als JSON an die App melden
        partial = getattr(exc, "result", None) or {}
        out = {"error": f"{type(exc).__name__}: {exc}",
               "warnings": [str(w) for w in partial.get("warnings", [])]}
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if "abc" in out else 2


if __name__ == "__main__":
    sys.exit(main())
