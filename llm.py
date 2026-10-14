"""Schlanker Ollama-Client (REST) für Lyrics- und Style-Generierung."""
import json
import re

import requests

from i18n import t
from settings import CONFIG

BASE = CONFIG["ollama_url"].rstrip("/")

SONG_SCHEMA = {
    "type": "object",
    "properties": {
        "concept": {"type": "string"},  # zuerst: das Modell plant den Song, bevor es Style und Lyrics schreibt
        "title": {"type": "string"},
        "language": {"type": "string"},
        "style": {"type": "string"},
        "lyrics": {"type": "string"},
    },
    "required": ["concept", "title", "language", "style", "lyrics"],
}


class OllamaError(RuntimeError):
    pass


def list_models():
    try:
        r = requests.get(f"{BASE}/api/tags", timeout=5)
        r.raise_for_status()
    except requests.RequestException as e:
        raise OllamaError(t("err.ollama_unreachable", url=BASE, e=e)) from e
    return sorted(m["name"] for m in r.json().get("models", []) if m.get("size", 0) > 0)


def _chat(payload):
    try:
        r = requests.post(f"{BASE}/api/chat", json=payload, timeout=900)
    except requests.RequestException as e:
        raise OllamaError(t("err.ollama_unreachable", url=BASE, e=e)) from e
    if r.status_code != 200:
        raise OllamaError(t("err.ollama_status", code=r.status_code, text=r.text[:500]))
    return r.json()["message"]["content"]


def _parse_json(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise OllamaError(t("err.bad_json", text=text[:800]))


def chat_json(model, system, user, schema=SONG_SCHEMA, temperature=None, think=False):
    """Chat mit erzwungenem JSON-Schema.

    think=True lässt Denkmodelle (z. B. Qwen) erst überlegen: deutlich bessere Reime und Struktur, aber etwa
    dreimal langsamer. Modelle ohne Denkmodus laufen unverändert (der Schalter wird dann weggelassen).
    """
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "format": schema,
        "stream": False,
        "think": bool(think),
        # Die Überlegungen belegen bis zu ~10 000 Tokens zusätzlich im Kontext.
        "options": {"temperature": CONFIG["ollama_temperature"] if temperature is None else temperature,
                    "num_ctx": 32768 if think else 16384},
    }
    try:
        content = _chat(payload)
    except OllamaError as e:
        if "think" not in str(e).lower():
            raise
        payload.pop("think")
        content = _chat(payload)
    data = _parse_json(content)
    return {k: str(data.get(k) or "").strip() for k in schema["properties"]}


def unload(model=None):
    """Entlädt ein (oder alle geladenen) Ollama-Modell(e) aus dem VRAM."""
    try:
        if model:
            names = [model]
        else:
            r = requests.get(f"{BASE}/api/ps", timeout=5)
            names = [m["name"] for m in r.json().get("models", [])]
        for name in names:
            requests.post(f"{BASE}/api/generate", json={"model": name, "keep_alive": 0}, timeout=60)
    except requests.RequestException:
        pass  # Ollama nicht erreichbar → belegt auch keinen VRAM
