"""HTTP server (stdlib only): the JSON API, the SSE event stream, job outputs and the web app.

  python -I atolye/calis.py sunucu [--adres 127.0.0.1] [--port 8731]

The API contract is in design/PLAN.md ("API contract" + "API additions"). Error responses are JSON
{"hata": <stable id>, "ayrinti": ...}; the web side turns ids into Turkish text.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
import time
import traceback
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .ayar import KOK, yukle
from .isler import Atolye, GirdiHatasi, gecerli_id

EN_BUYUK_YUKLEME = 300 * 2**20
SSE_CANLI_TUT = 15.0
mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("image/webp", ".webp")


def multipart_coz(govde: bytes, icerik_turu: str) -> tuple[dict, dict]:
    """multipart/form-data -> ({field: str}, {field: (filename, bytes)})."""
    msg = BytesParser(policy=HTTP).parsebytes(b"Content-Type: " + icerik_turu.encode("latin-1") + b"\r\n\r\n" + govde)
    if not msg.is_multipart():
        raise GirdiHatasi("gecersiz_form")
    alanlar, dosyalar = {}, {}
    for parca in msg.iter_parts():
        ad = parca.get_param("name", header="content-disposition")
        if not ad:
            continue
        dosya_adi = parca.get_filename()
        veri = parca.get_payload(decode=True) or b""
        if dosya_adi is not None:
            if veri:
                dosyalar[ad] = (dosya_adi, veri)
        else:
            alanlar[ad] = veri.decode(parca.get_content_charset() or "utf-8", errors="replace")
    return alanlar, dosyalar


class Isleyici(BaseHTTPRequestHandler):
    server_version = "ParcaAtolyesi"
    protocol_version = "HTTP/1.1"
    atolye: Atolye = None  # set by sun()
    web: Path = KOK / "web"

    def log_message(self, fmt, *args):  # quiet: the VRAM poll would flood the console
        if "/api/vram" in self.path or "/olaylar" in self.path:
            return
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # ------------------------------------------------------------ helpers
    def end_headers(self):
        # A web page served from another local port (e.g. a dev server) may call the API; nothing beyond loopback.
        o = self.headers.get("Origin") if self.headers else None
        if o and re.fullmatch(r"https?://(127\.0\.0\.1|localhost)(:\d+)?", o):
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Vary", "Origin")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Last-Event-ID")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, veri, durum: int = 200) -> None:
        b = json.dumps(veri, ensure_ascii=False).encode("utf-8")
        self.send_response(durum)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)

    def _hata(self, kod: str, durum: int = 400, ayrinti=None) -> None:
        self._json({"hata": kod, "ayrinti": ayrinti}, durum)

    def _govde(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > EN_BUYUK_YUKLEME:
            raise GirdiHatasi("dosya_cok_buyuk", {"en_cok_mb": EN_BUYUK_YUKLEME // 2**20}, 413)
        return self.rfile.read(n) if n else b""

    def _form_ya_da_json(self) -> dict:
        tur = self.headers.get("Content-Type", "")
        govde = self._govde()
        if tur.startswith("multipart/form-data"):
            return multipart_coz(govde, tur)[0]
        if tur.startswith("application/x-www-form-urlencoded"):
            from urllib.parse import parse_qsl

            return dict(parse_qsl(govde.decode("utf-8")))
        if not govde.strip():
            return {}
        try:
            d = json.loads(govde)
        except ValueError:
            raise GirdiHatasi("gecersiz_json")
        if not isinstance(d, dict):
            raise GirdiHatasi("gecersiz_json")
        return d

    def _dosya(self, kok: Path, rel: str, onbellek: str) -> None:
        try:
            yol = (kok / rel).resolve()
            yol.relative_to(kok.resolve())
        except (ValueError, OSError):
            return self._hata("bulunamadi", 404)
        if yol.is_dir():
            yol = yol / "index.html"
        if not yol.is_file():
            return self._hata("bulunamadi", 404)
        st = yol.stat()
        etag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        tur = mimetypes.guess_type(yol.name)[0] or "application/octet-stream"
        if tur.startswith("text/") or tur.endswith("json") or tur.endswith("javascript"):
            tur += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(st.st_size))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", onbellek)
        if yol.suffix == ".zip":
            self.send_header("Content-Disposition", f'attachment; filename="parca-atolyesi-{yol.parent.name}.zip"')
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(yol, "rb") as f:
            while b := f.read(1 << 20):
                self.wfile.write(b)

    # ------------------------------------------------------------ routing
    def _yonlendir(self, yontem: str) -> None:
        yol = unquote(urlsplit(self.path).path)
        A = self.atolye
        try:
            if yol.startswith("/api/"):
                if yontem == "GET" and yol == "/api/sistem":
                    return self._json(A.sistem())
                if yontem == "GET" and yol == "/api/vram":
                    return self._json(A.vram())
                if yol == "/api/ayar" and yontem == "GET":
                    return self._json(A.ayar())
                if yol == "/api/ayar" and yontem == "POST":
                    return self._json(A.ayar_degistir(self._form_ya_da_json()))
                if yontem == "GET" and yol == "/api/paletler":
                    return self._json(A.sistem()["paletler"])
                if yontem == "GET" and yol == "/api/isler":
                    return self._json(A.liste())
                if yontem == "POST" and yol == "/api/is":
                    return self._is_olustur()
                m = re.fullmatch(r"/api/is/([^/]+)(?:/(olaylar|toon|piksel))?", yol)
                if m:
                    j = A.al(m.group(1))
                    if j is None:
                        return self._hata("is_yok", 404)
                    alt = m.group(2)
                    if yontem == "GET" and alt is None:
                        d = j.sozluk()
                        d["sira"] = A.sira(j)
                        return self._json(d)
                    if yontem == "DELETE" and alt is None:
                        A.sil(j.id)
                        return self._json({"silindi": j.id})
                    if yontem == "GET" and alt == "olaylar":
                        return self._sse(j)
                    if yontem == "POST" and alt == "toon":
                        f = self._form_ya_da_json()
                        aci = f.get("aci") or f.get("toon_aci")
                        if not aci:
                            raise GirdiHatasi("gecersiz_toon_aci")
                        return self._json(A.yeniden(j, toon_aci=aci))
                    if yontem == "POST" and alt == "piksel":
                        f = self._form_ya_da_json()
                        boy = f.get("boy", f.get("piksel_boy"))
                        return self._json(A.yeniden(j, boy=boy, palet=f.get("palet")))
                return self._hata("yol_yok", 404)
            if yontem in ("GET", "HEAD"):
                m = re.fullmatch(r"/cikti/([^/]+)/(.+)", yol)
                if m:
                    if not gecerli_id(m.group(1)) or A.al(m.group(1)) is None:
                        return self._hata("bulunamadi", 404)
                    return self._dosya(A.a.cikti / m.group(1), m.group(2), "no-cache")
                return self._dosya(self.web, yol.lstrip("/") or "index.html", "no-cache")
            return self._hata("yontem_yok", 405)
        except GirdiHatasi as e:
            return self._hata(e.kod, e.durum, e.ayrinti)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as e:  # pragma: no cover
            traceback.print_exc()
            try:
                return self._hata("sunucu_hatasi", 500, str(e))
            except Exception:
                return

    def do_GET(self):
        self._yonlendir("GET")

    def do_HEAD(self):
        self._yonlendir("HEAD")

    def do_POST(self):
        self._yonlendir("POST")

    def do_DELETE(self):
        self._yonlendir("DELETE")

    # ------------------------------------------------------------ endpoints
    def _is_olustur(self) -> None:
        tur = self.headers.get("Content-Type", "")
        if not tur.startswith("multipart/form-data"):
            raise GirdiHatasi("multipart_gerekli", None, 415)
        alanlar, dosyalar = multipart_coz(self._govde(), tur)
        j = self.atolye.olustur(alanlar, dosyalar.get("on"), dosyalar.get("arka"), dosyalar.get("mesh"))
        self._json({"id": j.id}, 201)

    def _sse(self, j) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True

        def gonder(n, olay):
            self.wfile.write(f"id: {n}\ndata: {json.dumps(olay, ensure_ascii=False)}\n\n".encode("utf-8"))

        son = self.headers.get("Last-Event-ID")
        with j.kosul:
            sayac = j.sayac
            eski = [(n, o) for n, o in j.olaylar if son and son.isdigit() and n > int(son)]
            ilk_n = j.olaylar[0][0] if j.olaylar else sayac + 1
        try:
            self.wfile.write(b"retry: 2000\n\n")
            if son and son.isdigit() and int(son) + 1 >= ilk_n:
                for n, o in eski:  # resume exactly where the browser stopped
                    gonder(n, o)
            else:  # fresh connection: a snapshot of the current state
                for o in j.anlik():
                    gonder(sayac, o)
            self.wfile.flush()
            while True:
                with j.kosul:
                    if j.sayac == sayac:
                        j.kosul.wait(SSE_CANLI_TUT)
                    yeni = [(n, o) for n, o in j.olaylar if n > sayac]
                    sayac = j.sayac
                if yeni:
                    for n, o in yeni:
                        gonder(n, o)
                else:
                    self.wfile.write(b": canli\n\n")
                self.wfile.flush()
                if self.atolye.al(j.id) is None:  # deleted
                    return
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return


class Sunucu(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False  # Windows: True would let a second server steal the port


def sun(adres: str | None = None, port: int | None = None, web: Path | None = None, atolye: Atolye | None = None):
    a = yukle()
    Isleyici.atolye = atolye or Atolye(a)
    Isleyici.web = Path(web) if web else Path(a.ham.get("sunucu", {}).get("web") or (KOK / "web"))
    if not Isleyici.web.is_absolute():
        Isleyici.web = (KOK / Isleyici.web).resolve()
    srv = Sunucu((adres or a.adres, a.port if port is None else port), Isleyici)
    return srv


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sunucu")
    ap.add_argument("--adres")
    ap.add_argument("--port", type=int)
    ap.add_argument("--web", help="web app folder (default: <repo>/web)")
    a = ap.parse_args(argv)
    srv = sun(a.adres, a.port, a.web)
    h, p = srv.server_address[:2]
    print(f"Parça Atölyesi: http://{h}:{p}/  (durdurmak için Ctrl+C)", flush=True)
    try:
        srv.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
