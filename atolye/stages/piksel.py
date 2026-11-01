"""Step 08 (Piksel): toon still -> pixel sprite (numpy + Pillow only, runs in well under a second).

The subject is scaled so its height is `boy` pixels, placed on a fixed grid (feet near the bottom, centred), downsampled
by block majority alpha and a robust median colour, snapped to a palette in OKLab, cleaned of specks and pinholes, and
given a 1 px selective outline (the darkest shade of the neighbouring colour, from the same palette).

Palettes: a `.hex` file from paletler/ (one RRGGBB per line), or `ozgun` / `ozgun-32` / `ozgun-16`: an adaptive
palette of 64 / 32 / 16 colours taken from the still itself (k-means in OKLab).

  python -I atolye/calis.py piksel --girdi toon_ucceyrek.png --cikti piksel_160.png --boy 160 --palet ozgun
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from ..ayar import KOK

PALET_KLASORU = KOK / "paletler"
OZGUN = {"ozgun": 64, "ozgun-32": 32, "ozgun-16": 16}


# ---------------------------------------------------------------- colour
def srgb_to_oklab(rgb: np.ndarray) -> np.ndarray:
    c = rgb.astype(np.float32) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    l = 0.4122214708 * c[..., 0] + 0.5363325363 * c[..., 1] + 0.0514459929 * c[..., 2]
    m = 0.2119034982 * c[..., 0] + 0.6806995451 * c[..., 1] + 0.1073969566 * c[..., 2]
    s = 0.0883024619 * c[..., 0] + 0.2817188376 * c[..., 1] + 0.6299787005 * c[..., 2]
    l, m, s = np.cbrt(l), np.cbrt(m), np.cbrt(s)
    return np.stack([
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    ], -1)


def hex_oku(yol: Path) -> np.ndarray:
    renkler = []
    for satir in Path(yol).read_text(encoding="utf-8").split():
        h = satir.strip().lstrip("#")
        if len(h) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in h):
            renkler.append([int(h[i:i + 2], 16) for i in (0, 2, 4)])
    if not renkler:
        raise ValueError(f"palette has no colours: {yol}")
    return np.array(renkler, dtype=np.uint8)


def paletler(klasor: Path = PALET_KLASORU) -> list[dict]:
    """Every palette id the API offers: the adaptive ones first, then the .hex files (sorted)."""
    out = [{"id": k, "renk_sayisi": n, "uyarlamali": True, "renkler": []} for k, n in OZGUN.items()]
    for f in sorted(klasor.glob("*.hex")):
        pal = hex_oku(f)
        out.append({"id": f.stem, "renk_sayisi": len(pal), "uyarlamali": False,
                    "renkler": ["#%02x%02x%02x" % tuple(int(v) for v in c) for c in pal]})
    return out


def palet_gecerli(palet: str, klasor: Path = PALET_KLASORU) -> bool:
    return palet in OZGUN or (klasor / f"{palet}.hex").is_file() and "/" not in palet and "\\" not in palet


def kmeans_palet(rgb: np.ndarray, k: int, iters: int = 12, seed: int = 0) -> np.ndarray:
    """Adaptive palette: k-means in OKLab over the opaque pixels, seeded along lightness. Returns uint8 [k', 3]."""
    px = rgb.reshape(-1, 3)
    uniq = np.unique(px, axis=0)
    if len(uniq) <= k:
        return uniq.astype(np.uint8)
    rng = np.random.default_rng(seed)
    if len(px) > 60000:
        px = px[rng.choice(len(px), 60000, replace=False)]
    lab = srgb_to_oklab(px)
    order = np.argsort(lab[:, 0])
    cen = lab[order[((np.arange(k) + 0.5) / k * len(order)).astype(int)]].copy()
    for _ in range(iters):
        d = ((lab[:, None, :] - cen[None]) ** 2).sum(-1)
        lbl = d.argmin(1)
        for j in range(k):
            sel = lbl == j
            if sel.any():
                cen[j] = lab[sel].mean(0)
    # Report each cluster by its member closest to the centre (a real colour from the still, in sRGB).
    d = ((lab[:, None, :] - cen[None]) ** 2).sum(-1)
    lbl = d.argmin(1)
    out = []
    for j in range(k):
        sel = np.nonzero(lbl == j)[0]
        if len(sel):
            out.append(px[sel[d[sel, j].argmin()]])
    return np.unique(np.array(out, dtype=np.uint8), axis=0)


def snap(rgb: np.ndarray, pal: np.ndarray, pal_lab: np.ndarray) -> np.ndarray:
    lab = srgb_to_oklab(rgb.reshape(-1, 3))
    out = np.empty((len(lab),), dtype=np.int64)
    for s in range(0, len(lab), 16384):  # bounded memory for big palettes
        out[s:s + 16384] = ((lab[s:s + 16384, None, :] - pal_lab[None]) ** 2).sum(-1).argmin(1)
    return pal[out].reshape(rgb.shape)


# ---------------------------------------------------------------- geometry
def bbox(alpha: np.ndarray, thr: int = 128):
    ys, xs = np.nonzero(alpha >= thr)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def kanvas(boy: int, w_src: int, h_src: int) -> tuple[int, int, int]:
    """(width, height, feet_y) of the sprite canvas for a subject of w_src x h_src source pixels at `boy` px tall.
    Height = boy * 1.6 rounded up to 16 (160 -> 256, 128 -> 208, 80 -> 128), feet ~8% above the bottom; the width is
    the same unless the subject is wider than that."""
    h = int(math.ceil(boy * 1.6 / 16) * 16)
    w = max(h, int(math.ceil((w_src * boy / h_src + 8) / 16) * 16))
    feet = h - max(2, round(h * 0.078))
    return w, h, feet


def grid_downsample(im: Image.Image, scale: float, offset, size, k: int = 4):
    """1 target px = k x k source px: majority alpha per block, colour = mean of the opaque samples within one std
    of the block's median luminance (ignores stray line pixels)."""
    cw, ch = size
    W, H = im.size
    big = im.resize((max(1, round(W * scale * k)), max(1, round(H * scale * k))), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (cw * k, ch * k), (0, 0, 0, 0))
    canvas.paste(big, (round(offset[0] * k), round(offset[1] * k)), big)
    a = np.asarray(canvas).reshape(ch, k, cw, k, 4).transpose(0, 2, 1, 3, 4).reshape(ch, cw, k * k, 4)
    opaque = a[..., 3] >= 128
    keep = opaque.sum(-1) >= (k * k) // 2
    rgb = a[..., :3].astype(np.float32)
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    lum_o = np.where(opaque, lum, np.nan)
    with np.errstate(all="ignore"):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(lum_o, axis=-1, keepdims=True)
            std = np.nanstd(lum_o, axis=-1, keepdims=True)
    near = (np.abs(lum - med) <= std + 1e-3) & opaque
    w2 = near[..., None].astype(np.float32)
    col = (rgb * w2).sum(-2) / np.maximum(w2.sum(-2), 1)
    col = np.where(keep[..., None], col, 0)
    return np.clip(col, 0, 255).astype(np.uint8), keep


def _komsu_say(m: np.ndarray, sekiz: bool = True) -> np.ndarray:
    p = np.pad(m.astype(np.int32), 1)
    H, W = m.shape
    dirs = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy or dx) and (sekiz or not (dy and dx))]
    return sum(p[1 + dy:1 + dy + H, 1 + dx:1 + dx + W] for dy, dx in dirs)


def _komsu_ortalama(rgb: np.ndarray, m: np.ndarray, sekiz: bool) -> np.ndarray:
    H, W = m.shape
    p = np.pad(rgb.astype(np.float32) * m[..., None], ((1, 1), (1, 1), (0, 0)))
    dirs = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy or dx) and (sekiz or not (dy and dx))]
    s = sum(p[1 + dy:1 + dy + H, 1 + dx:1 + dx + W] for dy, dx in dirs)
    n = _komsu_say(m, sekiz)
    return s / np.maximum(n, 1)[..., None]


def cleanup(rgb: np.ndarray, mask: np.ndarray):
    """Remove isolated specks, fill pinholes with the mean of their opaque neighbours."""
    n = _komsu_say(mask)
    m = mask.copy()
    m[mask & (n <= 1)] = False
    hole = (~mask) & (n >= 7)
    m[hole] = True
    rgb = rgb.copy()
    if hole.any():
        rgb[hole] = _komsu_ortalama(rgb, mask, True)[hole].astype(np.uint8)
    return rgb, m


def add_outline(rgb: np.ndarray, mask: np.ndarray, pal: np.ndarray, pal_lab: np.ndarray):
    """1 px outline outside the silhouette: per pixel the darkest local shade of its neighbours' colour (keeps hue)."""
    ring = (~mask) & (_komsu_say(mask, sekiz=False) > 0)
    out_rgb, out_mask = rgb.copy(), mask.copy()
    if ring.any():
        mean = _komsu_ortalama(rgb, mask, False)[ring]
        c = srgb_to_oklab(np.clip(mean, 0, 255).astype(np.uint8))
        target = np.stack([np.minimum(c[:, 0], 0.22), c[:, 1] * 0.6, c[:, 2] * 0.6], -1)
        idx = ((target[:, None, :] - pal_lab[None]) ** 2).sum(-1).argmin(1)
        out_rgb[ring] = pal[idx]
        out_mask[ring] = True
    return out_rgb, out_mask


# ---------------------------------------------------------------- main step
def pikselle(girdi: Path, cikti: Path, boy: int = 160, palet: str = "ozgun", cizgi: bool = True,
             klasor: Path = PALET_KLASORU) -> dict:
    if not 16 <= boy <= 1024:
        raise ValueError("boy must be 16..1024")
    im = Image.open(girdi).convert("RGBA")
    bb = bbox(np.asarray(im)[..., 3])
    if bb is None:
        raise ValueError(f"the still is empty (no opaque pixel): {girdi}")
    x0, y0, x1, y1 = bb
    scale = boy / (y1 - y0)
    cw, ch, feet = kanvas(boy, x1 - x0, y1 - y0)
    ox = cw / 2 - ((x0 + x1) / 2) * scale
    oy = feet - y1 * scale
    rgb, mask = grid_downsample(im, scale, (ox, oy), (cw, ch))
    if palet in OZGUN:
        # k colours in total: most from the still, a few dark shades of them for the outline.
        k = OZGUN[palet]
        koyu = max(1, k // 8)
        pal = kmeans_palet(rgb[mask], k - koyu)
        pal = np.unique(np.vstack([pal, kmeans_palet((pal.astype(np.float32) * 0.35).astype(np.uint8), koyu)]), axis=0)
    else:
        if not palet_gecerli(palet, klasor):
            raise ValueError(f"unknown palette: {palet}")
        pal = hex_oku(klasor / f"{palet}.hex")
    pal_lab = srgb_to_oklab(pal)
    rgb = snap(rgb, pal, pal_lab)
    rgb, mask = cleanup(rgb, mask)
    rgb = snap(rgb, pal, pal_lab)
    if cizgi:
        rgb, mask = add_outline(rgb, mask, pal, pal_lab)
    rgba = np.dstack([np.where(mask[..., None], rgb, 0), np.where(mask, 255, 0)]).astype(np.uint8)
    cikti = Path(cikti)
    cikti.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(cikti)
    used = np.unique(rgba[mask][:, :3], axis=0) if mask.any() else np.zeros((0, 3))
    return {"boy": boy, "genislik": cw, "yukseklik": ch, "ayak_y": feet, "palet": palet,
            "renk_sayisi": int(len(used)), "cizgi": cizgi, "olcek": round(scale, 5), "girdi": Path(girdi).name,
            "dosya": cikti.name}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="piksel")
    ap.add_argument("--girdi", required=True, help="toon still (RGBA, transparent background)")
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--boy", type=int, default=160, help="subject height in pixels")
    ap.add_argument("--palet", default="ozgun")
    ap.add_argument("--cizgi", action=argparse.BooleanOptionalAction, default=True, help="1 px outline")
    a = ap.parse_args(argv)
    meta = pikselle(Path(a.girdi), Path(a.cikti), a.boy, a.palet, a.cizgi)
    print("@@sonuc " + json.dumps(meta))
    return meta


if __name__ == "__main__":
    main()
