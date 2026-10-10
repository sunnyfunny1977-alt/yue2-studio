"""Startet die Melodie-Transkription (SheetSage2) in deren eigener venv."""
import json
import re
import subprocess
import tempfile

from i18n import t
from settings import ROOT, path


def transcribe_melody(audio_path):
    """Gibt (abc, warnings) zurück oder wirft RuntimeError mit verständlicher Meldung."""
    python, model = path("sheetsage_python"), path("sheetsage_model")
    if not python.exists():
        raise RuntimeError(t("err.sheetsage_env", p=python))
    if not (model / "config.json").exists():
        raise RuntimeError(t("err.sheetsage_model", p=model))
    out_dir = tempfile.mkdtemp(prefix="sheetsage_")
    proc = subprocess.run([str(python), str(ROOT / "sheetsage_worker.py"), str(audio_path), out_dir, str(model)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    result = None
    for line in reversed(proc.stdout.strip().splitlines()):
        if line.startswith("{"):
            try:
                result = json.loads(line)
                break
            except json.JSONDecodeError:
                pass
    if result is None:
        raise RuntimeError(t("err.sheetsage_noresult", code=proc.returncode, err=proc.stderr[-1500:]))
    if "error" in result:
        raise RuntimeError(t("err.melody_failed", e=result["error"]))
    return result["abc"], result.get("warnings", [])


def abc_header(abc):
    """Tempo-, Takt- und Tonart-Zeilen der Partitur als Hinweis für den Masterprompt."""
    keep = [line.strip() for line in (abc or "").splitlines() if re.match(r"^\s*[QMLK]:", line)]
    return " ".join(dict.fromkeys(keep))[:300]


def abc_sections(abc):
    """Sektionsfolge, die SheetSage2 als Kommentare (z. B. „% verse“) in die Partitur schreibt."""
    return [m.group(1).strip() for m in re.finditer(r"^%\s*([A-Za-z][\w -]*)$", abc or "", re.M)]
