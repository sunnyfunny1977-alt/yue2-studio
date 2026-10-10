"""YuE2-Pipeline-Wrapper: lazy laden, stufenweise generieren, Fortschritt und Abbruch."""
import threading
import time
from dataclasses import dataclass, field

from i18n import t
from settings import CONFIG

SAMPLE_RATE = 48000
TOKENS_PER_SECOND = 25


# Phasen der Generierung: (Schlüssel, Anzeigename, Start-%, End-%)
PHASES = [("load", "Laden", 0, 5), ("plan", "Partitur", 5, 20), ("semantic", "Song", 20, 82),
          ("synth", "Synthese", 82, 95), ("decode", "Decode", 95, 100)]
TYPICAL_ABC_TOKENS = 700


@dataclass
class Progress:
    stage: str = "start"  # Text-ID, übersetzt in ui_theme (i18n-Schlüssel stage.<id>)
    key: str = "idle"
    abc_tokens: int = 0
    semantic_tokens: int = 0
    max_tokens: int = 0
    expected_tokens: int = 0
    started: float = field(default_factory=time.time)

    def set(self, key, stage):
        self.key, self.stage = key, stage

    @property
    def elapsed(self):
        return time.time() - self.started

    @property
    def percent(self):
        """Grobe Gesamt-Prozentzahl; die Song-Phase wird an der aus den Lyrics erwarteten Länge gemessen."""
        if self.key == "done":
            return 100.0
        for key, _, lo, hi in PHASES:
            if key != self.key:
                continue
            if key == "plan":
                frac = min(self.abc_tokens / TYPICAL_ABC_TOKENS, 0.95)
            elif key == "semantic":
                frac = min(self.semantic_tokens / max(self.expected_tokens or self.max_tokens, 1), 0.98)
            else:
                frac = 0.0
            return lo + (hi - lo) * frac
        return 0.0

    def text(self):
        """Einzeilige Zusammenfassung (Logs/Diagnose)."""
        parts = [f"⏳ {t('stage.' + self.stage)}"]
        if self.abc_tokens:
            parts.append(t("prog.score", n=self.abc_tokens))
        if self.semantic_tokens:
            parts.append(t("prog.music", s=f"{self.semantic_tokens / TOKENS_PER_SECOND:.0f}"))
        parts.append(f"{self.elapsed:.0f} s")
        return " · ".join(parts)


class Cancelled(Exception):
    pass


def _patch_graph_attention():
    """Windows-Builds von PyTorch registrieren den Flash-Attention-Operator, enthalten ihn aber nicht
    („USE_FLASH_ATTENTION was not enabled for build“). YuE2s CUDA-Graph-Decoder wählt bei „auto“
    trotzdem Flash – dort stattdessen cuDNN (bzw. den Wert aus config.json) verwenden."""
    import sys
    choice = CONFIG.get("yue2_attention", "auto")
    if choice == "auto":
        if sys.platform != "win32":
            return
        choice = "cudnn"
    import yue2.cuda_graph as cuda_graph
    original = cuda_graph.GraphAR.__init__
    if getattr(original, "_yue2_app_patched", False):
        return

    def __init__(self, *args, attention_backend="auto", **kwargs):
        if attention_backend == "auto":
            attention_backend = choice
        original(self, *args, attention_backend=attention_backend, **kwargs)

    __init__._yue2_app_patched = True
    cuda_graph.GraphAR.__init__ = __init__


class YuE2Engine:
    def __init__(self):
        self._pipe = None
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self.progress = Progress()

    @property
    def loaded(self):
        return self._pipe is not None

    def load(self):
        if self._pipe is None:
            from yue2 import YuE2Pipeline
            _patch_graph_attention()
            self.progress.set("load", "load_model")
            self._pipe = YuE2Pipeline.from_pretrained(
                CONFIG["yue2_model"], vae=CONFIG["yue2_vae"], device="cuda",
                memory_budget_gib=CONFIG["yue2_memory_budget_gib"], backend=CONFIG["yue2_backend"],
            )
        return self._pipe

    def unload(self):
        """Gibt YuE2 frei. Liefert False, wenn gerade generiert wird."""
        if not self._lock.acquire(blocking=False):
            return False
        try:
            if self._pipe is not None:
                self._pipe.close()
                self._pipe = None
            import gc
            gc.collect()
            return True
        finally:
            self._lock.release()

    def cancel(self):
        self._cancel.set()

    def _on_token(self, phase, _token):
        if self._cancel.is_set():
            return
        if phase == "abc":
            self.progress.abc_tokens += 1
        else:
            self.progress.semantic_tokens += 1

    def generate(self, style, lyrics, *, cot="full", seed=0, abc=None, cfg_scale=None, max_seconds=360,
                 expected_seconds=None):
        """Erzeugt einen Song. Rückgabe: (audio[samples, 2] float32, meta-dict)."""
        import torch
        if not self._lock.acquire(blocking=False):
            raise RuntimeError(t("err.engine_busy"))
        self._cancel.clear()
        max_tokens = int(max_seconds * TOKENS_PER_SECOND)
        self.progress = Progress(max_tokens=max_tokens,
                                 expected_tokens=int((expected_seconds or 0) * TOKENS_PER_SECOND))
        self.progress.set("load", "start")
        cancelled = self._cancel.is_set
        try:
            pipe = self.load()
            request = pipe._request(style, lyrics, cot=cot, seed=int(seed), abc=abc or None,
                                    cfg_scale=cfg_scale, id="song")
            start = time.perf_counter()
            self.progress.set("plan", "plan" if cot != "off" and not abc else "prepare")
            plan = pipe.plan(request=request, cancelled=cancelled, on_token=self._on_token)
            if cancelled():
                raise Cancelled()
            # Prefix (Text + Partitur) und Song-Tokens teilen sich den Kontext von 24576 Tokens.
            from yue2.protocol import CONTEXT
            max_tokens = max(1, min(max_tokens, CONTEXT - len(plan.prefix) - 1))
            self.progress.max_tokens = max_tokens
            semantic_sampling = {"max_tokens": max_tokens, "min_tokens": min(200, max_tokens)}
            self.progress.set("semantic", "semantic")
            semantic = pipe.generate_semantic(plan, sampling=semantic_sampling,
                                              cancelled=cancelled, on_token=self._on_token)
            if cancelled():
                raise Cancelled()
            self.progress.set("synth", "synth")
            latents = pipe.synthesize(semantic, cancelled=cancelled)
            if cancelled():
                raise Cancelled()
            self.progress.set("decode", "decode")
            audio = pipe.decode(latents)
            gen_seconds = time.perf_counter() - start
            meta = {
                "model": CONFIG["yue2_model"], "vae": CONFIG["yue2_vae"],
                "cot": cot, "seed": int(seed),
                "cfg_scale": cfg_scale, "cfg_default": request.guidance,
                "max_tokens": max_tokens,
                "truncated": {"score": plan.truncated, "song": semantic.truncated},
                "abc": plan.abc,
                "gen_seconds": gen_seconds,
                "duration": len(audio) / SAMPLE_RATE,
            }
            self.progress.set("done", "done")
            return audio, meta
        except (Cancelled, InterruptedError):
            self.progress.set("cancel", "cancel")
            raise Cancelled()
        except torch.cuda.OutOfMemoryError as e:
            self.progress.set("error", "error")
            torch.cuda.empty_cache()
            raise RuntimeError(t("err.oom")) from e
        finally:
            self._lock.release()


ENGINE = YuE2Engine()
