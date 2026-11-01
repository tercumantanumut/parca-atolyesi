import numpy as np
import pytest
from PIL import Image, ImageDraw

from atolye.stages import piksel


def figur_png(yol, w=400, h=800, renkler=((200, 60, 40), (40, 90, 200), (240, 220, 180))):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((w * 0.35, 40, w * 0.65, 200), fill=renkler[2] + (255,))         # head
    d.rectangle((w * 0.3, 200, w * 0.7, 500), fill=renkler[0] + (255,))         # body
    d.rectangle((w * 0.32, 500, w * 0.48, h - 20), fill=renkler[1] + (255,))    # legs
    d.rectangle((w * 0.52, 500, w * 0.68, h - 20), fill=renkler[1] + (255,))
    im.save(yol)
    return yol


def test_kanvas_kurallari():
    assert piksel.kanvas(160, 100, 200) == (256, 256, 236)
    assert piksel.kanvas(128, 100, 200)[:2] == (208, 208)
    assert piksel.kanvas(80, 100, 200) == (128, 128, 118)
    w, h, _ = piksel.kanvas(160, 1000, 200)  # five times wider than tall
    assert h == 256 and w >= 800 + 8 and w % 16 == 0


@pytest.mark.parametrize("palet,en_cok", [("ozgun", 64), ("ozgun-16", 16), ("pico-8", 16), ("gameboy-4", 4)])
def test_sprite_paleti_ve_boyu(tmp_path, palet, en_cok):
    g = figur_png(tmp_path / "toon.png")
    meta = piksel.pikselle(g, tmp_path / "p.png", boy=160, palet=palet)
    a = np.asarray(Image.open(tmp_path / "p.png"))
    assert a.shape[:2] == (256, 256)
    assert set(np.unique(a[..., 3])) <= {0, 255}  # hard alpha
    renk = np.unique(a[a[..., 3] == 255][:, :3], axis=0)
    assert 1 < len(renk) <= en_cok and meta["renk_sayisi"] == len(renk)
    if not palet.startswith("ozgun"):
        pal = {tuple(c) for c in piksel.hex_oku(piksel.PALET_KLASORU / f"{palet}.hex")}
        assert {tuple(c) for c in renk} <= pal
    ys = np.nonzero(a[..., 3].any(1))[0]
    # body (without the 1 px outline) is `boy` tall, feet on the feet line
    assert 160 <= ys.max() - ys.min() + 1 <= 163
    assert abs(ys.max() - meta["ayak_y"]) <= 1


def test_cizgi_koyu_ve_kapali(tmp_path):
    g = figur_png(tmp_path / "toon.png")
    piksel.pikselle(g, tmp_path / "c.png", boy=80, palet="ozgun", cizgi=True)
    piksel.pikselle(g, tmp_path / "n.png", boy=80, palet="ozgun", cizgi=False)
    c, n = np.asarray(Image.open(tmp_path / "c.png")), np.asarray(Image.open(tmp_path / "n.png"))
    halka = (c[..., 3] == 255) & (n[..., 3] == 0)
    assert halka.sum() > 50
    lum = c[halka][:, :3] @ np.array([0.299, 0.587, 0.114])
    assert lum.mean() < 90  # the outline is a dark shade


def test_paletler_ve_dogrulama():
    ids = [p["id"] for p in piksel.paletler()]
    assert ids[:3] == ["ozgun", "ozgun-32", "ozgun-16"]
    assert {"pico-8", "sweetie-16", "endesga-32", "gameboy-4"} <= set(ids)
    assert piksel.palet_gecerli("pico-8") and piksel.palet_gecerli("ozgun")
    for kotu in ("../atolye", "yok", "..\\x", ""):
        assert not piksel.palet_gecerli(kotu)


def test_bos_gorsel_hata(tmp_path):
    Image.new("RGBA", (100, 100), (0, 0, 0, 0)).save(tmp_path / "bos.png")
    with pytest.raises(ValueError):
        piksel.pikselle(tmp_path / "bos.png", tmp_path / "x.png")
    with pytest.raises(ValueError):
        piksel.pikselle(figur_png(tmp_path / "t.png"), tmp_path / "x.png", palet="yok")
