import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from atolye import modeller
from kurulum import kur
from kurulum.kaynaklar import GRUPLAR, klasor


def test_git_blob_sha1(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"hello\n")
    assert kur.git_blob_sha1(f) == "ce013625030ba8dba906f756967f9e9ca394464a"  # `git hash-object`


def test_dogru_mu(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"abc" * 1000)
    sha = hashlib.sha256(f.read_bytes()).hexdigest()
    assert kur.dogru_mu(f, {"boyut": 3000, "sha256": sha})[0]
    assert not kur.dogru_mu(f, {"boyut": 3000, "sha256": "0" * 64})[0]
    assert not kur.dogru_mu(f, {"boyut": 2999, "sha256": sha})[0]
    assert kur.dogru_mu(f, {"boyut": 3000, "md5": hashlib.md5(f.read_bytes()).hexdigest()})[0]


class _Aralikli(BaseHTTPRequestHandler):
    veri = b""
    istekler: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        r = self.headers.get("Range")
        self.istekler.append(r)
        if r:
            a, b = r.split("=")[1].split("-")
            bas, son = int(a), (int(b) if b else len(self.veri) - 1)
            parca = self.veri[bas:son + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {bas}-{son}/{len(self.veri)}")
        else:
            parca = self.veri
            self.send_response(200)
        self.send_header("Content-Length", str(len(parca)))
        self.end_headers()
        self.wfile.write(parca)


@pytest.fixture
def http_sunucu():
    _Aralikli.veri = bytes(range(256)) * 4096
    _Aralikli.istekler = []
    s = ThreadingHTTPServer(("127.0.0.1", 0), _Aralikli)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}/f.bin"
    s.shutdown()


def test_indir_kaldigi_yerden_surer(tmp_path, http_sunucu):
    veri = _Aralikli.veri
    hedef = tmp_path / "m" / "f.bin"
    hedef.parent.mkdir()
    (hedef.parent / "f.bin.part").write_bytes(veri[:300000])  # an interrupted download
    dog = kur.Dogrulanan(tmp_path / "dog.json")
    b = {"boyut": len(veri), "sha256": hashlib.sha256(veri).hexdigest()}
    kur.indir_dosya(http_sunucu, hedef, b, dog)
    assert hedef.read_bytes() == veri
    assert _Aralikli.istekler == ["bytes=300000-"]
    # second call: verified from the cache, no request
    kur.indir_dosya(http_sunucu, hedef, b, kur.Dogrulanan(tmp_path / "dog.json"))
    assert len(_Aralikli.istekler) == 1


def test_indir_bozuk_ozet(tmp_path, http_sunucu):
    hedef = tmp_path / "f.bin"
    with pytest.raises(kur.KurulumHatasi):
        kur.indir_dosya(http_sunucu, hedef, {"boyut": len(_Aralikli.veri), "sha256": "0" * 64},
                        kur.Dogrulanan(tmp_path / "d.json"))
    assert not hedef.exists() and (tmp_path / "f.bin.bozuk").exists()


def test_secilen_ve_grup_durumu(tmp_path):
    liste = [{"type": "file", "path": "a/x.bin", "size": 3}, {"type": "file", "path": "a/y.bin", "size": 2},
             {"type": "file", "path": "b.txt", "size": 1}, {"type": "directory", "path": "a"}]
    assert [f["path"] for f in modeller.secilen(liste, ["a/"])] == ["a/x.bin", "a/y.bin"]
    assert [f["path"] for f in modeller.secilen(liste, ["b.txt", "c"])] == ["b.txt"]

    grup = {"model": "deneme", "hf": [("org/repo", "abc123", ["a/"])], "dosya": []}
    assert not modeller.grup_hazir(tmp_path, grup)  # no listing yet
    lp = modeller.liste_yolu(tmp_path, "org/repo", "abc123")
    lp.parent.mkdir(parents=True)
    lp.write_text(json.dumps(liste))
    assert not modeller.grup_hazir(tmp_path, grup)
    d = tmp_path / klasor("org/repo") / "a"
    d.mkdir(parents=True)
    (d / "x.bin").write_bytes(b"123")
    (d / "y.bin").write_bytes(b"12")
    assert modeller.grup_hazir(tmp_path, grup)


def test_kaynaklar_tutarli():
    assert [g["model"] for g in GRUPLAR] == ["sekil", "doku", "parcalar", "2mv", "xpart"]
    assert GRUPLAR[-1]["ad"] == "xpart" and not GRUPLAR[-1]["zorunlu"]  # X-Part last and optional
    for g in GRUPLAR:
        for repo, rev, desenler in g["hf"]:
            assert len(rev) == 40 and desenler


def test_tekerlekler_platforma_gore():
    from kurulum.kaynaklar import tekerlekler

    for p, uz in (("win32", "win_amd64.whl"), ("linux", "manylinux_2_28_x86_64.whl")):
        t = tekerlekler(p)
        assert len(t) == 2 and all(x["ad"].endswith(uz) and len(x["sha256"]) == 64 for x in t)
    assert tekerlekler("darwin") == []


def test_parcali_indirme_ve_devam(tmp_path, http_sunucu, monkeypatch):
    monkeypatch.setattr(kur, "PARCALI_ESIK", 1000)
    veri = _Aralikli.veri
    b = {"boyut": len(veri), "sha256": hashlib.sha256(veri).hexdigest()}
    hedef = tmp_path / "a.bin"
    kur.indir_dosya(http_sunucu, hedef, b, kur.Dogrulanan(tmp_path / "d.json"), baglanti=3)
    assert hedef.read_bytes() == veri and len(_Aralikli.istekler) == 3
    assert not (tmp_path / "a.bin.part.json").exists()

    # an interrupted segmented download: first segment done, second half done, third untouched
    hedef2 = tmp_path / "b.bin"
    part = tmp_path / "b.bin.part"
    n = len(veri)
    seg = [[0, n // 3, n // 3], [n // 3, 2 * n // 3, n // 2], [2 * n // 3, n, 2 * n // 3]]
    ham = bytearray(n)
    ham[0:n // 3] = veri[0:n // 3]
    ham[n // 3:n // 2] = veri[n // 3:n // 2]
    part.write_bytes(bytes(ham))
    (tmp_path / "b.bin.part.json").write_text(json.dumps({"toplam": n, "parcalar": seg}))
    _Aralikli.istekler = []
    kur.indir_dosya(http_sunucu, hedef2, b, kur.Dogrulanan(tmp_path / "d2.json"), baglanti=3)
    assert hedef2.read_bytes() == veri
    assert sorted(_Aralikli.istekler) == sorted([f"bytes={n // 2}-{2 * n // 3 - 1}", f"bytes={2 * n // 3}-{n - 1}"])

    # a prefix left by the single-stream mode becomes the start of the segments
    hedef3 = tmp_path / "c.bin"
    (tmp_path / "c.bin.part").write_bytes(veri[:500000])
    _Aralikli.istekler = []
    kur.indir_dosya(http_sunucu, hedef3, b, kur.Dogrulanan(tmp_path / "d3.json"), baglanti=2)
    assert hedef3.read_bytes() == veri and all(int(r.split("=")[1].split("-")[0]) >= 500000 for r in _Aralikli.istekler)
