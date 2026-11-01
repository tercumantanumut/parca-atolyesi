import os
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))


@pytest.fixture
def ayar_dosyasi(tmp_path, monkeypatch):
    """A config pointing every folder into tmp_path (Blender from the real config, if any)."""
    from atolye import ayar

    gercek = ayar.yukle()
    blender = str(gercek.blender).replace("\\", "/") if gercek.blender else ""
    f = tmp_path / "atolye.toml"
    f.write_text(f'''[yollar]
modeller = "{(tmp_path / 'modeller').as_posix()}"
veri = "{(tmp_path / 'veri').as_posix()}"
cikti = "{(tmp_path / 'cikti').as_posix()}"
blender = "{blender}"
''', encoding="utf-8")
    monkeypatch.setenv("ATOLYE_AYAR", str(f))
    return f


def blender_var():
    from atolye import ayar

    b = ayar.yukle().blender
    return bool(b and Path(b).exists())


gerek_blender = pytest.mark.skipif(not blender_var(), reason="Blender yok (atolye.toml [yollar] blender)")
