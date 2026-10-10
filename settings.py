"""Lädt config.json und löst relative Pfade gegen den Projektordner auf."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROMPTS = ROOT / "prompts"

with (ROOT / "config.json").open(encoding="utf-8") as f:
    CONFIG = json.load(f)


def path(key):
    """Pfad aus der Konfiguration; relative Angaben gelten ab dem Projektordner."""
    p = Path(CONFIG[key])
    return p if p.is_absolute() else ROOT / p


def prompt(name):
    return (PROMPTS / name).read_text(encoding="utf-8")


# Persönliche Einstellungen (z. B. Oberflächensprache) – werden von der App selbst geschrieben.
USER_FILE = ROOT / "user_settings.json"


def load_user():
    try:
        return json.loads(USER_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_user(**values):
    data = {**load_user(), **values}
    USER_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
