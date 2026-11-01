"""Model groups on disk: which files each group needs and whether they are present (stdlib only).

The installer writes the Hugging Face listing of every pinned repo to `<modeller>/.liste/` when it downloads, so
this module can tell, offline, whether each file is present at its expected size. Hash checks are done by the
installer (`kur.py dogrula`); this check is cheap enough for every GET /api/sistem.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .ayar import KOK

if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))
from kurulum.kaynaklar import GRUPLAR, klasor  # noqa: E402


def liste_yolu(modeller: Path, repo: str, rev: str) -> Path:
    return modeller / ".liste" / f"{klasor(repo)}@{rev[:12]}.json"


def secilen(liste: list[dict], desenler: list[str]) -> list[dict]:
    """Files of a HF tree listing that match the patterns (exact path, or a folder prefix ending in '/')."""
    out = []
    for f in liste:
        if f.get("type") != "file":
            continue
        p = f["path"]
        if any(p == d or (d.endswith("/") and p.startswith(d)) for d in desenler):
            out.append(f)
    return out


def grup_dosyalari(modeller: Path, grup: dict) -> list[tuple[Path, int]] | None:
    """(local path, expected size) for every file of the group, or None if a listing has not been fetched yet."""
    out = []
    for repo, rev, desenler in grup["hf"]:
        lp = liste_yolu(modeller, repo, rev)
        if not lp.exists():
            return None
        for f in secilen(json.loads(lp.read_text(encoding="utf-8")), desenler):
            out.append((modeller / klasor(repo) / f["path"], int(f["size"])))
    for d in grup["dosya"]:
        out.append((modeller / d["yol"], int(d["boyut"])))
    return out


def grup_hazir(modeller: Path, grup: dict) -> bool:
    dosyalar = grup_dosyalari(modeller, grup)
    if not dosyalar:
        return False
    return all(p.exists() and p.stat().st_size == n for p, n in dosyalar)


def durum(modeller: Path) -> dict[str, bool]:
    """{model id: ready} for GET /api/sistem."""
    return {g["model"]: grup_hazir(modeller, g) for g in GRUPLAR}


# Paths the stages load from (Hugging Face layout under <modeller>/<org>__<repo>/).
def yollar(modeller: Path) -> dict[str, Path]:
    return {
        "hy21": modeller / "tencent__Hunyuan3D-2.1",
        "part": modeller / "tencent__Hunyuan3D-Part",
        "mv": modeller / "tencent__Hunyuan3D-2mv",
        "dino": modeller / "facebook__dinov2-giant",
        "sonata": modeller / "facebook__sonata" / "sonata.pth",
        "realesrgan": modeller / "xinntao__Real-ESRGAN" / "RealESRGAN_x4plus.pth",
        "u2net": modeller / "danielgatis__rembg",
    }
