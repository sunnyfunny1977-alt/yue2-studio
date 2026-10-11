"""Erkennt Grafikkarte (NVIDIA/CUDA oder AMD/ROCm), VRAM und ob der Sparmodus nötig ist."""
from dataclasses import dataclass
from functools import lru_cache

from settings import CONFIG

LOW_VRAM_GIB = 22  # darunter: Sparmodus (YuE2 ist für 24 GB ausgelegt)


@dataclass(frozen=True)
class GpuInfo:
    vendor: str        # "nvidia", "amd" oder "none"
    name: str
    vram_gib: float
    runtime: str       # "CUDA", "ROCm" oder ""

    @property
    def is_amd(self):
        return self.vendor == "amd"

    @property
    def low_vram(self):
        """Sparmodus aktiv? Steuerbar über config.json: yue2_low_vram = auto | on | off."""
        mode = CONFIG.get("yue2_low_vram", "auto")
        if mode == "on":
            return True
        if mode == "off":
            return False
        return self.vendor != "none" and self.vram_gib < LOW_VRAM_GIB

    @property
    def short_name(self):
        name = self.name
        for prefix in ("NVIDIA GeForce ", "NVIDIA ", "AMD Radeon ", "AMD "):
            if name.startswith(prefix):
                return name[len(prefix):]
        return name


def detect(torch_module=None):
    """Liest die erste GPU aus PyTorch. ROCm-Builds stellen AMD-GPUs über die CUDA-API bereit."""
    try:
        torch = torch_module
        if torch is None:
            import torch
        if not torch.cuda.is_available():
            return GpuInfo("none", "", 0.0, "")
        props = torch.cuda.get_device_properties(0)
        is_amd = bool(getattr(torch.version, "hip", None))
        return GpuInfo("amd" if is_amd else "nvidia", props.name, props.total_memory / 2**30,
                       "ROCm" if is_amd else "CUDA")
    except Exception:  # pragma: no cover - fehlendes/defektes torch
        return GpuInfo("none", "", 0.0, "")


@lru_cache(maxsize=1)
def current():
    return detect()
