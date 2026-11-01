"""GPU / VRAM probe: NVML when nvidia-ml-py is installed (fast enough for 2 polls a second), else nvidia-smi.

All sizes are GiB (2**30 bytes): a "32 GB" RTX 5090 reports 31.8.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time

GiB = 2**30


class GPU:
    def __init__(self):
        self._kilit = threading.Lock()
        self._nvml = None
        self._tutamak = None
        self._son: tuple[float, dict | None] = (0.0, None)
        try:
            import pynvml

            pynvml.nvmlInit()
            self._nvml = pynvml
            self._tutamak = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception:
            self._nvml = None

    def _smi(self) -> dict | None:
        exe = shutil.which("nvidia-smi")
        if not exe:
            return None
        try:
            out = subprocess.run([exe, "--query-gpu=name,memory.total,memory.used,memory.free,compute_cap",
                                  "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            ad, top, kul, bos, cc = [x.strip() for x in out.splitlines()[0].split(",")]
            mib = 2**20 / GiB
            return {"ad": ad, "toplam": float(top) * mib, "kullanilan": float(kul) * mib, "bos": float(bos) * mib,
                    "cc": cc}
        except Exception:
            return None

    def oku(self, en_fazla_yas: float = 0.3) -> dict | None:
        """{ad, toplam, kullanilan, bos} in GiB, or None without an NVIDIA GPU. Cached for en_fazla_yas seconds."""
        with self._kilit:
            t, d = self._son
            if d is not None and time.time() - t < en_fazla_yas:
                return d
            d = None
            if self._nvml is not None:
                try:
                    m = self._nvml.nvmlDeviceGetMemoryInfo(self._tutamak)
                    ad = self._nvml.nvmlDeviceGetName(self._tutamak)
                    ad = ad.decode() if isinstance(ad, bytes) else ad
                    d = {"ad": ad, "toplam": m.total / GiB, "kullanilan": m.used / GiB, "bos": m.free / GiB}
                except Exception:
                    d = None
            if d is None:
                d = self._smi()
            self._son = (time.time(), d)
            return d


class TepeOrnekleyici:
    """Samples the card's used VRAM while a step runs; tepe() = peak above the level when it started."""

    def __init__(self, gpu: GPU, aralik: float = 0.25):
        self.gpu, self.aralik = gpu, aralik
        d = gpu.oku(0)
        self.taban = d["kullanilan"] if d else 0.0
        self.en = self.taban
        self._dur = threading.Event()
        self._t = threading.Thread(target=self._dongu, daemon=True, name="vram")
        self._t.start()

    def _dongu(self):
        while not self._dur.wait(self.aralik):
            d = self.gpu.oku(0)
            if d:
                self.en = max(self.en, d["kullanilan"])

    def bitir(self) -> float:
        self._dur.set()
        self._t.join(timeout=2)
        return round(max(0.0, self.en - self.taban), 2)
