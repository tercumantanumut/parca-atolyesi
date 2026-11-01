"""GPU worker: one long-lived process that runs the model steps (02 Şekil, 03 Doku, 04 Parçalar) and can keep their
pipelines loaded between jobs, so a second run skips the 15-20 s loads.

  python -I atolye/calis.py isci        (started and fed by the server; one JSON command per stdin line)

Commands: {"komut": "adim", "adim": "sekil", "argv": [...], "tut": true, "sonraki": ["doku", ...]},
{"komut": "bosalt"} (unload everything), {"komut": "durum"}. Each command's output ends with `@@bitti <code>`; in
between the step prints its usual protocol lines, plus `@@model <id> yuklendi <s> <GB>` / `@@model <id> bellekte <GB>`
/ `@@model <id> bosaltildi <reason>` and `@@bellek <json>` (what is loaded now).

Memory policy (plain LRU plus the measured needs in atolye/ihtiyac.py): before a step, if the free VRAM is less than
its model's need, kept models are unloaded, least recently used first, models a later step of this job still needs
last. With keeping off (`tut` false) a model is unloaded after its job's last step that needs it. Unloading frees the
model fully (gc + torch.cuda.empty_cache); reloading from disk is what keeping saves.
"""
from __future__ import annotations

import gc
import importlib
import json
import sys
import time
import traceback

from .ihtiyac import IHTIYAC_GB, PAY_GB
from .stages import _ortak as o

GiB = 2**30
ADIMLAR = {"sekil", "doku", "parcalar"}


def ihtiyac(ad: str) -> float:
    return IHTIYAC_GB.get(ad, IHTIYAC_GB.get(ad.split("_")[0], 8.0))


def _cpuya(nesne, derinlik: int = 0) -> str:
    """Move every torch module a pipeline holds to the CPU (diffusers pipelines, nn.Modules, plain objects and dicts
    of them, two levels deep). Returns a note when something could not be moved."""
    import torch

    if derinlik > 2 or nesne is None:
        return ""
    try:
        if isinstance(nesne, torch.nn.Module) or (hasattr(nesne, "to") and hasattr(nesne, "components")):
            nesne.to("cpu")
            return ""
    except Exception as e:  # pragma: no cover - best effort
        return f"taşınamadı: {type(nesne).__name__} ({e})"
    degerler = nesne.values() if isinstance(nesne, dict) else (vars(nesne).values() if hasattr(nesne, "__dict__") else [])
    notlar = [n for v in list(degerler) if (n := _cpuya(v, derinlik + 1))]
    return "; ".join(notlar)


class Bellek:
    def __init__(self):
        self.modeller: dict[str, dict] = {}  # id -> {"nesne", "gb", "son"}

    def _bos_gb(self) -> float:
        import torch

        bos, _ = o.kart_bos()  # the whole card (NVML): the other worker's models count too
        return (bos + torch.cuda.memory_reserved() - torch.cuda.memory_allocated()) / GiB

    def bosalt(self, ad: str, neden: str) -> None:
        import torch

        if ad not in self.modeller:
            return
        a0 = torch.cuda.memory_allocated()
        bekl = self.modeller[ad]["gb"]
        iz = _cpuya(self.modeller.pop(ad)["nesne"])  # tensors to CPU first: VRAM frees even if a reference lingers
        gc.collect()
        torch.cuda.empty_cache()
        bosalan = (a0 - torch.cuda.memory_allocated()) / GiB
        print(f"@@model {ad} bosaltildi {neden}", flush=True)
        print(f"model boşaltıldı: {ad} ({bosalan:.1f} / {bekl:.1f} GB geri verildi{', ' + iz if iz else ''})", flush=True)

    def bosalt_hepsi(self, neden: str = "istek") -> None:
        for ad in list(self.modeller):
            self.bosalt(ad, neden)

    def yer_ac(self, gerekli: list[str], sonraki: list[str]) -> None:
        """Unload kept models (LRU, later-needed last) until the step's model fits next to the rest."""
        lazim = sum(max(0.0, ihtiyac(a) - (self.modeller[a]["gb"] if a in self.modeller else 0.0)) for a in gerekli)
        lazim += PAY_GB
        adaylar = sorted((a for a in self.modeller if a not in gerekli),
                         key=lambda a: (a in sonraki, self.modeller[a]["son"]))
        for a in adaylar:
            if self._bos_gb() >= lazim:
                break
            self.bosalt(a, "yer_ac")

    def al(self, ad: str, yukleyici):
        import torch

        m = self.modeller.get(ad)
        if m is not None:
            m["son"] = time.time()
            print(f"@@model {ad} bellekte {m['gb']:.2f}", flush=True)
            print(f"model bellekte: {ad} ({m['gb']:.1f} GB), yükleme atlandı", flush=True)
            return m["nesne"]
        a0, t0 = torch.cuda.memory_allocated(), time.time()
        # No local name for the pipeline: libraries imported during the load can keep a traceback whose frame chain
        # reaches this frame, and a local here would then pin the model in VRAM after it is unloaded.
        self.modeller[ad] = {"nesne": yukleyici(), "gb": 0.0, "son": time.time()}
        self.modeller[ad]["gb"] = gb = max(0, torch.cuda.memory_allocated() - a0) / GiB
        sn = time.time() - t0
        print(f"@@model {ad} yuklendi {sn:.1f} {gb:.2f}", flush=True)
        print(f"model yüklendi: {ad} ({sn:.0f} sn, {gb:.1f} GB)", flush=True)
        return self.modeller[ad]["nesne"]

    def diger_bayt(self, gerekli: list[str]) -> int:
        return int(sum(m["gb"] for a, m in self.modeller.items() if a not in gerekli) * GiB)

    def durum(self) -> list[dict]:
        return [{"ad": a, "gb": round(m["gb"], 2), "son": round(m["son"], 1)}
                for a, m in sorted(self.modeller.items(), key=lambda x: -x[1]["son"])]


def adim(b: Bellek, k: dict) -> int:
    import torch

    ad = k["adim"]
    if ad not in ADIMLAR:
        print(f"bilinmeyen adım: {ad}", flush=True)
        return 2
    mod = importlib.import_module(f"atolye.stages.{ad}")
    a = mod.ayristir(k.get("argv", []))
    gerekli, sonraki = mod.gerekli_modeller(a), list(k.get("sonraki", []))
    try:
        for deneme in (1, 2):
            try:
                b.yer_ac(gerekli, sonraki)
                o.TABAN = b.diger_bayt(gerekli)
                st = mod.calistir(a, b.al)
                break
            except torch.OutOfMemoryError:
                if deneme == 2:
                    raise
                # One retry: free the other models this worker keeps AND lift the cap. If another app or the other
                # worker holds the VRAM, or the input is simply bigger than usual, Windows spills into shared memory:
                # slower, but the job finishes instead of failing.
                for m in [m for m in b.modeller if m not in gerekli]:
                    b.bosalt(m, "vram_yetmedi")
                print("VRAM yetmedi: adım sınırsız yeniden deneniyor (gerekirse Windows paylaşılan belleğe "
                      "taşır, yavaşlar)", flush=True)
                o.SINIRSIZ = True
                torch.cuda.set_per_process_memory_fraction(1.0)
                gc.collect()
                torch.cuda.empty_cache()
    finally:
        o.SINIRSIZ = False  # the next step gets its cap again
    st["bellek"] = {"tutuldu": bool(k.get("tut", True)), "diger_gb": round(o.TABAN / GiB, 2)}
    o.sonuc(st)
    torch.cuda.empty_cache()  # keep the weights, give back the step's cache
    if not k.get("tut", True):
        for m in gerekli:
            if m not in sonraki:
                b.bosalt(m, "tutma_kapali")
    return 0


def main(argv=None) -> None:
    b = Bellek()
    print("@@hazir", flush=True)
    for satir in sys.stdin:
        satir = satir.strip()
        if not satir:
            continue
        try:
            k = json.loads(satir)
        except ValueError:
            print("@@bitti 2", flush=True)
            continue
        kod = 0
        try:
            if k.get("komut") == "adim":
                with o.gpu_kilidi():
                    kod = adim(b, k)
            elif k.get("komut") == "bosalt":
                b.bosalt_hepsi(k.get("neden", "istek"))
            elif k.get("komut") == "dur":
                b.bosalt_hepsi("dur")
                print("@@bitti 0", flush=True)
                return
        except Exception as e:  # report and stay alive; the models that loaded stay usable
            traceback.print_exc()
            sys.stdout.flush()
            kod = 1
            if "out of memory" in str(e).lower():
                b.bosalt_hepsi("vram_yetmedi")
        print("@@bellek " + json.dumps(b.durum()), flush=True)
        print(f"@@bitti {kod}", flush=True)


if __name__ == "__main__":
    main()
