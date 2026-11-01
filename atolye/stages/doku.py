"""Step 03 (Doku): PBR texture for a mesh with Hunyuan3D-2.1 paint (albedo + metallic + roughness, 2048² atlas).

  python -I atolye/calis.py doku --gorsel <is>/input_rgba.png --mesh <is>/shape.glb --cikti <is>

The paint model remeshes the shape to ~40k faces, unwraps it, renders 6 views of it, paints them with a multiview
diffusion model conditioned on the reference image, and bakes them back into the atlas (Real-ESRGAN upscales the views,
inpainting fills the gaps). Writes textured.glb (glTF PBR: base colour + metallic-roughness, JPEG textures) and
doku.json. The clone's intermediate files stay in <is>/doku/. Measured on an RTX 5090: 15-22 s load, 55-60 s, working set 13.5 GB (fits a 15 GB cap).
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from . import _ortak as o


def obj_to_glb(obj: Path, glb: Path) -> dict:
    """textured_mesh.obj (+ .jpg albedo, _metallic.jpg, _roughness.jpg) -> one GLB with a glTF PBR material."""
    import io

    import numpy as np
    import trimesh
    from PIL import Image

    mesh = trimesh.load(str(obj), force="mesh", process=False)
    base = obj.with_suffix("")

    def jpeg(im):
        b = io.BytesIO()
        im.convert("RGB").save(b, format="JPEG", quality=92)
        b.seek(0)
        return Image.open(b)

    albedo = None
    for ext in (".jpg", ".png"):
        if base.with_suffix(ext).exists():
            albedo = Image.open(base.with_suffix(ext))
            break
    if albedo is None and hasattr(mesh.visual, "material"):
        albedo = getattr(mesh.visual.material, "image", None)
    if albedo is None:
        raise FileNotFoundError(f"albedo texture next to {obj} not found")
    mr = None
    met, rou = Path(f"{base}_metallic.jpg"), Path(f"{base}_roughness.jpg")
    if met.exists() and rou.exists():
        m = Image.open(met).convert("L")
        r = Image.open(rou).convert("L").resize(m.size)
        # glTF: G = roughness, B = metallic
        mr = Image.merge("RGB", (Image.new("L", m.size, 0), r, m))
    mat = trimesh.visual.material.PBRMaterial(
        name="doku", baseColorTexture=jpeg(albedo), metallicRoughnessTexture=jpeg(mr) if mr else None,
        metallicFactor=1.0 if mr else 0.0, roughnessFactor=1.0)
    uv = mesh.visual.uv if hasattr(mesh.visual, "uv") and mesh.visual.uv is not None else np.zeros((len(mesh.vertices), 2))
    mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=mat)
    mesh.export(glb)
    return {"yuz": int(len(mesh.faces)), "doku_boyutu": list(albedo.size), "pbr": mr is not None}


def ayristir(argv=None):
    ap = argparse.ArgumentParser(prog="doku")
    ap.add_argument("--gorsel", required=True, help="reference image (input_rgba.png)")
    ap.add_argument("--mesh", required=True, help="mesh in the Hunyuan frame (shape.glb)")
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--gorunum", type=int, default=6, help="paint views, 6..9")
    ap.add_argument("--cozunurluk", type=int, default=512, help="view size, 512 or 768")
    return ap.parse_args(argv)


def gerekli_modeller(a) -> list[str]:
    return ["doku" if (a.gorunum, a.cozunurluk) == (6, 512) else f"doku_{a.gorunum}x{a.cozunurluk}"]


def yukleyici(gorunum: int, cozunurluk: int):
    def yukle():
        from textureGenPipeline import Hunyuan3DPaintConfig, Hunyuan3DPaintPipeline

        from .. import hy_ortam

        conf = Hunyuan3DPaintConfig(gorunum, cozunurluk)
        conf.realesrgan_ckpt_path = str(hy_ortam.M["realesrgan"])
        conf.multiview_cfg_path = str(hy_ortam.HY21 / "hy3dpaint" / "cfgs" / "hunyuan-paint-pbr.yaml")
        conf.custom_pipeline = str(hy_ortam.HY21 / "hy3dpaint" / "hunyuanpaintpbr")
        conf.dino_ckpt_path = str(hy_ortam.M["dino"])
        return Hunyuan3DPaintPipeline(conf)

    return yukle


def calistir(a, al) -> dict:
    from .. import hy_ortam

    hy_ortam.kur_hy21()
    out = Path(a.cikti).resolve()
    is_dir = out / "doku"
    is_dir.mkdir(parents=True, exist_ok=True)
    # The clone writes white_mesh_remesh.obj next to the mesh it is given: hand it a copy inside doku/.
    mesh = is_dir / "shape.glb"
    shutil.copyfile(a.mesh, mesh)
    gorsel = Path(a.gorsel).resolve()
    if gorsel.name != "input_rgba.png":  # a ready mesh with a raw reference image: cut it out first
        o.arkaplan_temizle(gorsel, out / "input_rgba.png")
        gorsel = out / "input_rgba.png"
    st = {"gorunum": a.gorunum, "cozunurluk": a.cozunurluk, "vram": o.vram_siniri()}
    o.faz(0.0, 0.2, "yukleniyor")
    t0 = time.time()
    paint = al(gerekli_modeller(a)[0], yukleyici(a.gorunum, a.cozunurluk))
    st["yukleme_sn"] = round(time.time() - t0, 1)
    o.faz(0.2, 0.95, "boyama")
    t = o.Tepe()
    paint(mesh_path=str(mesh), image_path=str(gorsel),
          output_mesh_path=str(is_dir / "textured_mesh.obj"), save_glb=False)
    st.update(calisma_sn=t.sn, tepe_vram_gb=t.gb, tepe_ayrilan_gb=t.ayrilan_gb)
    del paint  # a frame kept alive by a library must not pin the (possibly kept) pipeline
    o.faz(0.95, 1.0, "glb")
    st.update(obj_to_glb(is_dir / "textured_mesh.obj", out / "textured.glb"))
    (out / "doku.json").write_text(json.dumps(st, indent=2), encoding="utf-8")
    print(f"doku hazır: {st['yuz']} yüz, {st['calisma_sn']} sn, tepe {st['tepe_vram_gb']} GB")
    return st


def main(argv=None):
    a = ayristir(argv)
    with o.gpu_kilidi():
        st = calistir(a, o.dogrudan)
    o.sonuc(st)


if __name__ == "__main__":
    main()
