"""Shared bits of the step processes: the line protocol the job runner reads, VRAM peaks, background removal.

Protocol (one line each, on stdout): `@@faz <a> <b>` maps the following tqdm percentages to step progress a..b,
`@@cubuk <a> <b> <label>` maps one named tqdm bar to a..b,
`@@ilerleme <0..1>` sets the progress, `@@sonuc <json>` is the step's result. Every other line is a log line.
"""
from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def faz(a: float, b: float, ad: str = "") -> None:
    print(f"@@faz {a:.3f} {b:.3f} {ad}", flush=True)


def cubuk(a: float, b: float, etiket: str) -> None:
    """Map the tqdm bar whose label starts with `etiket` to progress a..b (once any bar is announced,
    unannounced bars only go to the log)."""
    print(f"@@cubuk {a:.3f} {b:.3f} {etiket}", flush=True)


def ilerleme(x: float) -> None:
    print(f"@@ilerleme {x:.3f}", flush=True)


def sonuc(d: dict) -> None:
    print("@@sonuc " + json.dumps(d), flush=True)


SINIRSIZ = False  # set once a process decided to allow the spill: a cap cannot be lifted again in the same process


def kart_bos() -> tuple[int, int]:
    """(free, total) bytes of the whole card. Under Windows WDDM torch.cuda.mem_get_info() reports this process's
    budget and does not see what OTHER processes hold (e.g. the other GPU worker's kept models), so NVML first."""
    try:
        import pynvml

        pynvml.nvmlInit()
        m = pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(0))
        return int(m.free), int(m.total)
    except Exception:
        import torch

        return torch.cuda.mem_get_info()


def vram_siniri(ihtiyac_gb: float | None = None) -> dict:
    """Cap this process's CUDA allocator at the VRAM that is actually free (minus a margin).

    On Windows (WDDM) a CUDA allocation beyond the card does not fail: the driver silently spills into shared system
    memory and the step runs 20-50x slower. PyTorch's caching allocator also keeps freed blocks reserved, so a step
    whose working set is 13.5 GiB can hold 20 GiB. With a cap the allocator frees its cache and retries instead of
    growing, so the step stays inside the card; if the working set itself does not fit, it fails fast with an OOM
    instead of crawling. `[sinirlar] vram_tasma = true` in atolye.toml turns the cap off (allows the spill);
    `vram_siniri_gb` sets an explicit cap (e.g. to try a 16 GB card's limit on a bigger one). A step whose measured
    need (`ihtiyac_gb`) is larger than the free VRAM runs without a cap: slow, but it finishes (X-Part on 32 GB)."""
    import torch

    from ..ayar import yukle

    s = yukle().ham.get("sinirlar", {})
    bos, toplam = kart_bos()
    bos += torch.cuda.memory_reserved()  # what this process already holds (kept models, cache) is ours to use
    d = {"toplam_gb": round(toplam / 2**30, 2), "bos_gb": round(bos / 2**30, 2), "sinir_gb": None}
    global SINIRSIZ
    if s.get("vram_tasma") or SINIRSIZ:
        return d
    if ihtiyac_gb and ihtiyac_gb > d["bos_gb"] - 0.4:
        SINIRSIZ = True
        d["tasma"] = True
        print(f"Bu adım ~{ihtiyac_gb:.0f} GB ister, kartta boş {d['bos_gb']} GB: Windows paylaşılan belleğe taşar, "
              "adım yavaşlar", flush=True)
        return d
    sinir = float(s.get("vram_siniri_gb") or 0) * 2**30 or bos - 0.4 * 2**30
    oran = max(0.05, min(0.99, sinir / toplam))
    torch.cuda.set_per_process_memory_fraction(oran)
    d["sinir_gb"] = round(oran * toplam / 2**30, 2)
    print(f"VRAM sınırı: {d['sinir_gb']} GB (kartta boş {d['bos_gb']} / {d['toplam_gb']} GB)", flush=True)
    return d


def dogrudan(ad: str, yukleyici):
    """Model getter for a step started by hand: always loads (the worker passes a cache-aware one instead)."""
    return yukleyici()


# Bytes held by kept models this step does not use (set by the worker, atolye/isci.py): they are not the step's need.
TABAN = 0


class Tepe:
    """Peak VRAM of this step. `gb` = the peak working set (allocated tensors: what the step needs; with the cap
    from vram_siniri the allocator sheds its cache to stay near it), minus other kept models; `ayrilan_gb` = the
    peak the allocator reserved."""

    def __init__(self):
        import torch

        self.torch = torch
        torch.cuda.reset_peak_memory_stats()
        self.t0 = time.time()

    @property
    def gb(self) -> float:
        return round(max(0, self.torch.cuda.max_memory_allocated() - TABAN) / 2**30, 2)

    @property
    def ayrilan_gb(self) -> float:
        return round(self.torch.cuda.max_memory_reserved() / 2**30, 2)

    @property
    def sn(self) -> float:
        return round(time.time() - self.t0, 1)


@contextlib.contextmanager
def gpu_kilidi():
    """One GPU step at a time on this machine: the server's steps and any step started by hand take the same lock
    file (<veri>/gpu.kilit), so they wait for each other instead of fighting over VRAM."""
    from ..ayar import yukle

    yol = yukle().veri / "gpu.kilit"
    yol.parent.mkdir(parents=True, exist_ok=True)
    f = open(yol, "a+b")
    try:
        if os.name == "nt":
            import msvcrt

            f.seek(0)
            bekledi = False
            while True:
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if not bekledi:
                        print("GPU başka bir adımda, sıra bekleniyor", flush=True)
                        bekledi = True
                    time.sleep(1)
        else:
            import fcntl

            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                print("GPU başka bir adımda, sıra bekleniyor", flush=True)
                fcntl.flock(f, fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        f.close()


def arkaplan_sec(im: Image.Image) -> str:
    """auto: an image with real transparency needs nothing; a flat light border is flood-filled (keeps white clothes,
    which u2net tends to eat); anything else goes to rembg (u2net)."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        a = np.asarray(im.convert("RGBA"))[..., 3]
        if (a < 250).mean() > 0.01:
            return "none"
    rgb = np.asarray(im.convert("RGB")).astype(np.int16)
    kenar = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    acik = (kenar.min(1) > 200).mean()
    duz = kenar.std(0).max() < 18
    return "flood" if acik > 0.9 and duz else "rembg"


def kirp_ortala(rgba: Image.Image, pay: float = 0.08) -> Image.Image:
    """Crop to the subject and centre it on a square transparent canvas with a margin (what the shape model expects)."""
    a = np.asarray(rgba)[..., 3]
    ys, xs = np.nonzero(a > 8)
    if len(xs) == 0:
        raise ValueError("arka plan temizlendikten sonra görselde nesne kalmadı")
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    nes = rgba.crop((x0, y0, x1, y1))
    k = int(max(nes.size) * (1 + 2 * pay))
    tuval = Image.new("RGBA", (k, k), (0, 0, 0, 0))
    tuval.paste(nes, ((k - nes.width) // 2, (k - nes.height) // 2), nes)
    return tuval


def arkaplan_temizle(kaynak: Path, hedef: Path, mod: str = "auto") -> tuple[Image.Image, str]:
    im = Image.open(kaynak)
    im.load()
    if mod == "auto":
        mod = arkaplan_sec(im)
    if mod == "none":
        rgba = im.convert("RGBA")
    elif mod == "rembg":
        from hy3dshape.rembg import BackgroundRemover

        rgba = BackgroundRemover()(im.convert("RGB"))
    else:  # flood: near-white flood fill from the border
        rgb = im.convert("RGB")
        w, h = rgb.size
        pad = Image.new("RGB", (w + 2, h + 2), (255, 255, 255))
        pad.paste(rgb, (1, 1))
        sentinel = (255, 0, 255)
        ImageDraw.floodfill(pad, (0, 0), sentinel, thresh=40)
        bg = np.all(np.asarray(pad)[1:-1, 1:-1] == np.array(sentinel), axis=-1)
        rgba = Image.fromarray(np.dstack([np.asarray(rgb), np.where(bg, 0, 255).astype(np.uint8)]), "RGBA")
    rgba = kirp_ortala(rgba)
    rgba.save(hedef)
    return rgba, mod
