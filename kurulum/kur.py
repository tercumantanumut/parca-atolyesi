"""Parça Atölyesi installer (stdlib only; any Python 3.11+). Normally started by kurulum/kur.ps1.

  python -I kurulum/kur.py ayar        create atolye.toml from atolye.ornek.toml (if missing)
  python -I kurulum/kur.py indir [grup ...] [--xpart-yok]
                                       download the model weights (resumable, verified); default: every group
  python -I kurulum/kur.py ortam       venv + torch wheels + packages + code clones + native extensions
  python -I kurulum/kur.py kod         only the pinned code clones
  python -I kurulum/kur.py dogrula [--tam]
                                       check every model file (size; with --tam also the hashes)
  python -I kurulum/kur.py hepsi [--xpart-yok]
                                       all of the above, the weights in a background thread
  python -I kurulum/kur.py baslat      start the server (http://127.0.0.1:8731) with the installed environment

Every step can be re-run: finished work is skipped and interrupted downloads continue where they stopped.
The log goes to <veri>/kayit/kurulum.log as well as the console.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from atolye import ayar as ayar_mod  # noqa: E402
from atolye.modeller import liste_yolu, secilen  # noqa: E402
from kurulum.kaynaklar import GRUPLAR, KODLAR, klasor, tekerlekler  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

_KAYIT_KILIT = threading.Lock()
_kayit_dosyasi: Path | None = None
UA = "parca-atolyesi-kurulum/0.1"


def kayit(msg: str) -> None:
    satir = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{threading.current_thread().name}] {msg}"
    with _KAYIT_KILIT:
        print(satir, flush=True)
        if _kayit_dosyasi:
            with open(_kayit_dosyasi, "a", encoding="utf-8") as f:
                f.write(satir + "\n")


class KurulumHatasi(RuntimeError):
    pass


# ---------------------------------------------------------------- download core
def _ozet(p: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def git_blob_sha1(p: Path) -> str:
    """The git object id of a file (how the Hub identifies small, non-LFS files)."""
    h = hashlib.sha1(f"blob {p.stat().st_size}\0".encode())
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class Dogrulanan:
    """Remembers which files were already hashed (path -> [size, mtime_ns, digest]), so re-runs don't re-hash 38 GB."""

    def __init__(self, yol: Path):
        self.yol = yol
        self.kilit = threading.Lock()
        try:
            self.d = json.loads(yol.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.d = {}

    def tamam_mi(self, p: Path, ozet: str) -> bool:
        k = self.d.get(str(p))
        if not k or not p.exists():
            return False
        st = p.stat()
        return k == [st.st_size, st.st_mtime_ns, ozet]

    def isle(self, p: Path, ozet: str) -> None:
        st = p.stat()
        with self.kilit:
            self.d[str(p)] = [st.st_size, st.st_mtime_ns, ozet]
            self.yol.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.yol.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.d, indent=0), encoding="utf-8")
            os.replace(tmp, self.yol)


def dogru_mu(p: Path, beklenen: dict) -> tuple[bool, str]:
    """beklenen: {'boyut', and one of 'sha256' | 'md5' | 'sha1_git'} -> (ok, digest string used as cache key)."""
    if not p.exists() or p.stat().st_size != beklenen["boyut"]:
        return False, ""
    if "sha256" in beklenen:
        o = _ozet(p, "sha256")
        return o == beklenen["sha256"], o
    if "md5" in beklenen:
        o = _ozet(p, "md5")
        return o == beklenen["md5"], o
    if "sha1_git" in beklenen:
        o = git_blob_sha1(p)
        return o == beklenen["sha1_git"], o
    return True, f"boyut:{beklenen['boyut']}"


def _beklenen_ozet(b: dict) -> str:
    return b.get("sha256") or b.get("md5") or b.get("sha1_git") or f"boyut:{b['boyut']}"


BAGLANTI = 4                 # parallel connections for big files (the CDN throttles each connection)
PARCALI_ESIK = 256 * 2**20   # files at least this big are fetched in segments


def _istek(url: str, bas: int, son: int | None = None):
    rng = f"bytes={bas}-{'' if son is None else son}"
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Range": rng}), timeout=60)


def _tek_akis(url: str, part: Path, toplam: int, ad: str, deneme: int) -> None:
    """Single stream into part, resuming from its current size."""
    bekle = 5
    for n in range(1, deneme + 1):
        basla = part.stat().st_size if part.exists() else 0
        if basla > toplam:
            part.unlink()
            basla = 0
        if basla == toplam:
            return
        try:
            with _istek(url, basla) as r:
                if basla and r.status != 206:  # server ignored the range: start over
                    basla = 0
                kayit(f"indiriliyor {ad} ({toplam / 1e9:.2f} GB) {'devam ' + f'{basla / 1e9:.2f} GB' if basla else ''}")
                with open(part, "ab" if basla else "wb") as f:
                    t0, son, alinan = time.time(), time.time(), 0
                    while b := r.read(1 << 20):
                        f.write(b)
                        alinan += len(b)
                        if time.time() - son > 30:
                            son = time.time()
                            hiz = alinan / max(son - t0, 1e-3)
                            kayit(f"  {ad}: {(basla + alinan) / 1e9:.2f}/{toplam / 1e9:.2f} GB, {hiz / 1e6:.1f} MB/s, "
                                  f"~{(toplam - basla - alinan) / max(hiz, 1) / 60:.0f} dk kaldı")
            if part.stat().st_size >= toplam:
                return
        except urllib.error.HTTPError as e:
            if e.code == 416 and part.exists() and part.stat().st_size == toplam:
                return
            kayit(f"  HTTP {e.code} {ad} (deneme {n}/{deneme})")
            if e.code in (401, 403, 404):
                raise KurulumHatasi(f"{url}: HTTP {e.code}") from e
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            kayit(f"  bağlantı koptu {ad}: {e} (deneme {n}/{deneme}, {bekle} sn sonra devam)")
        time.sleep(bekle)
        bekle = min(bekle * 2, 120)
    raise KurulumHatasi(f"{ad}: {deneme} denemede inmedi")


def _parcali(url: str, part: Path, toplam: int, ad: str, baglanti: int, deneme: int) -> None:
    """Several ranged connections writing into one pre-sized part file; the cursor of every segment is kept in
    <part>.json, so an interrupted download resumes per segment. A part file left by the single-stream mode counts
    as a finished prefix."""
    meta = part.with_name(part.name + ".json")
    kilit = threading.Lock()
    if meta.exists():
        segs = json.loads(meta.read_text(encoding="utf-8"))["parcalar"]
    else:
        bas = part.stat().st_size if part.exists() else 0
        bas = bas if bas <= toplam else 0
        adim = max(1, -(-(toplam - bas) // baglanti))
        segs = [[s, min(s + adim, toplam), s] for s in range(bas, toplam, adim)]  # [start, end, cursor]
        with open(part, "ab" if bas else "wb") as f:
            f.truncate(toplam)
        meta.write_text(json.dumps({"toplam": toplam, "parcalar": segs}), encoding="utf-8")

    def kaydet():
        tmp = meta.with_suffix(".tmp")
        tmp.write_text(json.dumps({"toplam": toplam, "parcalar": segs}), encoding="utf-8")
        os.replace(tmp, meta)

    hatalar: list[Exception] = []

    def isci(seg):
        bekle = 5
        for n in range(1, deneme + 1):
            if seg[2] >= seg[1]:
                return
            try:
                with _istek(url, seg[2], seg[1] - 1) as r, open(part, "r+b") as f:
                    if r.status != 206:
                        raise KurulumHatasi(f"{ad}: sunucu aralıklı indirmeyi desteklemiyor")
                    f.seek(seg[2])
                    yazilan = 0
                    while seg[2] < seg[1] and (b := r.read(min(1 << 20, seg[1] - seg[2]))):
                        f.write(b)
                        seg[2] += len(b)
                        yazilan += len(b)
                        if yazilan >= 16 << 20:
                            f.flush()
                            yazilan = 0
                            with kilit:
                                kaydet()
                    f.flush()
                with kilit:
                    kaydet()
                if seg[2] >= seg[1]:
                    return
            except KurulumHatasi as e:
                hatalar.append(e)
                return
            except urllib.error.HTTPError as e:
                if e.code in (401, 403, 404):
                    hatalar.append(KurulumHatasi(f"{url}: HTTP {e.code}"))
                    return
                kayit(f"  HTTP {e.code} {ad} (parça, deneme {n}/{deneme})")
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                kayit(f"  bağlantı koptu {ad}: {e} (parça, deneme {n}/{deneme}, {bekle} sn sonra devam)")
            time.sleep(bekle)
            bekle = min(bekle * 2, 120)
        hatalar.append(KurulumHatasi(f"{ad}: {deneme} denemede inmedi"))

    kalan0 = sum(s[1] - s[2] for s in segs)
    kayit(f"indiriliyor {ad} ({toplam / 1e9:.2f} GB, {len(segs)} bağlantı)"
          + (f" devam: {(toplam - kalan0) / 1e9:.2f} GB hazır" if kalan0 < toplam else ""))
    ts = [threading.Thread(target=isci, args=(s,), daemon=True, name=threading.current_thread().name) for s in segs]
    for t in ts:
        t.start()
    t0 = son = time.time()
    while any(t.is_alive() for t in ts):
        time.sleep(0.5)
        kalan = sum(s[1] - s[2] for s in segs)
        if kalan and time.time() - son >= 30:
            son = time.time()
            hiz = (kalan0 - kalan) / max(time.time() - t0, 1e-3)
            kayit(f"  {ad}: {(toplam - kalan) / 1e9:.2f}/{toplam / 1e9:.2f} GB, {hiz / 1e6:.1f} MB/s, "
                  f"~{kalan / max(hiz, 1) / 60:.0f} dk kaldı")
    if hatalar:
        raise hatalar[0]
    if any(s[2] < s[1] for s in segs):
        raise KurulumHatasi(f"{ad}: eksik kaldı (tekrar çalıştırınca sürer)")
    meta.unlink(missing_ok=True)


def indir_dosya(url: str, hedef: Path, beklenen: dict, dog: Dogrulanan, deneme: int = 60,
                baglanti: int | None = None) -> None:
    """Resumable download to hedef (via hedef.part), verified before it gets its final name. Big files use
    several connections."""
    if dog.tamam_mi(hedef, _beklenen_ozet(beklenen)):
        return
    if hedef.exists():
        ok, o = dogru_mu(hedef, beklenen)
        if ok:
            dog.isle(hedef, o)
            return
        kayit(f"bozuk ya da eksik, yeniden indiriliyor: {hedef.name}")
        hedef.unlink()
    hedef.parent.mkdir(parents=True, exist_ok=True)
    part = hedef.with_name(hedef.name + ".part")
    toplam = beklenen["boyut"]
    baglanti = BAGLANTI if baglanti is None else baglanti
    if part.with_name(part.name + ".json").exists() or (baglanti > 1 and toplam >= PARCALI_ESIK):
        _parcali(url, part, toplam, hedef.name, baglanti, deneme)
    else:
        _tek_akis(url, part, toplam, hedef.name, deneme)
    os.replace(part, hedef)
    ok, o = dogru_mu(hedef, beklenen)
    if not ok:
        bad = hedef.with_name(hedef.name + ".bozuk")
        os.replace(hedef, bad)
        raise KurulumHatasi(f"{hedef.name}: özet tutmadı (dosya {bad.name} olarak bırakıldı, silip tekrar çalıştırın)")
    dog.isle(hedef, o)
    kayit(f"tamam {hedef.name}")


def _json_al(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for n in range(8):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            kayit(f"  liste alınamadı ({e}), tekrar denenecek")
            time.sleep(5 * (n + 1))
    raise KurulumHatasi(f"liste alınamadı: {url}")


def hf_liste(modeller: Path, repo: str, rev: str) -> list[dict]:
    """The Hub file listing of repo@rev (cached under <modeller>/.liste/)."""
    lp = liste_yolu(modeller, repo, rev)
    if lp.exists():
        return json.loads(lp.read_text(encoding="utf-8"))
    liste = _json_al(f"https://huggingface.co/api/models/{repo}/tree/{rev}?recursive=true")
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(json.dumps(liste, indent=1), encoding="utf-8")
    return liste


def _hf_beklenen(f: dict) -> dict:
    if f.get("lfs"):
        return {"boyut": int(f["size"]), "sha256": f["lfs"]["oid"]}
    return {"boyut": int(f["size"]), "sha1_git": f["oid"]}


def grup_indir(a: ayar_mod.Ayar, grup: dict, dog: Dogrulanan) -> None:
    t0 = time.time()
    kayit(f"== grup {grup['ad']}")
    for repo, rev, desenler in grup["hf"]:
        dosyalar = secilen(hf_liste(a.modeller, repo, rev), desenler)
        if not dosyalar:
            raise KurulumHatasi(f"{repo}: {desenler} listede yok")
        # Small files first, so configs exist early and failures show fast.
        for f in sorted(dosyalar, key=lambda f: f["size"]):
            url = f"https://huggingface.co/{repo}/resolve/{rev}/{f['path']}"
            indir_dosya(url, a.modeller / klasor(repo) / f["path"], _hf_beklenen(f), dog)
    for d in grup["dosya"]:
        b = {k: d[k] for k in ("boyut", "sha256", "md5") if k in d}
        indir_dosya(d["url"], a.modeller / d["yol"], b, dog)
    kayit(f"== grup {grup['ad']} hazır ({time.time() - t0:.0f} sn)")


def cmd_indir(a, gruplar: list[str] | None, xpart: bool = True) -> None:
    dog = Dogrulanan(a.modeller / ".liste" / "dogrulanan.json")
    secim = [g for g in GRUPLAR if (not gruplar or g["ad"] in gruplar) and (xpart or g["ad"] != "xpart")]
    hatalar = []
    for g in secim:
        try:
            grup_indir(a, g, dog)
        except KurulumHatasi as e:
            kayit(f"HATA {g['ad']}: {e}")
            hatalar.append(g["ad"])
    if hatalar:
        raise KurulumHatasi(f"inmeyen gruplar: {', '.join(hatalar)} (tekrar çalıştırınca kaldığı yerden sürer)")
    kayit("İNDİRME BİTTİ")


def cmd_dogrula(a, tam: bool) -> bool:
    dog = Dogrulanan(a.modeller / ".liste" / "dogrulanan.json")
    hepsi_tamam = True
    for g in GRUPLAR:
        eksik, toplam = 0, 0
        beklenenler: list[tuple[Path, dict]] = []
        for repo, rev, desenler in g["hf"]:
            lp = liste_yolu(a.modeller, repo, rev)
            if not lp.exists():
                eksik += 1
                continue
            for f in secilen(json.loads(lp.read_text(encoding="utf-8")), desenler):
                beklenenler.append((a.modeller / klasor(repo) / f["path"], _hf_beklenen(f)))
        for d in g["dosya"]:
            beklenenler.append((a.modeller / d["yol"], {k: d[k] for k in ("boyut", "sha256", "md5") if k in d}))
        for p, b in beklenenler:
            toplam += b["boyut"]
            if tam:
                ok, o = dogru_mu(p, b)
                if ok:
                    dog.isle(p, o)
            else:
                ok = p.exists() and p.stat().st_size == b["boyut"]
            if not ok:
                eksik += 1
                kayit(f"  eksik/bozuk: {p}")
        durum = "tamam" if eksik == 0 else f"{eksik} eksik"
        if eksik and g["zorunlu"]:
            hepsi_tamam = False
        kayit(f"{g['ad']:9s} {toplam / 1e9:6.2f} GB  {durum}{'' if g['zorunlu'] else '  (isteğe bağlı)'}")
    kayit("DOĞRULAMA: " + ("TAMAM" if hepsi_tamam else "EKSİK VAR"))
    return hepsi_tamam


# ---------------------------------------------------------------- environment
def uv_bul() -> str:
    for c in (shutil.which("uv"), Path.home() / ".local" / "bin" / ("uv.exe" if os.name == "nt" else "uv")):
        if c and Path(c).exists():
            return str(c)
    raise KurulumHatasi("uv bulunamadı. Kurun: https://docs.astral.sh/uv/ (kur.ps1 bunu kendisi yapar)")


def calistir(komut: list[str], **kw) -> None:
    kayit("$ " + " ".join(f'"{c}"' if " " in str(c) else str(c) for c in komut))
    p = subprocess.Popen([str(c) for c in komut], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", **kw)
    for satir in p.stdout:
        kayit("  " + satir.rstrip())
    if p.wait() != 0:
        raise KurulumHatasi(f"komut başarısız ({p.returncode}): {komut[0]}")


def kod_klonla(a) -> None:
    git = shutil.which("git") or "git"
    for ad, (url, sha) in KODLAR.items():
        d = a.kod / ad
        if (d / ".git").exists():
            r = subprocess.run([git, "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True)
            if r.stdout.strip() == sha:
                kayit(f"kod hazır: {ad} @ {sha[:7]}")
                continue
        d.mkdir(parents=True, exist_ok=True)
        if not (d / ".git").exists():
            calistir([git, "init", "-q", str(d)])
            calistir([git, "-C", str(d), "remote", "add", "origin", url])
        calistir([git, "-C", str(d), "fetch", "-q", "--depth", "1", "origin", sha])
        calistir([git, "-C", str(d), "-c", "advice.detachedHead=false", "checkout", "-q", "--force", "FETCH_HEAD"])
        kayit(f"kod hazır: {ad} @ {sha[:7]}")


def cuda_arch_sec(a) -> str:
    """TORCH_CUDA_ARCH_LIST for the native build: the GPU's own arch if the toolkit knows it, else PTX JIT."""
    if a.cuda_arch:
        return a.cuda_arch
    try:
        cc = subprocess.run(["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
                            capture_output=True, text=True, timeout=20).stdout.split()[0].strip()
    except (OSError, IndexError, subprocess.TimeoutExpired):
        cc = "8.6"
    nvcc = (a.cuda / "bin" / "nvcc.exe") if a.cuda else None
    surum = (0, 0)
    if nvcc and nvcc.exists():
        m = re.search(r"release (\d+)\.(\d+)", subprocess.run([str(nvcc), "--version"], capture_output=True, text=True).stdout)
        if m:
            surum = (int(m[1]), int(m[2]))
    if float(cc) >= 12.0 and surum < (12, 8):
        return "9.0+PTX"  # the driver JIT-compiles compute_90 PTX for Blackwell
    return cc


def cmd_ortam(a) -> None:
    uv = uv_bul()
    if not a.venv_python.exists():
        calistir([uv, "venv", str(a.venv), "--python", a.python, "--seed"])
    teker = tekerlekler(sys.platform)
    if not teker:
        raise KurulumHatasi(f"bu platform için torch tekerleği tanımlı değil: {sys.platform}")
    dog = Dogrulanan(a.tekerlek / "dogrulanan.json")
    for t in teker:
        indir_dosya(t["url"], a.tekerlek / t["ad"], {"boyut": t["boyut"], "sha256": t["sha256"]}, dog)
    py = str(a.venv_python)
    gerek, kisit = KOK / "kurulum" / "gereksinimler.txt", KOK / "kurulum" / "kisitlar.txt"
    calistir([uv, "pip", "install", "--python", py, *[str(a.tekerlek / t["ad"]) for t in teker]])
    calistir([uv, "pip", "install", "--python", py, "-r", str(gerek), "-c", str(kisit),
              "--no-build-isolation-package", "basicsr"])
    calistir([uv, "pip", "install", "--python", py, "torch_scatter", "torch_cluster", "-c", str(kisit),
              "-f", "https://data.pyg.org/whl/torch-2.11.0+cu128.html"])
    kod_klonla(a)
    eklenti_derle(a)
    kayit("ORTAM HAZIR")


def eklenti_derle(a) -> None:
    if all(any(a.derleme.glob(f"{ad}*.{'pyd' if os.name == 'nt' else 'so'}"))
           for ad in ("custom_rasterizer_kernel", "mesh_inpaint_processor")):
        kayit("eklentiler hazır")
        return
    a.derleme.mkdir(parents=True, exist_ok=True)
    betik = KOK / "kurulum" / "eklenti_derle.py"
    arch = cuda_arch_sec(a)
    kayit(f"eklentiler derleniyor (TORCH_CUDA_ARCH_LIST={arch})")
    env = dict(os.environ, TORCH_CUDA_ARCH_LIST=arch, DISTUTILS_USE_SDK="1")
    if a.cuda:
        env.update(CUDA_HOME=str(a.cuda), CUDA_PATH=str(a.cuda), PATH=str(a.cuda / "bin") + os.pathsep + env["PATH"])
    argv = [str(a.venv_python), "-I", str(betik), "build_ext", "--build-lib", str(a.derleme),
            "--build-temp", str(a.derleme / "tmp")]
    if os.name == "nt":
        if not a.vsvars or not a.vsvars.exists():
            raise KurulumHatasi(f"Visual Studio C++ ortamı bulunamadı: {a.vsvars} (atolye.toml [kurulum] vsvars)")
        cmd = a.kayit / "derle.cmd"
        cmd.write_text("@echo off\r\n"
                       f'call "{a.vsvars}" >nul || exit /b 1\r\n'
                       + " ".join(f'"{x}"' for x in argv) + "\r\n", encoding="utf-8")
        calistir(["cmd", "/d", "/c", str(cmd)], env=env, cwd=str(a.derleme))
    else:
        calistir(argv, env=env, cwd=str(a.derleme))


# ---------------------------------------------------------------- main
def cmd_ayar() -> Path:
    hedef = ayar_mod.ayar_dosyasi()
    if not hedef.exists():
        shutil.copyfile(ayar_mod.ORNEK, hedef)
        print(f"{hedef} oluşturuldu; yolları gerekirse düzenleyin.")
    return hedef


def main() -> int:
    global _kayit_dosyasi
    ap = argparse.ArgumentParser(description="Parça Atölyesi kurulumu")
    sp = ap.add_subparsers(dest="komut", required=True)
    sp.add_parser("ayar")
    pi = sp.add_parser("indir")
    pi.add_argument("gruplar", nargs="*", help=" ".join(g["ad"] for g in GRUPLAR))
    pi.add_argument("--xpart-yok", action="store_true")
    sp.add_parser("ortam")
    sp.add_parser("kod", help="only the pinned upstream code clones")
    pd = sp.add_parser("dogrula")
    pd.add_argument("--tam", action="store_true", help="hash every file (slow: tens of GB)")
    sp.add_parser("baslat")
    ph = sp.add_parser("hepsi")
    ph.add_argument("--xpart-yok", action="store_true")
    ns = ap.parse_args()

    cmd_ayar()
    a = ayar_mod.yukle()
    if ns.komut == "baslat":
        if not a.venv_python.exists():
            print("Önce kurulum: kurulum/kur.ps1")
            return 1
        return subprocess.call([str(a.venv_python), "-I", str(KOK / "atolye" / "calis.py"), "sunucu"])
    a.kayit.mkdir(parents=True, exist_ok=True)
    _kayit_dosyasi = a.kayit / "kurulum.log"
    threading.current_thread().name = ns.komut
    kayit(f"başladı: {' '.join(sys.argv[1:])} | modeller={a.modeller} veri={a.veri}")
    try:
        if ns.komut == "indir":
            cmd_indir(a, ns.gruplar, xpart=not ns.xpart_yok)
        elif ns.komut == "ortam":
            cmd_ortam(a)
        elif ns.komut == "kod":
            kod_klonla(a)
        elif ns.komut == "dogrula":
            return 0 if cmd_dogrula(a, ns.tam) else 1
        elif ns.komut == "hepsi":
            hata: list[Exception] = []

            def _arka():
                try:
                    cmd_indir(a, None, xpart=not ns.xpart_yok)
                except Exception as e:  # reported after the environment step
                    hata.append(e)

            t = threading.Thread(target=_arka, name="indir", daemon=True)
            t.start()
            cmd_ortam(a)
            t.join()
            if hata:
                raise hata[0]
            return 0 if cmd_dogrula(a, False) else 1
    except KurulumHatasi as e:
        kayit(f"HATA: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
