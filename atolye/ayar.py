"""Configuration: one `atolye.toml` at the repo root (gitignored), `atolye.ornek.toml` is the committed template.

Every machine-specific path lives here. Relative paths are resolved against the repo root. Nothing is read from
environment variables (the only exception is ATOLYE_AYAR, which picks a different config file, for tests).
"""
from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
ORNEK = KOK / "atolye.ornek.toml"


@dataclass
class Ayar:
    kok: Path
    modeller: Path
    veri: Path
    cikti: Path
    blender: Path | None
    adres: str = "127.0.0.1"
    port: int = 8731
    python: str = "3.12"
    cuda: Path | None = None
    vsvars: Path | None = None
    cuda_arch: str = ""
    ham: dict = field(default_factory=dict)

    # Derived locations inside `veri`.
    @property
    def venv(self) -> Path:
        return self.veri / "venv"

    @property
    def venv_python(self) -> Path:
        return self.venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    @property
    def kod(self) -> Path:
        """Pinned upstream code clones (treated as read-only data)."""
        return self.veri / "kod"

    @property
    def derleme(self) -> Path:
        """Compiled native extensions (custom_rasterizer_kernel, mesh_inpaint_processor)."""
        return self.veri / "derleme"

    @property
    def tekerlek(self) -> Path:
        """Downloaded torch / torchvision wheels."""
        return self.veri / "tekerlek"

    @property
    def kayit(self) -> Path:
        return self.veri / "kayit"


def _yol(kok: Path, v: str | None) -> Path | None:
    if not v:
        return None
    p = Path(os.path.expandvars(os.path.expanduser(v)))
    return (p if p.is_absolute() else kok / p).resolve()


def ayar_dosyasi() -> Path:
    return Path(os.environ["ATOLYE_AYAR"]) if os.environ.get("ATOLYE_AYAR") else KOK / "atolye.toml"


def yukle(dosya: Path | None = None) -> Ayar:
    dosya = dosya or ayar_dosyasi()
    kaynak = dosya if dosya.exists() else ORNEK
    d = tomllib.loads(kaynak.read_text(encoding="utf-8"))
    y, s, k = d.get("yollar", {}), d.get("sunucu", {}), d.get("kurulum", {})
    kok = KOK
    blender = _yol(kok, y.get("blender"))
    if blender is None:
        w = shutil.which("blender")
        blender = Path(w) if w else None
    return Ayar(
        kok=kok,
        modeller=_yol(kok, y.get("modeller", "modeller")),
        veri=_yol(kok, y.get("veri", ".atolye")),
        cikti=_yol(kok, y.get("cikti", "cikti")),
        blender=blender,
        adres=s.get("adres", "127.0.0.1"),
        port=int(s.get("port", 8731)),
        python=str(k.get("python", "3.12")),
        cuda=_yol(kok, k.get("cuda")),
        vsvars=_yol(kok, k.get("vsvars")),
        cuda_arch=str(k.get("cuda_arch", "")),
        ham=d,
    )
