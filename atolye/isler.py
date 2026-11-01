"""Jobs: state, events (for SSE), persistence, and the runner that executes the steps one GPU job at a time.

Each job lives in <cikti>/<id>/ with is.json (its state) and every output file. The model steps 02-04 run in one
long-lived GPU worker (atolye/isci.py) that can keep their pipelines loaded between jobs ("modelleri_tut"); X-Part,
05, 07 and 08 run as their own processes (atolye/calis.py <adim>), X-Part after the worker unloaded everything. The steps print a small line
protocol (see stages/_ortak.py); tqdm percentages become step progress, other lines become log events.
"""
from __future__ import annotations

import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import modeller as modeller_mod
from .ayar import KOK, Ayar
from .gpu import GPU, TepeOrnekleyici
from .ihtiyac import IHTIYAC_GB, PAY_GB
from .stages import ADIMLAR
from .stages import piksel as piksel_mod

ROTALAR = ("hafif", "parcali")
ACILAR = ("on", "ucceyrek", "yan")
SON_DURUMLAR = ("bitti", "hata", "iptal")
OLAY_TAMPONU = 3000          # events kept in memory per job (for SSE resume)
LOG_OZETI = 200              # log lines replayed to a fresh SSE connection
TQDM = re.compile(r"^\s*(.*?)\s*:?\s*(\d{1,3})%\|")


# Model steps that run in a long-lived GPU worker, and which worker. Hunyuan3D-2.1 and Hunyuan3D-Part both have
# top-level packages called `utils` and `models`, so they cannot share one Python process: one worker per family.
ISCI_AILESI = {"sekil": "hy21", "doku": "hy21", "parcalar": "part"}
ISCI_ADIMLARI = tuple(ISCI_AILESI)


class SatirOkuyucu:
    """Lines (split on CR and LF, so tqdm updates count) from a byte stream; `dur` stops at a line starting with it."""

    def __init__(self, akis):
        self.akis, self.tampon = akis, b""
        self.son: str | None = None

    def satirlar(self, dur: str | None = None):
        while True:
            while b"\n" in self.tampon or b"\r" in self.tampon:
                ham, self.tampon = re.split(rb"[\r\n]", self.tampon, maxsplit=1)
                s = ham.decode("utf-8", errors="replace").rstrip()
                if not s:
                    continue
                if dur and s.startswith(dur):
                    self.son = s
                    return
                yield s
            parca = self.akis.read1(4096) if hasattr(self.akis, "read1") else self.akis.read(4096)
            if not parca:
                self.son = None
                return
            self.tampon += parca


class GpuIsci:
    """Client side of atolye/isci.py: starts it on demand, sends one command at a time, restarts it if it died."""

    def __init__(self, komut):
        self.komut, self.p, self.okuyucu = komut, None, None
        self.kilit = threading.Lock()
        self.son_kod: int | None = None
        self.yuklu: list[dict] = []

    def _hazirla(self) -> None:
        if self.p is not None and self.p.poll() is None:
            return
        self.yuklu = []
        self.p = subprocess.Popen(self.komut(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, cwd=str(KOK),
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.okuyucu = SatirOkuyucu(self.p.stdout)
        for _ in self.okuyucu.satirlar(dur="@@hazir"):
            pass

    def calistir(self, komut: dict):
        """Send a command; yields its output lines; afterwards son_kod is its exit code (None if the worker died)."""
        self.kilit.acquire()
        try:
            self._hazirla()
            self.son_kod = None
            try:
                self.p.stdin.write((json.dumps(komut) + "\n").encode("utf-8"))
                self.p.stdin.flush()
            except OSError:
                return
            for s in self.okuyucu.satirlar(dur="@@bitti"):
                if s.startswith("@@bellek "):
                    try:
                        self.yuklu = json.loads(s[9:])
                    except ValueError:
                        pass
                    continue
                yield s
            son = self.okuyucu.son
            self.son_kod = int(son.split()[1]) if son else None
            if son is None:
                self.yuklu = []
        finally:
            self.kilit.release()

    def bosalt(self, neden: str = "istek", bekle: bool = True) -> bool:
        """Unload every kept model. Without bekle, gives up at once if a step is running."""
        if self.p is None or self.p.poll() is not None:
            self.yuklu = []
            return True
        if not self.kilit.acquire(blocking=bekle):
            return False
        self.kilit.release()
        for _ in self.calistir({"komut": "bosalt", "neden": neden}):
            pass
        return True

    def kapat(self) -> None:
        if self.p is not None and self.p.poll() is None:
            self.p.kill()


class GirdiHatasi(ValueError):
    """Bad request: `kod` is a stable id for the web side; `ayrinti` optional data."""

    def __init__(self, kod: str, ayrinti=None, durum: int = 400):
        super().__init__(kod)
        self.kod, self.ayrinti, self.durum = kod, ayrinti, durum


def yeni_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def gecerli_id(i: str) -> bool:
    return bool(re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", i or ""))


def bool_oku(v, varsayilan=False) -> bool:
    if v is None or v == "":
        return varsayilan
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "evet", "on", "yes")


def boy_oku(v, varsayilan=160) -> int:
    if v is None or v == "":
        return varsayilan
    try:
        b = int(float(v))
    except (TypeError, ValueError):
        raise GirdiHatasi("gecersiz_piksel_boy")
    if not 16 <= b <= 512:
        raise GirdiHatasi("gecersiz_piksel_boy", {"en_az": 16, "en_cok": 512})
    return b


def ayarlari_dogrula(f: dict) -> dict:
    """Form fields of POST /api/is -> normalised settings (raises GirdiHatasi)."""
    rota = (f.get("rota") or "hafif").strip()
    if rota not in ROTALAR:
        raise GirdiHatasi("gecersiz_rota", {"secenekler": list(ROTALAR)})
    aci = (f.get("toon_aci") or "ucceyrek").strip()
    if aci not in ACILAR:
        raise GirdiHatasi("gecersiz_toon_aci", {"secenekler": list(ACILAR)})
    palet = (f.get("palet") or "ozgun").strip()
    if not piksel_mod.palet_gecerli(palet):
        raise GirdiHatasi("gecersiz_palet")
    try:
        tohum = int(f.get("tohum") or 1234)
    except ValueError:
        raise GirdiHatasi("gecersiz_tohum")
    try:
        parca_tohum = int(f.get("parca_tohum") or 42)
    except ValueError:
        raise GirdiHatasi("gecersiz_tohum")
    return {"rota": rota, "xpart": bool_oku(f.get("xpart")), "doku": bool_oku(f.get("doku"), True),
            "birlestir": bool_oku(f.get("birlestir")), "parca_tohum": parca_tohum,
            "toon_aci": aci, "piksel_boy": boy_oku(f.get("piksel_boy")), "palet": palet, "tohum": tohum}


@dataclass
class Is:
    id: str
    dizin: Path
    ayarlar: dict
    olusturma: float = field(default_factory=time.time)
    durum: str = "bekliyor"
    adimlar: dict = field(default_factory=dict)
    girdi: dict = field(default_factory=dict)
    cikti: dict = field(default_factory=dict)
    mesaj: str | None = None
    baslama: float | None = None
    bitis: float | None = None
    # runtime only
    olaylar: list = field(default_factory=list, repr=False)
    sayac: int = 0
    kosul: threading.Condition = field(default_factory=threading.Condition, repr=False)
    kilit: threading.Lock = field(default_factory=threading.Lock, repr=False)  # re-renders vs the runner
    surec: subprocess.Popen | None = field(default=None, repr=False)
    iptal: bool = False

    def url(self, rel: str) -> str:
        return f"/cikti/{self.id}/{rel}"

    # ---- events
    def yayinla(self, olay: dict) -> None:
        with self.kosul:
            self.sayac += 1
            self.olaylar.append((self.sayac, olay))
            if len(self.olaylar) > OLAY_TAMPONU:
                del self.olaylar[: len(self.olaylar) - OLAY_TAMPONU]
            self.kosul.notify_all()

    def log(self, satir: str) -> None:
        satir = satir.rstrip()
        if satir:
            self.yayinla({"tur": "log", "satir": satir})
            with open(self.dizin / "is.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%H:%M:%S ") + satir + "\n")

    def adim_olayi(self, adim: str) -> dict:
        return {"tur": "adim", **self.adimlar[adim]}

    def adim_guncelle(self, adim: str, kaydet: bool = True, **kw) -> None:
        self.adimlar[adim].update(kw)
        self.yayinla(self.adim_olayi(adim))
        if kaydet:
            self.kaydet()

    def anlik(self) -> list[dict]:
        """What a fresh SSE connection gets first: every step's state, the recent log, and the end state."""
        with self.kosul:
            loglar = [o for _, o in self.olaylar if o["tur"] == "log"][-LOG_OZETI:]
        out = [self.adim_olayi(a) for a in ADIMLAR if a in self.adimlar] + loglar
        if self.durum == "bitti":
            out.append({"tur": "bitti"})
        elif self.durum in ("hata", "iptal"):
            out.append({"tur": "hata", "mesaj": self.mesaj or self.durum})
        return out

    # ---- state
    def sozluk(self) -> dict:
        sure = None
        if self.baslama:
            son = self.bitis or (time.time() if self.durum == "calisiyor" else None)
            sure = round(son - self.baslama, 1) if son else None
        return {"id": self.id, "olusturma": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.olusturma)),
                "durum": self.durum, "mesaj": self.mesaj, "ayarlar": self.ayarlar, "rota": self.ayarlar["rota"],
                "girdi": self.girdi, "adimlar": {a: self.adimlar[a] for a in ADIMLAR if a in self.adimlar},
                "cikti": self.cikti, "sure_sn": sure, "son_olay": self.sayac}

    def kaydet(self) -> None:
        d = self.sozluk()
        d.update(olusturma_ts=self.olusturma, baslama=self.baslama, bitis=self.bitis)
        tmp = self.dizin / "is.json.tmp"
        tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.dizin / "is.json")

    @classmethod
    def yukle(cls, dizin: Path) -> "Is":
        d = json.loads((dizin / "is.json").read_text(encoding="utf-8"))
        j = cls(id=d["id"], dizin=dizin, ayarlar=d["ayarlar"], olusturma=d.get("olusturma_ts", time.time()),
                durum=d["durum"], adimlar=d.get("adimlar", {}), girdi=d.get("girdi", {}), cikti=d.get("cikti", {}),
                mesaj=d.get("mesaj"), baslama=d.get("baslama"), bitis=d.get("bitis"))
        log = dizin / "is.log"
        if log.exists():
            for s in log.read_text(encoding="utf-8", errors="replace").splitlines()[-LOG_OZETI:]:
                j.sayac += 1
                j.olaylar.append((j.sayac, {"tur": "log", "satir": s[9:] if s[2:3] == ":" else s}))
        return j

    def ozet(self) -> dict:
        """One row of GET /api/isler."""
        d = self.sozluk()
        d.pop("adimlar")
        d["adim_durumlari"] = {a: s["durum"] for a, s in self.adimlar.items()}
        aci = self.ayarlar.get("toon_aci")
        kapak = None
        for rel in (f"toon_{aci}.png", "input_rgba.png"):
            if (self.dizin / rel).exists():
                kapak = self.url(rel)
                break
        d["kapak"] = kapak
        return d


def plan(ayarlar: dict, sistem: dict) -> dict[str, dict]:
    """Initial step states: which steps run and which are skipped (with a stable reason id)."""
    adimlar = {a: {"adim": a, "durum": "bekliyor", "ilerleme": 0.0, "sure_sn": None, "tepe_vram_gb": None,
                   "cikti": {}} for a in ADIMLAR}

    def atla(a, neden):
        adimlar[a].update(durum="atlandi", neden=neden)

    if not sistem.get("blender", True):
        atla("toon", "blender_yok")
        atla("piksel", "blender_yok")
    if not ayarlar.get("doku", True):
        atla("doku", "secilmedi")
    if ayarlar["rota"] != "parcali":
        for a in ("parcalar", "ayrik", "xpart"):
            atla(a, "rota")
    elif not ayarlar.get("xpart"):
        atla("xpart", "secilmedi")
    elif not sistem.get("modeller", {}).get("xpart"):
        atla("xpart", "model_yok")
    # X-Part runs on any card: below its need Windows spills into shared memory (slow); the panel warns first
    return adimlar


class Atolye:
    """All jobs + the runner thread (one GPU job at a time, FIFO)."""

    def __init__(self, a: Ayar, gpu: GPU | None = None, adim_komutu=None, isci_komutu=None):
        self.a = a
        self.gpu = gpu or GPU()
        komut = isci_komutu or (lambda: [str(a.venv_python), "-I", str(KOK / "atolye" / "calis.py"), "isci"])
        self.isciler = {aile: GpuIsci(komut) for aile in sorted(set(ISCI_AILESI.values()))}
        self._durum_dosyasi = a.veri / "durum.json"
        self.isci_is: tuple[str, str] | None = None  # (job id, worker family) while a worker runs a step
        self.modelleri_tut = bool(self._durum().get("modelleri_tut",
                                                    a.ham.get("bellek", {}).get("modelleri_tut", True)))
        self.isler: dict[str, Is] = {}
        self.kuyruk: queue.Queue[str] = queue.Queue()
        self.kilit = threading.Lock()
        self._adim_komutu = adim_komutu or self._varsayilan_komut
        a.cikti.mkdir(parents=True, exist_ok=True)
        self._diskten_yukle()
        self._kosucu = threading.Thread(target=self._dongu, daemon=True, name="kosucu")
        self._kosucu.start()

    # ---------------------------------------------------------- settings changed from the panel
    def _durum(self) -> dict:
        try:
            return json.loads(self._durum_dosyasi.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def ayar(self) -> dict:
        return {"modelleri_tut": self.modelleri_tut}

    def ayar_degistir(self, d: dict) -> dict:
        if "modelleri_tut" in d:
            self.modelleri_tut = bool_oku(d["modelleri_tut"], True)
            kalici = {**self._durum(), "modelleri_tut": self.modelleri_tut}
            self._durum_dosyasi.parent.mkdir(parents=True, exist_ok=True)
            self._durum_dosyasi.write_text(json.dumps(kalici), encoding="utf-8")
            if not self.modelleri_tut:
                for isci in self.isciler.values():
                    isci.bosalt("tutma_kapali", bekle=False)  # a running job unloads at its end instead
        return self.ayar()

    def yuklu(self) -> list[dict]:
        return [m for isci in self.isciler.values() for m in isci.yuklu]

    def bosalt(self, neden: str, haric: str | None = None) -> None:
        for aile, isci in self.isciler.items():
            if aile != haric:
                isci.bosalt(neden)

    def yer_ac(self, aile: str, model: str) -> None:
        """Before a worker step: if the card's free VRAM is below the model's need, the OTHER worker unloads its
        kept models (the worker running the step manages its own, least recently used first)."""
        tutulan = sum(m["gb"] for m in self.isciler[aile].yuklu if m["ad"] == model)
        lazim = IHTIYAC_GB.get(model, IHTIYAC_GB.get(model.split("_")[0], 8.0)) - tutulan + PAY_GB
        for diger, isci in self.isciler.items():
            g = self.gpu.oku(0)
            if diger == aile or not isci.yuklu or (g and g["bos"] >= lazim):
                continue
            isci.bosalt("yer_ac")

    # ---------------------------------------------------------- system
    def ortam_hazir(self) -> dict:
        kod = all((self.a.kod / k).exists() for k in ("Hunyuan3D-2.1", "Hunyuan3D-Part"))
        ext = any(self.a.derleme.glob("custom_rasterizer_kernel*")) and any(self.a.derleme.glob("mesh_inpaint_processor*"))
        return {"venv": self.a.venv_python.exists(), "kod": kod, "eklentiler": bool(ext)}

    def sistem(self) -> dict:
        from . import __version__

        g = self.gpu.oku()
        gpu = {"ad": g["ad"], "toplam_gb": round(g["toplam"], 2), "bos_gb": round(g["bos"], 2)} if g else None
        return {"gpu": gpu, "blender": bool(self.a.blender and Path(self.a.blender).exists()),
                "modeller": modeller_mod.durum(self.a.modeller), "surum": __version__,
                # additions (design/PLAN.md, "API additions")
                "ortam": self.ortam_hazir(), "xpart_ihtiyac_gb": IHTIYAC_GB["xpart"],
                "bellek": {"modelleri_tut": self.modelleri_tut, "yuklu": self.yuklu()},
                "paletler": piksel_mod.paletler(), "kuyruk": self.kuyruk.qsize()}

    def vram(self) -> dict:
        g = self.gpu.oku(0.2)
        if not g:
            return {"kullanilan_gb": None, "toplam_gb": None}
        return {"kullanilan_gb": round(g["kullanilan"], 2), "toplam_gb": round(g["toplam"], 2)}

    # ---------------------------------------------------------- jobs
    def _diskten_yukle(self) -> None:
        for d in sorted(self.a.cikti.iterdir()):
            if not (d / "is.json").exists() or not gecerli_id(d.name):
                continue
            try:
                j = Is.yukle(d)
            except (OSError, ValueError, KeyError):
                continue
            if j.durum == "calisiyor":  # the server stopped while it ran
                j.durum, j.mesaj = "hata", "sunucu_durdu"
                j.bitis = j.bitis or max((d / f).stat().st_mtime for f in ("is.json", "is.log") if (d / f).exists())
                for s in j.adimlar.values():
                    if s["durum"] == "calisiyor":
                        s["durum"] = "hata"
                j.kaydet()
            self.isler[j.id] = j
            if j.durum == "bekliyor":
                self.kuyruk.put(j.id)

    def olustur(self, alanlar: dict, on: tuple[str, bytes] | None, arka: tuple[str, bytes] | None = None,
                mesh: tuple[str, bytes] | None = None) -> Is:
        """New job from an image (`on`, optional `arka`), or from a ready mesh (`mesh`: GLB/OBJ in glTF axes, Y up,
        front +Z), which skips step 01 (and 02 unless doku=true with an `on` image as the paint reference)."""
        if on is None and mesh is None:
            raise GirdiHatasi("on_gorsel_gerekli")
        if mesh is not None and "doku" not in alanlar:
            alanlar = {**alanlar, "doku": "false"}
        ayarlar = ayarlari_dogrula(alanlar)
        if mesh is not None and ayarlar["doku"] and on is None:
            raise GirdiHatasi("on_gorsel_gerekli")
        sis = self.sistem()
        m = sis["modeller"]
        gerek = (["sekil"] if mesh is None else []) + (["doku"] if ayarlar["doku"] else []) +             (["parcalar"] if ayarlar["rota"] == "parcali" else [])
        eksik = [k for k in gerek if not m.get(k)]
        if eksik:
            raise GirdiHatasi("model_yok", {"eksik": eksik}, 409)
        o = sis["ortam"]
        if gerek and not all(o.values()):
            raise GirdiHatasi("ortam_yok", o, 409)
        ayarlar["arka"] = arka is not None
        ayarlar["model"] = "mesh" if mesh is not None else ("2mv" if arka is not None and m.get("2mv") else "2.1")
        jid = yeni_id()
        d = self.a.cikti / jid
        d.mkdir(parents=True)
        try:
            j = Is(id=jid, dizin=d, ayarlar=ayarlar)
            if mesh is not None:
                dokulu = self._mesh_yaz(d, *mesh)
                if dokulu:
                    ayarlar["doku"] = False
                j.cikti["shape"] = j.url("shape.glb")
                if dokulu:
                    j.cikti["textured"] = j.url("textured.glb")
                j.girdi["mesh"] = j.cikti["shape"]
                j.girdi["ad"] = Path(mesh[0] or "mesh").stem[:80]
            j.adimlar = plan(ayarlar, sis)
            if mesh is not None:
                j.adimlar["sekil"].update(durum="atlandi", neden="mesh_verildi")
                if not ayarlar["doku"]:
                    j.adimlar["doku"].update(durum="atlandi", neden="dokulu_mesh" if dokulu else "secilmedi")
            if on is not None:
                j.girdi["on"] = j.url(self._gorsel_yaz(d, "girdi_on", *on))
                j.girdi["ad"] = j.girdi.get("ad") or Path(on[0] or "gorsel").stem[:80]
            if arka is not None:
                j.girdi["arka"] = j.url(self._gorsel_yaz(d, "girdi_arka", *arka))
                if ayarlar["model"] == "2.1":
                    j.log("2mv modeli kurulu değil: şekil yalnız ön görselden (2.1)")
        except Exception:
            shutil.rmtree(d, ignore_errors=True)
            raise
        j.kaydet()
        with self.kilit:
            self.isler[jid] = j
        self.kuyruk.put(jid)
        return j

    @staticmethod
    def _mesh_yaz(d: Path, dosya_adi: str, veri: bytes) -> bool:
        """Save an uploaded mesh as shape.glb (and textured.glb when it has a base colour texture)."""
        from io import BytesIO

        import trimesh

        uz = Path(dosya_adi or "x.glb").suffix.lower().lstrip(".")
        if uz not in ("glb", "gltf", "obj", "ply", "stl"):
            raise GirdiHatasi("gecersiz_mesh", {"turler": ["glb", "obj", "ply", "stl"]})
        try:
            s = trimesh.load(BytesIO(veri), file_type=uz, process=False)
            geoms = list(s.geometry.values()) if isinstance(s, trimesh.Scene) else [s]
            yuz = sum(len(g.faces) for g in geoms if hasattr(g, "faces"))
        except Exception:
            raise GirdiHatasi("gecersiz_mesh")
        if yuz == 0:
            raise GirdiHatasi("gecersiz_mesh")
        if uz == "glb":
            (d / "shape.glb").write_bytes(veri)
        else:
            s.export(d / "shape.glb")
        dokulu = any(getattr(getattr(g.visual, "material", None), "baseColorTexture", None) is not None
                     or getattr(getattr(g.visual, "material", None), "image", None) is not None
                     for g in geoms if hasattr(g, "visual"))
        if dokulu:
            shutil.copyfile(d / "shape.glb", d / "textured.glb")
        return dokulu

    @staticmethod
    def _gorsel_yaz(d: Path, ad: str, dosya_adi: str, veri: bytes) -> str:
        from io import BytesIO

        from PIL import Image

        try:
            im = Image.open(BytesIO(veri))
            im.load()
        except Exception:
            raise GirdiHatasi("gecersiz_gorsel")
        if im.width < 64 or im.height < 64 or im.width * im.height > 64e6:
            raise GirdiHatasi("gecersiz_gorsel_boyutu")
        rel = f"{ad}.png"
        im.save(d / rel)
        return rel

    def al(self, jid: str) -> Is | None:
        return self.isler.get(jid) if gecerli_id(jid) else None

    def liste(self) -> list[dict]:
        return [j.ozet() for j in sorted(self.isler.values(), key=lambda j: -j.olusturma)]

    def sil(self, jid: str) -> bool:
        j = self.al(jid)
        if j is None:
            return False
        j.iptal = True
        if j.surec and j.surec.poll() is None:
            j.surec.kill()
        if self.isci_is and self.isci_is[0] == jid:  # its step runs in a GPU worker: stop it (models reload later)
            self.isciler[self.isci_is[1]].kapat()
        with j.kilit:
            with self.kilit:
                self.isler.pop(jid, None)
            if j.durum not in SON_DURUMLAR:
                j.durum, j.mesaj = "iptal", "silindi"
                j.yayinla({"tur": "hata", "mesaj": "silindi"})
            shutil.rmtree(j.dizin, ignore_errors=True)
        return True

    def sira(self, j: Is) -> int | None:
        """Position in the queue (1 = next), None if not waiting."""
        if j.durum != "bekliyor":
            return None
        bekleyen = sorted((x for x in self.isler.values() if x.durum == "bekliyor"), key=lambda x: x.olusturma)
        return next((i + 1 for i, x in enumerate(bekleyen) if x.id == j.id), None)

    # ---------------------------------------------------------- runner
    def _dongu(self) -> None:
        while True:
            jid = self.kuyruk.get()
            j = self.isler.get(jid)
            if j is None or j.iptal or j.durum != "bekliyor":
                continue
            try:
                self.calistir(j)
                if not self.modelleri_tut:
                    self.bosalt("tutma_kapali")
            except Exception as e:  # never kill the runner
                j.durum, j.mesaj, j.bitis = "hata", f"ic_hata: {e}", time.time()
                j.log(f"iç hata: {e!r}")
                j.yayinla({"tur": "hata", "mesaj": j.mesaj})
                j.kaydet()

    def _varsayilan_komut(self, adim: str, argv: list[str]) -> list[str]:
        return [str(self.a.venv_python), "-I", str(KOK / "atolye" / "calis.py"), adim, *argv]

    def adim_argv(self, j: Is, adim: str) -> list[str]:
        d, ay = j.dizin, j.ayarlar
        if adim == "sekil":
            argv = ["--on", str(d / "girdi_on.png"), "--cikti", str(d), "--tohum", str(ay["tohum"])]
            if ay.get("model") == "2mv":
                argv += ["--arka", str(d / "girdi_arka.png")]
            return argv
        if adim == "doku":
            g = d / "input_rgba.png" if (d / "input_rgba.png").exists() else d / "girdi_on.png"
            return ["--gorsel", str(g), "--mesh", str(d / "shape.glb"), "--cikti", str(d)]
        if adim == "parcalar":
            return ["--mesh", str(d / "shape.glb"), "--cikti", str(d / "p3sam"),
                    "--tohum", str(ay.get("parca_tohum", 42))] + (["--birlestir"] if ay.get("birlestir") else [])
        if adim == "ayrik":
            return ["--p3sam", str(d / "p3sam"), "--hedef", str(self.ana_mesh(j)), "--cikti", str(d)]
        if adim == "xpart":
            return ["--mesh", str(d / "shape.glb"), "--cikti", str(d / "xpart")]
        if adim == "toon":
            return ["--girdi", str(self.ana_mesh(j)), "--cikti", str(d / f"toon_{ay['toon_aci']}.png"),
                    "--aci", ay["toon_aci"]]
        if adim == "piksel":
            return ["--girdi", str(d / f"toon_{ay['toon_aci']}.png"), "--cikti", str(d / f"piksel_{ay['piksel_boy']}.png"),
                    "--boy", str(ay["piksel_boy"]), "--palet", ay["palet"]]
        raise KeyError(adim)

    @staticmethod
    def ana_mesh(j: Is) -> Path:
        t = j.dizin / "textured.glb"
        return t if t.exists() else j.dizin / "shape.glb"

    def adim_ciktisi(self, j: Is, adim: str) -> dict:
        d, ay = j.dizin, j.ayarlar
        var = lambda rel: (d / rel).exists()  # noqa: E731
        u = j.url
        if adim == "sekil":
            c = {"input_rgba": u("input_rgba.png"), "shape": u("shape.glb")}
            if var("input_back_rgba.png"):
                c["input_back_rgba"] = u("input_back_rgba.png")
            return c
        if adim == "doku":
            return {"textured": u("textured.glb")}
        if adim == "parcalar":
            return {"p3sam": u("p3sam/auto_mask_mesh_final.glb")}
        if adim == "ayrik":
            parts = sorted(p.name for p in (d / "parts").glob("part_*.glb"))
            return {"parts_json": u("parts.json"), "parts_glb": u("parts.glb"), "parts": [u(f"parts/{p}") for p in parts]}
        if adim == "xpart":
            parts = sorted(p.name for p in (d / "xpart" / "parts").glob("part_*.glb"))
            return {"xpart_glb": u("xpart/parts.glb"), "xpart_explode": u("xpart/parts_explode.glb"),
                    "xpart_parts": [u(f"xpart/parts/{p}") for p in parts]}
        if adim == "toon":
            return {f"toon_{ay['toon_aci']}": u(f"toon_{ay['toon_aci']}.png")}
        if adim == "piksel":
            return {f"piksel_{ay['piksel_boy']}": u(f"piksel_{ay['piksel_boy']}.png")}
        return {}

    def calistir(self, j: Is) -> None:
        j.durum, j.baslama, j.mesaj = "calisiyor", time.time(), None
        j.kaydet()
        j.log(f"iş başladı: rota={j.ayarlar['rota']} model={j.ayarlar.get('model')} tohum={j.ayarlar['tohum']}")
        for adim in ADIMLAR:
            if j.iptal:
                return
            if j.adimlar[adim]["durum"] == "atlandi":
                j.yayinla(j.adim_olayi(adim))
                continue
            with j.kilit:
                ok = self.adim_kos(j, adim)
            if not ok:
                if j.iptal:
                    return
                for a in ADIMLAR[ADIMLAR.index(adim) + 1:]:
                    if j.adimlar[a]["durum"] == "bekliyor":
                        j.adimlar[a]["durum"] = "atlandi"
                        j.adimlar[a]["neden"] = "onceki_hata"
                j.durum, j.bitis = "hata", time.time()
                j.mesaj = j.mesaj or f"{adim}_hata"
                j.kaydet()
                j.yayinla({"tur": "hata", "mesaj": j.mesaj})
                return
        self.paketle(j)
        j.durum, j.bitis = "bitti", time.time()
        j.kaydet()
        j.log(f"iş bitti: {j.bitis - j.baslama:.0f} sn")
        j.yayinla({"tur": "bitti"})

    @staticmethod
    def adim_modeli(j: Is, adim: str) -> str:
        return {"sekil": "sekil_2mv" if j.ayarlar.get("model") == "2mv" else "sekil_21", "doku": "doku",
                "parcalar": "p3sam"}[adim]

    def sonraki_modeller(self, j: Is, adim: str) -> list[str]:
        """Model ids the job's later steps will ask the GPU worker for (kept loaded even with keeping off)."""
        out = []
        for a in ADIMLAR[ADIMLAR.index(adim) + 1:]:
            if j.adimlar[a]["durum"] != "bekliyor":
                continue
            if a == "doku":
                out.append("doku")
            elif a == "parcalar":
                out.append("p3sam")
        return out

    def adim_kos(self, j: Is, adim: str) -> bool:
        """Run one step (in the GPU worker, or as its own process); stream its progress and log. True on success."""
        j.adim_guncelle(adim, durum="calisiyor", ilerleme=0.0, sure_sn=None, tepe_vram_gb=None, cikti={}, bellek=None)
        argv = self.adim_argv(j, adim)
        t0 = time.time()
        ornek = TepeOrnekleyici(self.gpu)
        aile = ISCI_AILESI.get(adim)
        try:
            if aile:
                self.isci_is = (j.id, aile)
                self.yer_ac(aile, self.adim_modeli(j, adim))
                satirlar = self.isciler[aile].calistir({"komut": "adim", "adim": adim, "argv": argv,
                                                        "tut": self.modelleri_tut,
                                                        "sonraki": self.sonraki_modeller(j, adim)})
            else:
                if adim == "xpart":  # X-Part wants the whole card: the workers unload whatever they keep
                    self.bosalt("xpart")
                j.surec = subprocess.Popen(self._adim_komutu(adim, argv), stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, cwd=str(j.dizin),
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                satirlar = SatirOkuyucu(j.surec.stdout).satirlar()
            r = self._isle(j, adim, satirlar, t0)
        except OSError as e:
            ornek.bitir()
            self.isci_is = None
            j.mesaj = f"{adim}_baslatilamadi"
            j.log(f"{adim}: başlatılamadı: {e}")
            j.adim_guncelle(adim, durum="hata", sure_sn=round(time.time() - t0, 1))
            return False
        self.isci_is = None
        kod = self.isciler[aile].son_kod if aile else j.surec.wait()
        olculen = ornek.bitir()
        sure = round(time.time() - t0, 1)
        if j.iptal:
            return False
        sonuc = r["sonuc"]
        if kod != 0 or sonuc is None:
            j.mesaj = f"{adim}_vram_yetmedi" if r["oom"] else f"{adim}_hata"
            j.log(f"{adim}: hata (çıkış kodu {kod})")
            j.adim_guncelle(adim, durum="hata", sure_sn=sure, tepe_vram_gb=olculen or None,
                            hata_ozeti="\n".join(r["kuyruk"][-12:]))
            return False
        tepe = sonuc.get("tepe_vram_gb")
        j.adim_guncelle(adim, durum="bitti", ilerleme=1.0, sure_sn=sure,
                        tepe_vram_gb=tepe if tepe is not None else olculen,
                        cikti=self.adim_ciktisi(j, adim),
                        ayrinti={**sonuc, "tepe_vram_olculen_gb": olculen})
        return True

    def _isle(self, j: Is, adim: str, satirlar, t0: float) -> dict:
        """Turn a step's output lines into progress, log and model events."""
        faz = (0.0, 1.0)
        cubuklar: list[tuple[str, float, float]] = []  # tqdm bars the step announced: (label prefix, a, b)
        son_ilerleme, son_yayin = 0.0, 0.0
        r = {"sonuc": None, "kuyruk": [], "oom": False}
        son_cubuk = ""
        for s in satirlar:
            yeni = None
            if s.startswith("@@faz "):
                p = s.split()
                faz = (float(p[1]), float(p[2]))
                yeni = faz[0]
            elif s.startswith("@@cubuk "):
                p = s.split(maxsplit=3)
                cubuklar.append((p[3] if len(p) > 3 else "", float(p[1]), float(p[2])))
                continue
            elif s.startswith("@@ilerleme "):
                yeni = float(s.split()[1])
            elif s.startswith("@@sonuc "):
                try:
                    r["sonuc"] = json.loads(s[8:])
                except ValueError:
                    pass
                continue
            elif s.startswith("@@model "):
                p = s.split()  # @@model <id> yuklendi|bellekte|bosaltildi ...
                if len(p) >= 3 and p[2] in ("yuklendi", "bellekte"):
                    j.adim_guncelle(adim, kaydet=False, bellek=p[2])
                continue
            elif s.startswith("@@"):
                continue
            else:
                m = TQDM.search(s)
                if m:
                    oran = min(int(m.group(2)), 100) / 100
                    n = re.search(r"(\d+)/(\d+) \[([\d:]+)", s)
                    if oran >= 1 and (n is None or n.group(1) == n.group(2)):
                        # one compact log line per finished bar: "Volume Decoding 7134/7134 · 00:17"
                        ozet = f"{m.group(1).rstrip(':') or 'ilerleme'} {n.group(1)}/{n.group(2)} · {n.group(3)}" if n else s.strip()
                        if ozet != son_cubuk:
                            son_cubuk = ozet
                            j.log(f"[{adim}] {ozet}")
                    pencere = next(((ca, cb) for ad, ca, cb in cubuklar if m.group(1).startswith(ad)), None)
                    if pencere is None and not cubuklar:  # announced bars only, once there are any
                        pencere = faz
                    if pencere is not None:
                        yeni = pencere[0] + (pencere[1] - pencere[0]) * oran
                else:
                    r["oom"] = r["oom"] or "OutOfMemoryError" in s or "CUDA out of memory" in s
                    r["kuyruk"] = (r["kuyruk"] + [s])[-30:]
                    j.log(f"[{adim}] {s}")
            if yeni is not None and yeni > son_ilerleme:
                son_ilerleme = min(yeni, 0.999)
                if time.time() - son_yayin > 0.25:
                    son_yayin = time.time()
                    j.adim_guncelle(adim, kaydet=False, ilerleme=round(son_ilerleme, 3),
                                    sure_sn=round(time.time() - t0, 1))
        return r

    # ---------------------------------------------------------- re-render (steps 07 / 08)
    def yeniden(self, j: Is, toon_aci: str | None = None, boy=None, palet: str | None = None) -> dict:
        """Re-render toon (and the sprite from it) or only the sprite, with new settings. Synchronous."""
        if toon_aci is not None and toon_aci not in ACILAR:
            raise GirdiHatasi("gecersiz_toon_aci", {"secenekler": list(ACILAR)})
        if palet is not None and not piksel_mod.palet_gecerli(palet):
            raise GirdiHatasi("gecersiz_palet")
        boy = boy_oku(boy, j.ayarlar["piksel_boy"]) if boy is not None else None
        if not (j.dizin / "shape.glb").exists():
            raise GirdiHatasi("mesh_yok", None, 409)
        if j.durum not in SON_DURUMLAR and j.adimlar["toon"]["durum"] != "bitti":
            raise GirdiHatasi("is_bitmedi", None, 409)
        if not j.kilit.acquire(timeout=1):
            raise GirdiHatasi("is_mesgul", None, 409)
        try:
            if toon_aci:
                j.ayarlar["toon_aci"] = toon_aci
            if boy:
                j.ayarlar["piksel_boy"] = boy
            if palet:
                j.ayarlar["palet"] = palet
            j.kaydet()
            adimlar = (["toon"] if toon_aci or not (j.dizin / f"toon_{j.ayarlar['toon_aci']}.png").exists() else [])
            adimlar.append("piksel")
            for adim in adimlar:
                if not self.adim_kos(j, adim):
                    raise GirdiHatasi(f"{adim}_hata", {"ozet": j.adimlar[adim].get("hata_ozeti")}, 500)
            if j.durum == "bitti":
                self.paketle(j)
                j.kaydet()
                j.yayinla({"tur": "bitti"})
        finally:
            j.kilit.release()
        return j.sozluk()

    # ---------------------------------------------------------- download bundle
    PAKET_DISI = ("is.json", "is.json.tmp", "is.log", "paket.zip", "girdi_on.png", "girdi_arka.png")

    def paketle(self, j: Is) -> None:
        """paket.zip: every output a user keeps (meshes, parts, toon stills, sprites, json), not the intermediates."""
        hedef = j.dizin / "paket.zip"
        tmp = j.dizin / "paket.zip.tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(j.dizin.rglob("*")):
                rel = p.relative_to(j.dizin).as_posix()
                if not p.is_file() or rel in self.PAKET_DISI or rel.endswith(".tmp"):
                    continue
                ust = rel.split("/")[0]
                if ust in ("doku", "p3sam") or (ust == "xpart" and "/p3sam_post/" in f"/{rel}"):
                    continue  # model intermediates (remesh, masks, point clouds): large, not useful
                z.write(p, rel, compress_type=zipfile.ZIP_STORED if p.suffix in (".png", ".glb", ".jpg") else zipfile.ZIP_DEFLATED)
        os.replace(tmp, hedef)
        j.cikti["paket"] = j.url("paket.zip")
