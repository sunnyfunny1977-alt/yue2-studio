"""FLUX.3-Image-Klein-Worker für Cover (läuft in .venv-flux3, gesteuert von cover.py).

Protokoll: eine JSON-Zeile pro Auftrag auf stdin, Antworten als JSON-Zeilen auf stdout.
  {"cmd": "render", "prompt": ..., "seed": 1, "width": 1024, "height": 1024, "steps": 16, "out": "x.png"}
  → {"progress": i, "total": n} …, dann {"ok": true, "png": ..., "seconds": ...} oder {"error": ...}
  {"cmd": "quit"}
Alles andere (Ladefortschritt, Warnungen) geht nach stderr.
"""
import json
import os
import sys
import time
import traceback
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # Windows-Konsole: sonst cp1252
    except (AttributeError, ValueError):
        pass
PROTO = sys.stdout
sys.stdout = sys.stderr  # Bibliotheken dürfen das Protokoll nicht stören


def send(**msg):
    PROTO.write(json.dumps(msg, ensure_ascii=False) + "\n")
    PROTO.flush()


class Flux:
    def __init__(self, model_dir, variant, low_vram):
        self.model_dir, self.variant, self.low_vram = Path(model_dir), variant, low_vram
        self.pipe, self.calls = None, 0

    def _patch_fp8(self, torch):
        """Ohne zeilenweise skaliertes fp8-GEMM (z. B. RTX 50 mit CUDA 12.8, AMD) würde der BFL-Linear-Layer
        abstürzen, weil er nur die Compute Capability prüft. Dann rechnet er das Gewicht pro Schritt nach bf16
        zurück – gleiches Ergebnis, etwas langsamer, VRAM bleibt beim fp8-Bedarf."""
        try:
            a = torch.randn(16, 32, device="cuda").to(torch.float8_e4m3fn)
            torch._scaled_mm(a, a.T, torch.ones(16, 1, device="cuda"), torch.ones(1, 16, device="cuda"),
                             out_dtype=torch.bfloat16)
            return "fp8"
        except (RuntimeError, TypeError, AttributeError):
            import diffusers.quantizers.bfl.utils as bfl

            def forward(layer, inputs):
                weight = bfl.dequantize_fp8r(layer.weight, layer.weight_scale).to(layer.compute_dtype)
                return torch.nn.functional.linear(inputs, weight, layer.bias)

            bfl.BFLFP8RLinear.forward = forward
            return "fp8→bf16"

    def load(self):
        if self.pipe is not None:
            return
        import torch
        from diffusers import AutoencoderKLFlux2, BFLQuantizationConfig, Flux3Transformer2DModel
        from diffusers.modular_pipelines.flux3.modular_blocks_flux3_distilled import Flux3DistilledAutoBlocks
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

        start = time.time()
        bf16, m = torch.bfloat16, self.model_dir
        blocks = Flux3DistilledAutoBlocks()
        # Den Prompt-Upsampler (Qwen3.5-9B) übernimmt Ollama in der App – hier den fertigen Prompt direkt kodieren.
        blocks.sub_blocks.pop("prompt_upsampler")
        manager = None
        if self.low_vram:
            from diffusers import ComponentsManager
            manager = ComponentsManager()
            manager.enable_auto_cpu_offload(device="cuda")
        pipe = blocks.init_pipeline(components_manager=manager) if manager else blocks.init_pipeline()
        # Die Komponenten kommen aus dem lokalen Download; die Indexdatei des Repos verweist auf das (gated) BFL-Repo.
        components = {
            "text_encoder": Qwen3VLForConditionalGeneration.from_pretrained(m / "text_encoder", dtype=bf16),
            "tokenizer": AutoProcessor.from_pretrained(m / "text_encoder"),
            "vae": AutoencoderKLFlux2.from_pretrained(m / "vae", dtype=bf16),
        }
        mode = "bf16"
        if self.variant == "fp8r":
            mode = self._patch_fp8(torch)
            components["transformer"] = Flux3Transformer2DModel.from_single_file(
                str(m / "variants" / "fp8r" / "model.safetensors"), config=str(m), subfolder="transformer",
                quantization_config=BFLQuantizationConfig(compute_dtype=bf16), dtype=bf16)
        else:
            components["transformer"] = Flux3Transformer2DModel.from_pretrained(m / "transformer", dtype=bf16)
        # Fortschritt: ein Transformer-Durchlauf je Schritt (Distilled ohne CFG). Ein Hook statt eines Wrappers,
        # weil die Pipeline die Signatur von forward() auswertet.
        def count(_module, _inputs):
            self.calls += 1
            send(progress=self.calls, total=self.total)

        components["transformer"].register_forward_pre_hook(count)
        pipe.update_components(**components)
        self.pipe, self.mode = pipe, mode
        print(f"[flux] geladen in {time.time() - start:.1f} s ({self.variant}, {mode}, low_vram={self.low_vram})",
              file=sys.stderr, flush=True)

    def render(self, job):
        import torch
        self.total, self.calls = int(job.get("steps", 16)), 0
        self.load()
        if not self.low_vram:
            self.pipe.to("cuda")
        start = time.time()
        image = self.pipe(prompt=job["prompt"], height=int(job.get("height", 1024)), width=int(job.get("width", 1024)),
                          num_inference_steps=self.total,
                          generator=torch.Generator().manual_seed(int(job.get("seed", 0))), output="images")[0]
        image.save(job["out"])
        seconds = time.time() - start
        # VRAM sofort freigeben: Modelle bleiben im RAM, der nächste Auftrag lädt nur noch auf die GPU.
        if not self.low_vram:
            self.pipe.to("cpu")
        torch.cuda.empty_cache()
        return {"ok": True, "png": job["out"], "seconds": round(seconds, 1), "mode": self.mode}


def selftest(model_dir, variant):
    """Für install_cover.ps1: Modell laden und ein kleines Bild in 4 Schritten rendern."""
    import tempfile
    global send
    send = lambda **_msg: None  # noqa: E731 – Fortschrittszeilen im Installer nicht anzeigen
    flux = Flux(model_dir, variant, low_vram=False)
    out = Path(tempfile.gettempdir()) / "yue2_flux_selftest.png"
    result = flux.render({"prompt": 'A red apple on a wooden table, the word "OK" painted on the wall.',
                          "seed": 1, "width": 256, "height": 256, "steps": 4, "out": str(out)})
    print(f"FLUX.3 Selbsttest OK ({result['seconds']} s, {result['mode']}) -> {out}", file=PROTO, flush=True)


def main():
    if "--selftest" in sys.argv:
        args = sys.argv[sys.argv.index("--selftest") + 1:]
        selftest(args[0], args[1] if len(args) > 1 else "fp8r")
        return
    flux = Flux(os.environ["FLUX_MODEL_DIR"], os.environ.get("FLUX_VARIANT", "fp8r"),
                os.environ.get("FLUX_LOW_VRAM") == "1")
    send(ready=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
            if job.get("cmd") == "quit":
                break
            send(**flux.render(job))
        except Exception as e:  # noqa: BLE001 – jede Fehlermeldung an die App melden, Worker läuft weiter
            traceback.print_exc()
            send(error=f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
