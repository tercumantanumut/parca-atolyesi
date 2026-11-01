"""The HTTP API end to end, with tests/sahte_adim.py standing in for the GPU steps (toon/piksel/ayrik are real)."""
import io
import json
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest
from PIL import Image

from tests.conftest import gerek_blender

SAHTE = Path(__file__).resolve().parent / "sahte_adim.py"


class SahteGPU:
    def __init__(self, toplam=31.8):
        self.toplam = toplam

    def oku(self, en_fazla_yas=0.3):
        return {"ad": "Sahte RTX", "toplam": self.toplam, "kullanilan": 2.0, "bos": self.toplam - 2.0}


@pytest.fixture
def sunucu(ayar_dosyasi, monkeypatch):
    from atolye import ayar
    from atolye import isler as isler_mod
    from atolye import sunucu as sunucu_mod

    a = ayar.yukle()
    A = isler_mod.Atolye(a, gpu=SahteGPU(), adim_komutu=lambda adim, argv: [sys.executable, str(SAHTE), adim, *argv],
                         isci_komutu=lambda: [sys.executable, str(SAHTE), "isci"])
    gercek = A.sistem

    def sistem():
        d = gercek()
        d["modeller"] = {"sekil": True, "doku": True, "parcalar": True, "xpart": True, "2mv": False}
        d["ortam"] = {"venv": True, "kod": True, "eklentiler": True}
        return d

    monkeypatch.setattr(A, "sistem", sistem)
    srv = sunucu_mod.sun("127.0.0.1", 0, web=Path(ayar_dosyasi).parent / "web", atolye=A)
    (Path(ayar_dosyasi).parent / "web").mkdir()
    (Path(ayar_dosyasi).parent / "web" / "index.html").write_text("<h1>tezgah</h1>", encoding="utf-8")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    taban = f"http://127.0.0.1:{srv.server_address[1]}"
    yield taban, A
    for isci in A.isciler.values():
        isci.kapat()
    srv.shutdown()
    srv.server_close()


def iste(url, veri=None, yontem=None, basliklar=None):
    req = urllib.request.Request(url, data=veri, method=yontem, headers=basliklar or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def gorsel_bytes():
    b = io.BytesIO()
    Image.new("RGB", (128, 256), (240, 240, 240)).save(b, "PNG")
    return b.getvalue()


def is_baslat(taban, **alanlar):
    sinir = uuid.uuid4().hex
    parcalar = []
    for k, v in alanlar.items():
        parcalar.append(f'--{sinir}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parcalar.append(f'--{sinir}\r\nContent-Disposition: form-data; name="on"; filename="kahraman.png"\r\n'
                    f'Content-Type: image/png\r\n\r\n'.encode() + gorsel_bytes() + b"\r\n")
    govde = b"".join(parcalar) + f"--{sinir}--\r\n".encode()
    return iste(f"{taban}/api/is", govde, "POST", {"Content-Type": f"multipart/form-data; boundary={sinir}"})


def olaylari_oku(url, zaman=120):
    """Read SSE until bitti/hata; returns the parsed events."""
    out = []
    with urllib.request.urlopen(url, timeout=zaman) as r:
        assert r.headers["Content-Type"].startswith("text/event-stream")
        for ham in r:
            s = ham.decode("utf-8").rstrip("\n")
            if s.startswith("data: "):
                e = json.loads(s[6:])
                out.append(e)
                if e["tur"] in ("bitti", "hata"):
                    return out
    return out


def test_sistem_vram_web(sunucu):
    taban, _ = sunucu
    k, _, b = iste(f"{taban}/api/sistem")
    d = json.loads(b)
    assert k == 200 and d["gpu"] == {"ad": "Sahte RTX", "toplam_gb": 31.8, "bos_gb": 29.8}
    assert set(d["modeller"]) == {"sekil", "doku", "parcalar", "xpart", "2mv"} and "surum" in d
    assert any(p["id"] == "ozgun" for p in d["paletler"])
    k, _, b = iste(f"{taban}/api/vram")
    assert json.loads(b) == {"kullanilan_gb": 2.0, "toplam_gb": 31.8}
    k, h, b = iste(f"{taban}/")
    assert k == 200 and b"tezgah" in b and h["Content-Type"].startswith("text/html")
    assert iste(f"{taban}/../../atolye.toml")[0] == 404


def test_hatali_istekler(sunucu):
    taban, _ = sunucu
    k, _, b = is_baslat(taban, rota="ucan")
    assert k == 400 and json.loads(b)["hata"] == "gecersiz_rota"
    k, _, b = is_baslat(taban, piksel_boy="9999")
    assert json.loads(b)["hata"] == "gecersiz_piksel_boy"
    k, _, b = iste(f"{taban}/api/is", b"{}", "POST", {"Content-Type": "application/json"})
    assert k == 415
    assert iste(f"{taban}/api/is/20990101-000000-abcd")[0] == 404
    assert iste(f"{taban}/api/is/../../x")[0] == 404


@gerek_blender
def test_hafif_rota_uctan_uca(sunucu):
    taban, A = sunucu
    k, _, b = is_baslat(taban, rota="hafif", toon_aci="on", piksel_boy="80", palet="pico-8", tohum="7")
    assert k == 201
    jid = json.loads(b)["id"]
    olaylar = olaylari_oku(f"{taban}/api/is/{jid}/olaylar")
    assert olaylar[-1] == {"tur": "bitti"}
    son = {}
    for e in olaylar:
        if e["tur"] == "adim":
            assert set(e) >= {"adim", "durum", "ilerleme", "sure_sn", "tepe_vram_gb", "cikti"}
            son[e["adim"]] = e
    assert {a: son[a]["durum"] for a in son} == {"sekil": "bitti", "doku": "bitti", "parcalar": "atlandi",
                                                "ayrik": "atlandi", "xpart": "atlandi", "toon": "bitti",
                                                "piksel": "bitti"}
    assert son["sekil"]["tepe_vram_gb"] == 1.5 and son["sekil"]["ilerleme"] == 1.0
    assert any(e["tur"] == "log" for e in olaylar)
    assert son["piksel"]["cikti"] == {"piksel_80": f"/cikti/{jid}/piksel_80.png"}

    k, _, b = iste(f"{taban}/api/is/{jid}")
    d = json.loads(b)
    assert d["durum"] == "bitti" and d["ayarlar"]["tohum"] == 7 and d["cikti"]["paket"].endswith("paket.zip")
    for rel in ("input_rgba.png", "shape.glb", "textured.glb", "toon_on.png", "piksel_80.png", "paket.zip"):
        k, h, _ = iste(f"{taban}/cikti/{jid}/{rel}")
        assert k == 200, rel
    assert iste(f"{taban}/cikti/{jid}/shape.glb")[1]["Content-Type"] == "model/gltf-binary"
    assert iste(f"{taban}/cikti/{jid}/../../atolye.toml")[0] == 404

    # a finished job replays a snapshot and ends with bitti
    tekrar = olaylari_oku(f"{taban}/api/is/{jid}/olaylar")
    assert tekrar[-1] == {"tur": "bitti"} and sum(e["tur"] == "adim" for e in tekrar) == 7

    # re-render 08 (synchronous), then 07 (+08 from the new still)
    k, _, b = iste(f"{taban}/api/is/{jid}/piksel", json.dumps({"boy": 128, "palet": "ozgun-16"}).encode(), "POST",
                   {"Content-Type": "application/json"})
    d = json.loads(b)
    assert k == 200 and d["adimlar"]["piksel"]["cikti"] == {"piksel_128": f"/cikti/{jid}/piksel_128.png"}
    assert Image.open(A.a.cikti / jid / "piksel_128.png").size == (208, 208)
    k, _, b = iste(f"{taban}/api/is/{jid}/toon", json.dumps({"aci": "yan"}).encode(), "POST",
                   {"Content-Type": "application/json"})
    d = json.loads(b)
    assert k == 200 and "toon_yan" in d["adimlar"]["toon"]["cikti"] and d["ayarlar"]["toon_aci"] == "yan"
    k, _, b = iste(f"{taban}/api/is/{jid}/toon", json.dumps({"aci": "ters"}).encode(), "POST",
                   {"Content-Type": "application/json"})
    assert k == 400

    lst = json.loads(iste(f"{taban}/api/isler")[2])
    assert lst[0]["id"] == jid and lst[0]["kapak"] == f"/cikti/{jid}/toon_yan.png"
    assert iste(f"{taban}/api/is/{jid}", yontem="DELETE")[0] == 200
    assert iste(f"{taban}/api/is/{jid}")[0] == 404 and not (A.a.cikti / jid).exists()


@gerek_blender
def test_parcali_rota_xpart_vram(sunucu):
    taban, A = sunucu
    jid = json.loads(is_baslat(taban, rota="parcali", xpart="true", piksel_boy="80")[2])["id"]
    olaylar = olaylari_oku(f"{taban}/api/is/{jid}/olaylar")
    assert olaylar[-1] == {"tur": "bitti"}
    d = json.loads(iste(f"{taban}/api/is/{jid}")[2])
    ad = d["adimlar"]
    assert ad["parcalar"]["durum"] == "bitti" and ad["ayrik"]["durum"] == "bitti"
    assert ad["xpart"]["durum"] == "bitti"  # runs on any card now (the fake step stands in for it)
    assert len(ad["ayrik"]["cikti"]["parts"]) == 4
    parts = json.loads(iste(f"{taban}/cikti/{jid}/parts.json")[2])
    assert len(parts["parts"]) == 4


def test_hata_sonraki_adimlari_atlar_ve_kuyruk(sunucu, monkeypatch):
    taban, A = sunucu
    monkeypatch.setenv("SAHTE_HATA", "doku")
    j1 = json.loads(is_baslat(taban)[2])["id"]
    j2 = json.loads(is_baslat(taban)[2])["id"]
    d2 = json.loads(iste(f"{taban}/api/is/{j2}")[2])
    assert d2["durum"] in ("bekliyor", "calisiyor", "hata")  # one GPU job at a time: j2 waits behind j1
    olaylar = olaylari_oku(f"{taban}/api/is/{j1}/olaylar")
    assert olaylar[-1]["tur"] == "hata" and olaylar[-1]["mesaj"] == "doku_hata"
    d = json.loads(iste(f"{taban}/api/is/{j1}")[2])
    assert d["adimlar"]["sekil"]["durum"] == "bitti" and d["adimlar"]["doku"]["durum"] == "hata"
    assert d["adimlar"]["toon"]["durum"] == "atlandi" and d["adimlar"]["toon"]["neden"] == "onceki_hata"
    assert "sahte hata" in d["adimlar"]["doku"]["hata_ozeti"]
    olaylari_oku(f"{taban}/api/is/{j2}/olaylar")
    t1 = A.isler[j1]
    t2 = A.isler[j2]
    assert t2.baslama >= t1.bitis  # strictly after


def test_sse_kaldigi_yerden(sunucu, monkeypatch):
    taban, A = sunucu
    monkeypatch.setenv("SAHTE_HATA", "sekil")
    jid = json.loads(is_baslat(taban)[2])["id"]
    olaylari_oku(f"{taban}/api/is/{jid}/olaylar")
    j = A.isler[jid]
    orta = j.olaylar[len(j.olaylar) // 2][0]
    req = urllib.request.Request(f"{taban}/api/is/{jid}/olaylar", headers={"Last-Event-ID": str(orta)})
    ids = []
    with urllib.request.urlopen(req, timeout=30) as r:
        for ham in r:
            s = ham.decode().strip()
            if s.startswith("id: "):
                ids.append(int(s[4:]))
            if s.startswith("data: ") and json.loads(s[6:])["tur"] == "hata":
                break
    assert ids and ids[0] == orta + 1 and ids == sorted(ids)


@gerek_blender
def test_hazir_mesh_ile_is(sunucu):
    """A ready GLB skips 01 (and 02); 07-08 run on it. No model needed for the light route."""
    from tests.sahte_adim import figur

    taban, A = sunucu
    m, _ = figur()
    glb = m.export(file_type="glb")
    sinir = uuid.uuid4().hex
    govde = (f'--{sinir}\r\nContent-Disposition: form-data; name="rota"\r\n\r\nhafif\r\n'
             f'--{sinir}\r\nContent-Disposition: form-data; name="mesh"; filename="figur.glb"\r\n'
             f'Content-Type: model/gltf-binary\r\n\r\n').encode() + glb + f"\r\n--{sinir}--\r\n".encode()
    k, _, b = iste(f"{taban}/api/is", govde, "POST", {"Content-Type": f"multipart/form-data; boundary={sinir}"})
    assert k == 201, b
    jid = json.loads(b)["id"]
    assert olaylari_oku(f"{taban}/api/is/{jid}/olaylar")[-1] == {"tur": "bitti"}
    d = json.loads(iste(f"{taban}/api/is/{jid}")[2])
    assert d["adimlar"]["sekil"]["neden"] == "mesh_verildi" and d["adimlar"]["doku"]["durum"] == "atlandi"
    assert d["adimlar"]["piksel"]["durum"] == "bitti" and d["cikti"]["shape"] == f"/cikti/{jid}/shape.glb"
    assert d["girdi"]["ad"] == "figur"
    govde = b'--x\r\nContent-Disposition: form-data; name="rota"\r\n\r\nhafif\r\n--x--\r\n'
    k, _, b = iste(f"{taban}/api/is", govde, "POST", {"Content-Type": "multipart/form-data; boundary=x"})
    assert k == 400 and json.loads(b)["hata"] == "on_gorsel_gerekli"


def test_cors_yalniz_yerel(sunucu):
    taban, _ = sunucu
    _, h, _ = iste(f"{taban}/api/vram", basliklar={"Origin": "http://127.0.0.1:5173"})
    assert h["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
    _, h, _ = iste(f"{taban}/api/vram", basliklar={"Origin": "https://kotu.example"})
    assert h["Access-Control-Allow-Origin"] is None


@gerek_blender
def test_modelleri_bellekte_tut(sunucu):
    """The second job reuses the worker's kept models; with keeping off they are unloaded after the job."""
    taban, A = sunucu
    assert json.loads(iste(f"{taban}/api/ayar")[2]) == {"modelleri_tut": True}
    j1 = json.loads(is_baslat(taban)[2])["id"]
    olaylari_oku(f"{taban}/api/is/{j1}/olaylar")
    j2 = json.loads(is_baslat(taban)[2])["id"]
    olaylari_oku(f"{taban}/api/is/{j2}/olaylar")
    a1 = json.loads(iste(f"{taban}/api/is/{j1}")[2])["adimlar"]
    a2 = json.loads(iste(f"{taban}/api/is/{j2}")[2])["adimlar"]
    assert a1["sekil"]["bellek"] == "yuklendi" and a2["sekil"]["bellek"] == "bellekte"
    assert a2["doku"]["bellek"] == "bellekte" and a2["toon"].get("bellek") is None
    s = json.loads(iste(f"{taban}/api/sistem")[2])["bellek"]
    assert s["modelleri_tut"] is True and {m["ad"] for m in s["yuklu"]} == {"sekil_21", "doku"}

    k, _, b = iste(f"{taban}/api/ayar", json.dumps({"modelleri_tut": False}).encode(), "POST",
                   {"Content-Type": "application/json"})
    assert k == 200 and json.loads(b) == {"modelleri_tut": False}
    assert json.loads(iste(f"{taban}/api/sistem")[2])["bellek"]["yuklu"] == []
    j3 = json.loads(is_baslat(taban)[2])["id"]
    olaylari_oku(f"{taban}/api/is/{j3}/olaylar")
    a3 = json.loads(iste(f"{taban}/api/is/{j3}")[2])["adimlar"]
    assert a3["sekil"]["bellek"] == "yuklendi"
    assert json.loads(iste(f"{taban}/api/sistem")[2])["bellek"]["yuklu"] == []
    assert json.loads((A.a.veri / "durum.json").read_text())["modelleri_tut"] is False
