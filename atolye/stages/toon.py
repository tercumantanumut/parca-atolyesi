"""Step 07 (Toon): cel-shaded still from Blender, headless (blender/toon_still.py does the work; ~1-3 s plus Blender start).

  python -I atolye/calis.py toon --girdi <is>/textured.glb --cikti <is>/toon_ucceyrek.png --aci ucceyrek
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from ..ayar import KOK, yukle

BETIK = KOK / "blender" / "toon_still.py"
ACILAR = ("on", "ucceyrek", "yan")


def render(blender: Path, girdiler: list[Path], cikti: Path, aci: str, boyut: int = 1024, cizgi: float = 1.0,
           zaman_asimi: int = 600) -> dict:
    if aci not in ACILAR:
        raise ValueError(f"aci must be one of {ACILAR}")
    if not blender or not Path(blender).exists():
        raise FileNotFoundError("Blender bulunamadı (atolye.toml [yollar] blender)")
    cmd = [str(blender), "-b", "--factory-startup", "-noaudio", "-P", str(BETIK), "--"]
    for g in girdiler:
        cmd += ["--girdi", str(g)]
    cmd += ["--cikti", str(cikti), "--aci", aci, "--boyut", str(boyut), "--cizgi", str(cizgi)]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=zaman_asimi)
    sonuc = None
    for satir in p.stdout.splitlines():
        if satir.startswith("@@sonuc "):
            sonuc = json.loads(satir[8:])
    if p.returncode != 0 or sonuc is None or not Path(cikti).exists():
        kuyruk = "\n".join((p.stdout + p.stderr).strip().splitlines()[-15:])
        raise RuntimeError(f"Blender toon render failed ({p.returncode}):\n{kuyruk}")
    sonuc["toplam_sn"] = round(time.time() - t0, 2)
    return sonuc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="toon")
    ap.add_argument("--girdi", required=True, action="append")
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--aci", choices=ACILAR, default="ucceyrek")
    ap.add_argument("--boyut", type=int, default=1024)
    ap.add_argument("--cizgi", type=float, default=1.0)
    a = ap.parse_args(argv)
    s = render(yukle().blender, [Path(g) for g in a.girdi], Path(a.cikti), a.aci, a.boyut, a.cizgi)
    print("@@sonuc " + json.dumps(s))


if __name__ == "__main__":
    sys.exit(main())
