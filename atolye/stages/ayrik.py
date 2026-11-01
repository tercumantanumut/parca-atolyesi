"""Step 05 (Ayrık): split a mesh into one GLB per part, using P3-SAM's per-face labels (CPU, a few seconds).

P3-SAM segments its own cleaned copy of the mesh. Every face of the mesh we split (normally the textured mesh, so the
parts keep their UVs and texture; else the shape) takes the label of the nearest labelled P3-SAM face. Both meshes
are in the same Hunyuan coordinates, so this is exact up to the remeshing.

Writes, in --cikti:
- parts/part_XX.glb: one mesh per part, 00 = largest (UVs and material kept)
- parts.glb: every part in one scene, one node per part (part_XX_<guess>)
- parts.json: {"stats": {...}, "parts": [{index, p3sam_id, faces, aabb_min, aabb_max, centroid, guess, renk, file}]}

`guess` is a box heuristic for an upright humanoid in Hunyuan axes (Y up, front +Z, the character's left = +X):
hair / head / top / legs / hand.L / hand.R / foot.L / foot.R, everything else `accessory`. It is only a hint.
"""
from __future__ import annotations

import argparse
import colorsys
import json
import time
from pathlib import Path

import numpy as np


def guess_labels(parts: list[dict], bounds) -> None:
    """Rough humanoid labels from part boxes (Y up, character's left = +X). Sets p['guess'] on every part."""
    lo, hi = np.asarray(bounds[0], float), np.asarray(bounds[1], float)
    h, w = max(hi[1] - lo[1], 1e-9), max(hi[0] - lo[0], 1e-9)
    total = sum(p["faces"] for p in parts) or 1
    for p in parts:
        p["guess"] = "accessory"
    rest = list(parts)

    def take(cands, label):
        for c in cands:
            if c in rest:
                c["guess"] = label
                rest.remove(c)
                return c

    def ny(v):
        return (v - lo[1]) / h  # 0 = feet, 1 = top

    feet = [p for p in rest if ny(p["aabb_max"][1]) < 0.2 and p["faces"] < 0.15 * total]
    take([p for p in feet if p["centroid"][0] > 0], "foot.L")
    take([p for p in feet if p["centroid"][0] <= 0], "foot.R")
    cx = (lo[0] + hi[0]) / 2
    hands = [p for p in rest if abs(p["centroid"][0] - cx) > 0.25 * w and p["faces"] < 0.1 * total]
    hands.sort(key=lambda p: -abs(p["centroid"][0]))
    take([p for p in hands if p["centroid"][0] > 0], "hand.L")
    take([p for p in hands if p["centroid"][0] <= 0], "hand.R")
    top = sorted([p for p in rest if ny(p["aabb_max"][1]) > 0.9], key=lambda p: -p["aabb_max"][1])
    if top:
        take(top[:1], "hair" if len(top) > 1 else "head")
        take(top[1:2], "head")
    big = sorted(rest, key=lambda p: -p["faces"])[:2]
    take([p for p in big if ny(p["centroid"][1]) >= 0.5], "top")
    take([p for p in big if ny(p["centroid"][1]) < 0.5], "legs")


def part_rengi(i: int) -> str:
    """Distinct, stable colour per part index (golden-ratio hue walk)."""
    r, g, b = colorsys.hsv_to_rgb((0.08 + i * 0.618034) % 1.0, 0.55, 0.92)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def etiket_aktar(kaynak_merkez: np.ndarray, kaynak_etiket: np.ndarray, hedef_merkez: np.ndarray,
                 tolerans: float) -> tuple[np.ndarray, int]:
    """Label of the nearest labelled source face for every target face; also how many are farther than tolerans."""
    from scipy.spatial import cKDTree

    ok = kaynak_etiket >= 0
    if not ok.any():
        raise ValueError("P3-SAM labelled no face")
    agac = cKDTree(kaynak_merkez[ok])
    d, i = agac.query(hedef_merkez, k=1, workers=-1)
    return kaynak_etiket[ok][i], int((d > tolerans).sum())


def tek_mesh(yol: Path):
    """Load a GLB/OBJ as one trimesh with its visuals (UVs + material), in world coordinates."""
    import trimesh

    s = trimesh.load(str(yol), process=False)
    if isinstance(s, trimesh.Trimesh):
        return s
    geoms = s.dump() if hasattr(s, "dump") else list(s.geometry.values())
    geoms = [g for g in geoms if isinstance(g, trimesh.Trimesh) and len(g.faces)]
    if len(geoms) == 1:
        return geoms[0]
    return trimesh.util.concatenate(geoms)


def _jpeg(im, kalite: int = 90):
    """Re-open an image from JPEG bytes, so trimesh embeds it as JPEG (it keeps JPEG, writes everything else PNG)."""
    import io

    from PIL import Image

    b = io.BytesIO()
    im.convert("RGB").save(b, format="JPEG", quality=kalite)
    b.seek(0)
    return Image.open(b)


def parca_dokusu(sub, boyut: int = 2048) -> None:
    """Give a part its own copy of the atlas with every texel it does not use blacked out (UVs unchanged).

    The atlas charts of one part are scattered over the whole texture, so cropping does not help; masking does:
    the unused area compresses to almost nothing, and 31 parts stay a few MB instead of 31 full atlases."""
    import copy

    from PIL import Image, ImageDraw, ImageFilter

    vis = sub.visual
    mat = getattr(vis, "material", None)
    uv = getattr(vis, "uv", None)
    if mat is None or uv is None or getattr(mat, "baseColorTexture", None) is None:
        return
    tri = uv[sub.faces] * [boyut, boyut]
    tri[..., 1] = boyut - tri[..., 1]
    maske = Image.new("L", (boyut, boyut), 0)
    ciz = ImageDraw.Draw(maske)
    for t in tri:
        ciz.polygon([tuple(p) for p in t], fill=255)
    maske = maske.filter(ImageFilter.MaxFilter(5))  # a little padding against seams and mip bleeding
    siyah = Image.new("RGB", (boyut, boyut), (0, 0, 0))
    yeni = copy.copy(mat)
    for ad in ("baseColorTexture", "metallicRoughnessTexture"):
        img = getattr(mat, ad, None)
        if img is not None:
            img = img.convert("RGB").resize((boyut, boyut), Image.Resampling.LANCZOS)
            setattr(yeni, ad, _jpeg(Image.composite(img, siyah, maske)))
    for ad in ("normalTexture", "occlusionTexture", "emissiveTexture"):
        if getattr(yeni, ad, None) is not None:
            setattr(yeni, ad, None)
    vis.material = yeni


def bol(p3sam: Path, hedef: Path, cikti: Path, face_ids: Path | None = None, min_yuzey: int = 0) -> dict:
    import trimesh

    t0 = time.time()
    seg_glb = p3sam / "auto_mask_mesh_final.glb"
    face_ids = face_ids or p3sam / "auto_mask_mesh_final_face_ids.npy"
    seg = tek_mesh(seg_glb)
    ids = np.load(face_ids).astype(np.int64).reshape(-1)
    if len(ids) != len(seg.faces):
        raise ValueError(f"face_ids ({len(ids)}) do not match the segmented mesh ({len(seg.faces)} faces)")
    mesh = tek_mesh(hedef)
    tol = 0.02 * float(np.ptp(mesh.bounds[:, 1]))
    etiket, uzak = etiket_aktar(seg.triangles_center, ids, mesh.triangles_center, tol)

    pids = [int(p) for p in np.unique(etiket)]
    pids.sort(key=lambda p: -int((etiket == p).sum()))
    if min_yuzey:
        pids = [p for p in pids if (etiket == p).sum() >= min_yuzey]
    parts_dir = cikti / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    for f in parts_dir.glob("part_*.glb"):
        f.unlink()
    subs, parts = [], []
    for idx, pid in enumerate(pids):
        sel = np.nonzero(etiket == pid)[0]
        sub = mesh.submesh([sel], append=True)
        subs.append(sub)
        parts.append({"index": idx, "p3sam_id": pid, "faces": int(len(sel)),
                      "aabb_min": sub.bounds[0].round(4).tolist(), "aabb_max": sub.bounds[1].round(4).tolist(),
                      "centroid": sub.centroid.round(4).tolist(), "renk": part_rengi(idx)})
    guess_labels(parts, mesh.bounds)
    # parts.glb first: every part shares the one full atlas (trimesh writes a shared material once).
    scene = trimesh.Scene()
    for p, sub in zip(parts, subs):
        scene.add_geometry(sub, node_name=f"part_{p['index']:02d}_{p['guess']}", geom_name=f"part_{p['index']:02d}")
    scene.export(cikti / "parts.glb")
    for p, sub in zip(parts, subs):
        p["file"] = f"part_{p['index']:02d}.glb"
        parca_dokusu(sub)
        sub.export(parts_dir / p["file"])
    stats = {"mesh": hedef.name, "segmented": seg_glb.name, "num_parts": len(parts), "faces": int(len(mesh.faces)),
             "faces_beyond_tolerance": uzak, "split_s": round(time.time() - t0, 2)}
    p3 = p3sam / "p3sam.json"
    if p3.exists():
        stats["p3sam"] = json.loads(p3.read_text(encoding="utf-8"))
    (cikti / "parts.json").write_text(json.dumps({"stats": stats, "parts": parts}, indent=2), encoding="utf-8")
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ayrik")
    ap.add_argument("--p3sam", required=True, help="P3-SAM output folder (auto_mask_mesh_final.glb + face ids)")
    ap.add_argument("--hedef", required=True, help="mesh to split: textured.glb (keeps the texture) or shape.glb")
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--min-yuzey", type=int, default=0, help="drop parts with fewer faces")
    a = ap.parse_args(argv)
    stats = bol(Path(a.p3sam), Path(a.hedef), Path(a.cikti), min_yuzey=a.min_yuzey)
    print(f"{stats['num_parts']} parça, {stats['faces_beyond_tolerance']} yüz tolerans dışında")
    print("@@sonuc " + json.dumps(stats))


if __name__ == "__main__":
    main()
