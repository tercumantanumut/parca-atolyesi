"""Stand-in for the GPU steps in tests: same arguments, same files, same line protocol, no model.

  python sahte_adim.py <adim> [args...]

sekil writes a small capsule figure as shape.glb, doku a textured copy, parcalar a labelled "P3-SAM" output, xpart
a few boxes. ayrik, toon and piksel are the real steps (they need no GPU). SAHTE_HATA=<adim> makes that step fail.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def figur():
    import numpy as np
    import trimesh

    parcalar = []
    for merkez, boyut in [((0, 0.75, 0), (0.25, 0.25, 0.25)), ((0, 0.3, 0), (0.4, 0.6, 0.2)),
                          ((-0.1, -0.35, 0), (0.12, 0.7, 0.12)), ((0.1, -0.35, 0), (0.12, 0.7, 0.12))]:
        b = trimesh.creation.box(extents=boyut)
        b.apply_translation(merkez)
        b = b.subdivide().subdivide()
        parcalar.append(b)
    m = trimesh.util.concatenate(parcalar)
    ids = np.concatenate([np.full(len(p.faces), i * 5 + 1) for i, p in enumerate(parcalar)])
    return m, ids


def main():
    adim, argv = sys.argv[1], sys.argv[2:]
    if os.environ.get("SAHTE_HATA") == adim:
        print("sahte hata", flush=True)
        sys.exit(3)
    if adim in ("ayrik", "toon", "piksel"):
        import importlib

        importlib.import_module(f"atolye.stages.{adim}").main(argv)
        return
    import numpy as np
    import trimesh
    from PIL import Image

    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", required=True)
    a, _ = ap.parse_known_args(argv)
    out = Path(a.cikti)
    out.mkdir(parents=True, exist_ok=True)
    print("@@faz 0.0 1.0 sahte", flush=True)
    for i in range(0, 101, 25):
        print(f"Sahte:  {i}%|####| {i}/100", end="\r", flush=True)
        time.sleep(0.02)
    print(flush=True)
    m, ids = figur()
    if adim == "sekil":
        Image.new("RGBA", (64, 64), (200, 100, 50, 255)).save(out / "input_rgba.png")
        m.export(out / "shape.glb")
    elif adim == "doku":
        uv = np.random.default_rng(0).random((len(m.vertices), 2))
        tex = Image.new("RGB", (64, 64), (180, 120, 60))
        m.visual = trimesh.visual.TextureVisuals(uv=uv, material=trimesh.visual.material.PBRMaterial(baseColorTexture=tex))
        m.export(out / "textured.glb")
    elif adim == "parcalar":
        m.export(out / "auto_mask_mesh_final.glb")
        np.save(out / "auto_mask_mesh_final_face_ids.npy", ids)
    elif adim == "xpart":
        (out / "parts").mkdir(exist_ok=True)
        m.export(out / "parts.glb")
        m.export(out / "parts_explode.glb")
        m.export(out / "parts" / "part_00.glb")
    print(f"sahte {adim} bitti", flush=True)
    print("@@sonuc " + json.dumps({"tepe_vram_gb": 1.5, "sahte": True}), flush=True)




def isci():
    """Stand-in for atolye/isci.py: the same stdin/stdout protocol, fake steps, a pretend model cache."""
    import json as _json
    import subprocess as _sp

    yuklu: dict[str, float] = {}
    print("@@hazir", flush=True)
    for satir in sys.stdin:
        k = _json.loads(satir)
        kod = 0
        if k.get("komut") == "adim":
            ad = {"sekil": "sekil_21", "doku": "doku", "parcalar": "p3sam"}[k["adim"]]
            if ad in yuklu:
                print(f"@@model {ad} bellekte 1.00", flush=True)
            else:
                yuklu[ad] = 1.0
                print(f"@@model {ad} yuklendi 0.1 1.00", flush=True)
            r = _sp.run([sys.executable, __file__, k["adim"], *k.get("argv", [])], capture_output=True, text=True,
                        encoding="utf-8")
            sys.stdout.write(r.stdout)
            sys.stdout.flush()
            kod = 0 if r.returncode == 0 else 1
            if not k.get("tut", True) and ad not in k.get("sonraki", []):
                yuklu.pop(ad, None)
                print(f"@@model {ad} bosaltildi tutma_kapali", flush=True)
        elif k.get("komut") == "bosalt":
            yuklu.clear()
        print("@@bellek " + _json.dumps([{"ad": a, "gb": g} for a, g in yuklu.items()]), flush=True)
        print(f"@@bitti {kod}", flush=True)


if __name__ == "__main__":
    isci() if sys.argv[1:2] == ["isci"] else main()
