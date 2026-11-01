"""Runs the upstream Hunyuan3D code offline, from the folders in atolye.toml, without editing the clones.

The clones under <veri>/kod are kept pristine (treated as data). Everything they would download or compile in place is
redirected here instead:
- weights come from <modeller>/<org>__<repo> (HF_HUB_OFFLINE=1, no network at run time)
- the compiled extensions (custom_rasterizer_kernel, mesh_inpaint_processor) live in <veri>/derleme
- `bpy` (only used by the clone to convert OBJ -> GLB) is stubbed; we write GLBs ourselves
- Sonata (P3-SAM / X-Part backbone) loads our local sonata.pth, without flash-attn when it is not installed
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

from . import ayar as _ayar
from .modeller import yollar as _model_yollari

A = _ayar.yukle()
M = _model_yollari(A.modeller)
HY21 = A.kod / "Hunyuan3D-2.1"
HYPART = A.kod / "Hunyuan3D-Part"
HY2 = A.kod / "Hunyuan3D-2"
BUILD = A.derleme

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ.setdefault("U2NET_HOME", str(M["u2net"]))


def _yol_ekle(*ps: Path) -> None:
    for p in ps:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def stub_bpy() -> None:
    """The clone imports bpy at module level (DifferentiableRenderer/mesh_utils.py) only for OBJ -> GLB."""
    if "bpy" not in sys.modules:
        sys.modules["bpy"] = types.ModuleType("bpy")


def kur_hy21() -> None:
    """Shape + paint (Hunyuan3D-2.1)."""
    stub_bpy()
    _yol_ekle(BUILD, HY21 / "hy3dshape", HY21 / "hy3dpaint", HY21)
    try:
        import mesh_inpaint_processor  # our build, registered under the name the clone imports

        sys.modules["DifferentiableRenderer.mesh_inpaint_processor"] = mesh_inpaint_processor
    except ImportError as e:
        print(f"[hy_ortam] mesh_inpaint_processor yok: {e}")
    try:
        import contextlib
        import io

        from torchvision_fix import apply_fix  # clone helper for basicsr/realesrgan on new torchvision

        with contextlib.redirect_stdout(io.StringIO()):  # it prints three lines on every run
            apply_fix()
    except Exception as e:  # pragma: no cover
        print(f"[hy_ortam] torchvision düzeltmesi atlandı: {e}")
    import huggingface_hub

    _orig = huggingface_hub.snapshot_download

    def _yerel(repo_id=None, **kw):
        if repo_id == "tencent/Hunyuan3D-2.1":
            return str(M["hy21"])
        return _orig(repo_id=repo_id, **kw)

    huggingface_hub.snapshot_download = _yerel


def kur_2mv() -> None:
    """Multi-view shape (Hunyuan3D-2mv, from the Hunyuan3D-2 code). Its loader looks under HY3DGEN_MODELS/<repo id>."""
    _yol_ekle(HY2)
    os.environ["HY3DGEN_MODELS"] = str(A.modeller)


def flash_var() -> bool:
    try:
        import flash_attn  # noqa: F401

        return True
    except ImportError:
        return False


def kur_part():
    """P3-SAM (and the shared Sonata loader)."""
    _yol_ekle(HYPART / "XPart" / "partgen", HYPART / "P3-SAM", HYPART / "P3-SAM" / "demo")
    from models import sonata  # XPart/partgen/models/sonata

    _orig_load = sonata.load

    def _yerel_load(name="sonata", repo_id="facebook/sonata", download_root=None, custom_config=None, ckpt_only=False):
        cfg = dict(custom_config or {})
        if not flash_var():
            cfg.setdefault("enable_flash", False)
        return _orig_load(str(M["sonata"]), custom_config=cfg, ckpt_only=ckpt_only)

    sonata.load = _yerel_load
    return sonata


class _LazyCdist:
    def __init__(self, a, b):
        self.a, self.b = a, b


class _TorchNN:
    """Stand-in for `torch` inside partgen.models.conditioner.condioner_release only.

    Its forward() does torch.argmin(torch.cdist(query[P,4096,3], surface[P,81920,3])) twice. The dense distance
    matrices are ~12 GB each for 9 parts and push a 32 GB card into Windows' shared-memory fallback (X-Part then takes
    ~47 min instead of ~2). Here cdist returns a lazy pair and argmin computes the same indices in row chunks."""

    def __init__(self, torch, chunk=2048):
        self._t, self._chunk = torch, chunk

    def __getattr__(self, name):
        return getattr(self._t, name)

    def cdist(self, a, b, *args, **kwargs):
        return _LazyCdist(a, b)

    def argmin(self, x, dim=None, **kwargs):
        if not isinstance(x, _LazyCdist):
            return self._t.argmin(x, dim=dim, **kwargs)
        assert dim in (-1, 2)
        a, b = x.a, x.b.to(x.a.dtype)
        out = [self._t.argmin(self._t.cdist(a[:, s:s + self._chunk], b), dim=-1)
               for s in range(0, a.shape[1], self._chunk)]
        return self._t.cat(out, dim=1)


def kur_xpart() -> None:
    """X-Part: Sonata under both module names, flash off, chunked nearest neighbour."""
    xp = HYPART / "XPart"
    _yol_ekle(xp, xp / "partgen", HYPART / "P3-SAM")
    kur_part()
    import models.sonata as ms
    import partgen.models.sonata as ps

    ps.load = ms.load

    def _load_by_config(path):
        cfg = json.loads(Path(path).read_text())
        if not flash_var():
            cfg["enable_flash"] = False
        from partgen.models.sonata.model import PointTransformerV3

        return PointTransformerV3(**cfg)

    ps.load_by_config = _load_by_config
    import torch
    import partgen.models.conditioner.condioner_release as cr

    cr.torch = _TorchNN(torch)
