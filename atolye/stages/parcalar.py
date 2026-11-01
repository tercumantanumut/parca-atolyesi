"""Step 04 (Parçalar): automatic part segmentation with P3-SAM (Hunyuan3D-Part). Works on any mesh.

  python -I atolye/calis.py parcalar --mesh <is>/shape.glb --cikti <is>/p3sam [--tohum 42] [--birlestir]

Writes the clone's outputs into --cikti: auto_mask_mesh_final.glb (the cleaned mesh, faces coloured per part),
auto_mask_mesh_final_face_ids.npy (part id per face), *_aabb.npy (part boxes, the X-Part input), plus p3sam.json.
Step 05 (ayrik) turns that into per-part GLBs. Measured on an RTX 5090: ~2 s load, 16-27 s, working set ~12-13 GB.

Keep --prompt-bs 8: larger batches need far more VRAM and Windows silently spills into shared memory (minutes
instead of seconds). --birlestir (post-processing) merges small or unlabelled regions into fewer, larger parts.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import _ortak as o


def yukle():
    from .. import hy_ortam

    hy_ortam.kur_part()
    import auto_mask  # P3-SAM/demo/auto_mask.py

    return auto_mask.AutoMask(str(hy_ortam.M["part"] / "p3sam" / "p3sam.safetensors"))


def segment(mesh_yolu: Path, out: Path, tohum: int = 42, birlestir: bool = False, prompt_bs: int = 8,
            esik: float = 0.95, al=o.dogrudan) -> dict:
    from .. import hy_ortam

    hy_ortam.kur_part()
    import auto_mask  # P3-SAM/demo/auto_mask.py
    import trimesh

    out.mkdir(parents=True, exist_ok=True)
    st = {"tohum": tohum, "birlestir": birlestir, "prompt_bs": prompt_bs, "vram": o.vram_siniri()}
    t0 = time.time()
    am = al("p3sam", yukle)
    st["yukleme_sn"] = round(time.time() - t0, 1)
    mesh = trimesh.load(str(mesh_yolu), force="mesh")
    auto_mask.set_seed(tohum)
    t = o.Tepe()
    aabb, face_ids, mesh = am.predict_aabb(
        mesh, save_path=str(out), point_num=100000, prompt_num=400, threshold=esik, post_process=birlestir,
        save_mid_res=True, show_info=True, seed=tohum, is_parallel=False, clean_mesh_flag=True, prompt_bs=prompt_bs)
    st.update(calisma_sn=t.sn, tepe_vram_gb=t.gb, tepe_ayrilan_gb=t.ayrilan_gb)
    del am  # a frame kept alive by a library must not pin the (possibly kept) model
    import numpy as np

    st["parca_sayisi"] = int(len([p for p in np.unique(face_ids) if p >= 0]))
    son = "auto_mask_mesh_final_post" if birlestir else "auto_mask_mesh_final"
    st["face_ids"] = f"{son}_face_ids.npy"
    st["aabb"] = f"{son}_aabb.npy"
    if birlestir:
        # step 05 reads auto_mask_mesh_final.*: point it at the merged result
        mesh.export(out / "auto_mask_mesh_final.glb")
        np.save(out / "auto_mask_mesh_final_face_ids.npy", face_ids)
    (out / "p3sam.json").write_text(json.dumps(st, indent=2), encoding="utf-8")
    return st


def ayristir(argv=None):
    ap = argparse.ArgumentParser(prog="parcalar")
    ap.add_argument("--mesh", required=True)
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--tohum", type=int, default=42)
    ap.add_argument("--birlestir", action="store_true", help="merge small parts (P3-SAM post-processing)")
    ap.add_argument("--prompt-bs", type=int, default=8)
    ap.add_argument("--esik", type=float, default=0.95, help="mask NMS IoU merge threshold")
    return ap.parse_args(argv)


def gerekli_modeller(a) -> list[str]:
    return ["p3sam"]


def calistir(a, al) -> dict:
    o.faz(0.0, 0.1, "yukleniyor")
    st = segment(Path(a.mesh), Path(a.cikti).resolve(), a.tohum, a.birlestir, a.prompt_bs, a.esik, al)
    print(f"P3-SAM: {st['parca_sayisi']} parça, {st['calisma_sn']} sn, tepe {st['tepe_vram_gb']} GB")
    return st


def main(argv=None):
    a = ayristir(argv)
    with o.gpu_kilidi():
        st = calistir(a, o.dogrudan)
    o.sonuc(st)


if __name__ == "__main__":
    main()
