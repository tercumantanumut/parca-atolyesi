"""Step 02 (Şekil; 01 is the input image): image -> untextured mesh. Hunyuan3D-2.1 from one image, or Hunyuan3D-2mv from front + back.

  python -I atolye/calis.py sekil --on on.png [--arka arka.png] --cikti <is> [--tohum 1234] [--octree 384]

Writes input_rgba.png (the cut-out the models see; also the paint reference), shape.glb (Y up, front +Z) and
sekil.json (timings, peak VRAM, face count). Measured on an RTX 5090: 2.1 loads in ~20 s, runs ~34 s, working set ~7.6 GB.
Inside the server the step runs in the GPU worker (atolye/isci.py), which may keep the pipeline loaded between jobs.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import _ortak as o


def ayristir(argv=None):
    ap = argparse.ArgumentParser(prog="sekil")
    ap.add_argument("--on", required=True, help="front image (the shape condition and the paint style)")
    ap.add_argument("--arka", help="back image: uses Hunyuan3D-2mv (front + back) for the shape")
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--arkaplan", choices=["auto", "flood", "rembg", "none"], default="auto")
    ap.add_argument("--adim", type=int, default=50)
    ap.add_argument("--guidance", type=float, default=5.0)
    ap.add_argument("--octree", type=int, default=384)
    ap.add_argument("--tohum", type=int, default=1234)
    return ap.parse_args(argv)


def gerekli_modeller(a) -> list[str]:
    return ["sekil_2mv" if a.arka else "sekil_21"]


def yukle_21():
    from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline

    from .. import hy_ortam

    return Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(str(hy_ortam.M["hy21"]))


def yukle_2mv():
    from .. import hy_ortam

    hy_ortam.kur_2mv()
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

    return Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        str(hy_ortam.M["mv"]), subfolder="hunyuan3d-dit-v2-mv", variant="fp16", use_safetensors=True)


def calistir(a, al) -> dict:
    """al(model id, loader) -> pipeline (loads it, or returns the kept one)."""
    import torch

    from .. import hy_ortam

    hy_ortam.kur_hy21()
    out = Path(a.cikti).resolve()
    out.mkdir(parents=True, exist_ok=True)
    o.ilerleme(0.0)
    img, mod = o.arkaplan_temizle(Path(a.on), out / "input_rgba.png", a.arkaplan)
    print(f"arka plan: {mod}")
    st = {"arkaplan": mod, "tohum": a.tohum, "octree": a.octree, "adim": a.adim, "vram": o.vram_siniri()}
    arka = None
    if a.arka:
        arka, mod2 = o.arkaplan_temizle(Path(a.arka), out / "input_back_rgba.png", a.arkaplan)
        print(f"arka görsel, arka plan: {mod2}")
    o.faz(0.02, 0.25, "yukleniyor")
    t0 = time.time()
    pipe = al("sekil_2mv", yukle_2mv) if arka is not None else al("sekil_21", yukle_21)
    st["yukleme_sn"] = round(time.time() - t0, 1)
    o.faz(0.25, 0.95, "difuzyon")
    o.cubuk(0.25, 0.6, "Diffusion Sampling")
    o.cubuk(0.6, 0.95, "Volume Decoding")
    t = o.Tepe()
    if arka is not None:
        from hy3dgen.shapegen.postprocessors import DegenerateFaceRemover, FloaterRemover

        mesh = pipe(image={"front": img, "back": arka}, num_inference_steps=a.adim, octree_resolution=a.octree,
                    num_chunks=200000, guidance_scale=a.guidance, generator=torch.manual_seed(a.tohum),
                    output_type="trimesh")[0]
        mesh = DegenerateFaceRemover()(FloaterRemover()(mesh))
        st["model"] = "2mv"
    else:
        mesh = pipe(image=img, num_inference_steps=a.adim, guidance_scale=a.guidance, octree_resolution=a.octree,
                    generator=torch.manual_seed(a.tohum))[0]
        st["model"] = "2.1"
    st.update(calisma_sn=t.sn, tepe_vram_gb=t.gb, tepe_ayrilan_gb=t.ayrilan_gb)
    del pipe  # a frame kept alive by a library must not pin the (possibly kept) pipeline
    o.faz(0.95, 1.0, "yaziliyor")
    mesh.export(out / "shape.glb")
    st["yuz"] = int(len(mesh.faces))
    st["gpu"] = torch.cuda.get_device_name(0)
    (out / "sekil.json").write_text(json.dumps(st, indent=2), encoding="utf-8")
    print(f"şekil hazır: {st['yuz']} yüz, {st['calisma_sn']} sn, tepe {st['tepe_vram_gb']} GB")
    return st


def main(argv=None):
    a = ayristir(argv)
    with o.gpu_kilidi():
        st = calistir(a, o.dogrudan)
    o.sonuc(st)


if __name__ == "__main__":
    main()
