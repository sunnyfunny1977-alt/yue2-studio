"""Systemauslastung für die Live-Anzeige: VRAM, GPU-Last, Leistungsaufnahme, CPU und RAM.

NVIDIA-Werte kommen über NVML (Paket nvidia-ml-py). Auf AMD/ohne NVML wird nur der VRAM über PyTorch
ermittelt; GPU-Last und Leistungsaufnahme bleiben leer (None).
"""
import json
import threading

import psutil

import gpu_info

_lock = threading.Lock()
_nvml_handle = None
_nvml_failed = False


def _nvml():
    """NVML-Handle der von PyTorch genutzten Karte (einmalig initialisiert) oder None."""
    global _nvml_handle, _nvml_failed
    if _nvml_handle is not None or _nvml_failed:
        return _nvml_handle
    with _lock:
        if _nvml_handle is None and not _nvml_failed:
            try:
                import pynvml
                pynvml.nvmlInit()
                count = pynvml.nvmlDeviceGetCount()
                handles = [pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(count)]
                name = gpu_info.current().name
                # NVML zählt nach PCI-Bus, CUDA ggf. anders – die Karte über den Namen zuordnen.
                match = [h for h in handles if pynvml.nvmlDeviceGetName(h) == name]
                _nvml_handle = (match or handles or [None])[0]
                _nvml_failed = _nvml_handle is None
            except Exception:
                _nvml_failed = True
    return _nvml_handle


def snapshot():
    """Aktuelle Werte als Dict. Fehlende Werte sind None."""
    data = {"vram_used": None, "vram_total": None, "gpu_util": None, "power": None, "power_limit": None,
            "cpu": psutil.cpu_percent(interval=None), "ram_used": None, "ram_total": None}
    mem = psutil.virtual_memory()
    data["ram_used"], data["ram_total"] = (mem.total - mem.available) / 2**30, mem.total / 2**30

    handle = _nvml()
    if handle is not None:
        import pynvml
        try:
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            data["vram_used"], data["vram_total"] = info.used / 2**30, info.total / 2**30
            data["gpu_util"] = float(pynvml.nvmlDeviceGetUtilizationRates(handle).gpu)
            data["power"] = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000
            data["power_limit"] = pynvml.nvmlDeviceGetEnforcedPowerLimit(handle) / 1000
        except Exception:
            pass
    elif gpu_info.current().vendor != "none":
        try:  # AMD/ROCm: belegter Grafikspeicher der ganzen Karte über PyTorch
            import torch
            free, total = torch.cuda.mem_get_info(0)
            data["vram_used"], data["vram_total"] = (total - free) / 2**30, total / 2**30
        except Exception:
            pass
    return data


def snapshot_json():
    return json.dumps({k: (round(v, 2) if isinstance(v, float) else v) for k, v in snapshot().items()})
