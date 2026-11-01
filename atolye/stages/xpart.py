"""Step 06 (X-Part, optional): X-Part regenerates every part as a closed, standalone mesh (hidden surfaces filled in).

  python -I atolye/calis.py xpart --mesh <is>/shape.glb --cikti <is>/xpart [--octree 384]

It needs the part boxes of a merged P3-SAM run (fewer, larger parts), so it first runs P3-SAM with post-processing on
the mesh (~13 GB, freed before X-Part loads), then X-Part (~33-35 GB peak: a 40 GB+ card; on 32 GB it spills into
shared memory and slows down). The boxes come from our own P3-SAM run because the pipeline's built-in box predictor
hard-codes a prompt batch that needs ~100 GB of VRAM.

Writes xpart/parts.glb (one node per part), xpart/parts_explode.glb, xpart/bbox.glb, xpart/parts/part_XX.glb and
xpart/xpart.json. The parts are new geometry: no UVs or texture.
"""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path

import numpy as np

from . import _ortak as o
from . import parcalar


def _main(argv=None):
    ap = argparse.ArgumentParser(prog="xpart")
    ap.add_argument("--mesh", required=True)
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--aabb", help="[K,2,3] boxes; default: run P3-SAM with post-processing first")
    ap.add_argument("--adim", type=int, default=50)
    ap.add_argument("--octree", type=int, default=384, help="384: ~5 min, 32.7 GB; 512: ~7 min, 35.5 GB")
    ap.add_argument("--tohum", type=int, default=2026)
    ap.add_argument("--num-chunks", type=int, default=400000, help="marching-cubes query chunk; lower = less VRAM")
    a = ap.parse_args(argv)

    out = Path(a.cikti).resolve()
    (out / "parts").mkdir(parents=True, exist_ok=True)
    mesh = Path(a.mesh).resolve()
    st = {"octree": a.octree, "adim": a.adim, "num_chunks": a.num_chunks}
    from ..ihtiyac import IHTIYAC_GB

    # decide before the P3-SAM pre-run: once a cap is set in a process it cannot be lifted for X-Part
    st["vram"] = o.vram_siniri(IHTIYAC_GB["xpart"])
    if a.aabb:
        aabb_yolu = Path(a.aabb)
    else:
        o.faz(0.0, 0.08, "p3sam")
        p3 = parcalar.segment(mesh, out / "p3sam_post", birlestir=True)
        st["p3sam"] = p3
        aabb_yolu = out / "p3sam_post" / p3["aabb"]
        import torch

        gc.collect()
        torch.cuda.empty_cache()

    from .. import hy_ortam

    hy_ortam.kur_xpart()
    import torch
    from partgen.partformer_pipeline import PartFormerPipeline

    o.faz(0.08, 0.15, "yukleniyor")
    t = o.Tepe()
    pipe = PartFormerPipeline.from_pretrained(model_path=str(hy_ortam.M["part"]), verbose=True)
    pipe.to(device="cuda", dtype=torch.float32)
    st["yukleme_sn"] = t.sn
    aabb = np.load(aabb_yolu)
    st["kutu"] = int(len(aabb))
    o.faz(0.15, 0.97, "uretim")
    t = o.Tepe()
    obj_mesh, (out_bbox, _gt, explode) = pipe(
        mesh_path=str(mesh), aabb=aabb, num_inference_steps=a.adim, octree_resolution=a.octree, seed=a.tohum,
        num_chunks=a.num_chunks, output_type="trimesh")
    st.update(calisma_sn=t.sn, tepe_vram_gb=t.gb, tepe_ayrilan_gb=t.ayrilan_gb)
    obj_mesh.export(out / "parts.glb")
    out_bbox.export(out / "bbox.glb")
    explode.export(out / "parts_explode.glb")
    geoms = list(obj_mesh.geometry.values()) if hasattr(obj_mesh, "geometry") else [obj_mesh]
    for i, g in enumerate(geoms):
        g.export(out / "parts" / f"part_{i:02d}.glb")
    st["parca_sayisi"] = len(geoms)
    st["kapali"] = [bool(g.is_watertight) for g in geoms]
    (out / "xpart.json").write_text(json.dumps(st, indent=2), encoding="utf-8")
    print(f"X-Part: {len(geoms)} parça, {st['calisma_sn']} sn, tepe {st['tepe_vram_gb']} GB")
    o.sonuc(st)


def main(argv=None):
    with o.gpu_kilidi():
        _main(argv)


if __name__ == "__main__":
    main()
