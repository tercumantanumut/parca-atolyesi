import json

import numpy as np
import trimesh
from PIL import Image

from atolye.stages import ayrik
from tests.sahte_adim import figur


def test_guess_labels_insansi():
    def p(faces, lo, hi):
        lo, hi = np.array(lo, float), np.array(hi, float)
        return {"faces": faces, "aabb_min": lo.tolist(), "aabb_max": hi.tolist(), "centroid": ((lo + hi) / 2).tolist()}

    parts = [p(1000, (-0.3, -1, -0.2), (0.3, 0, 0.2)),      # legs
             p(900, (-0.35, 0, -0.2), (0.35, 0.6, 0.2)),    # top
             p(400, (-0.15, 0.6, -0.15), (0.15, 0.95, 0.15)),  # head
             p(300, (-0.17, 0.7, -0.2), (0.17, 1.0, 0.1)),  # hair (highest)
             p(80, (0.55, 0.0, -0.1), (0.7, 0.15, 0.1)),    # hand.L (+X)
             p(80, (-0.7, 0.0, -0.1), (-0.55, 0.15, 0.1)),  # hand.R
             p(90, (0.05, -1, -0.1), (0.25, -0.85, 0.15)),  # foot.L
             p(90, (-0.25, -1, -0.1), (-0.05, -0.85, 0.15)),  # foot.R
             p(50, (-0.1, 0.1, 0.2), (0.1, 0.3, 0.3))]      # accessory
    ayrik.guess_labels(parts, ((-0.7, -1, -0.2), (0.7, 1.0, 0.3)))
    assert [x["guess"] for x in parts] == ["legs", "top", "head", "hair", "hand.L", "hand.R", "foot.L", "foot.R",
                                           "accessory"]


def test_etiket_aktar_ve_tolerans():
    src = np.array([[0, 0, 0], [1, 0, 0], [5, 5, 5]], float)
    lab = np.array([3, 7, -1])
    hedef = np.array([[0.1, 0, 0], [0.9, 0.1, 0], [4.9, 5, 5]], float)
    e, uzak = ayrik.etiket_aktar(src, lab, hedef, tolerans=0.5)
    assert e.tolist() == [3, 7, 7] and uzak == 1  # unlabelled faces are never chosen


def _p3sam(tmp_path):
    m, ids = figur()
    d = tmp_path / "p3sam"
    d.mkdir()
    m.export(d / "auto_mask_mesh_final.glb")
    np.save(d / "auto_mask_mesh_final_face_ids.npy", ids)
    return m, ids, d


def test_bol_sekil(tmp_path):
    m, ids, d = _p3sam(tmp_path)
    m.export(tmp_path / "shape.glb")
    st = ayrik.bol(d, tmp_path / "shape.glb", tmp_path)
    j = json.loads((tmp_path / "parts.json").read_text())
    assert st["num_parts"] == 4 and st["faces_beyond_tolerance"] == 0
    assert sum(p["faces"] for p in j["parts"]) == len(m.faces)
    assert [p["faces"] for p in j["parts"]] == sorted((p["faces"] for p in j["parts"]), reverse=True)
    for p in j["parts"]:
        assert (tmp_path / "parts" / p["file"]).exists() and p["renk"].startswith("#")
    assert len(trimesh.load(tmp_path / "parts.glb").geometry) == 4


def test_bol_dokulu_parca_dokusu_maskeli(tmp_path):
    m, ids, d = _p3sam(tmp_path)
    t = m.copy()
    uv = np.random.default_rng(1).random((len(t.vertices), 2)) * 0.2 + 0.4  # all UVs in the middle of the atlas
    tex = Image.new("RGB", (256, 256), (250, 200, 100))
    t.visual = trimesh.visual.TextureVisuals(uv=uv, material=trimesh.visual.material.PBRMaterial(baseColorTexture=tex))
    t.export(tmp_path / "textured.glb")
    ayrik.bol(d, tmp_path / "textured.glb", tmp_path)
    p = trimesh.load(tmp_path / "parts" / "part_00.glb", force="mesh")
    img = np.asarray(p.visual.material.baseColorTexture.convert("RGB"))
    assert img.shape[0] == 2048
    assert img[5, 5].max() < 20            # unused corner blacked out
    assert img[1024, 1024].min() > 80      # used centre kept
