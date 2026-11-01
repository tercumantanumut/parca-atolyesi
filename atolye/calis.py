"""Entry point for one pipeline step in its own process:  python -I atolye/calis.py <adim> [args...]
(`python -I atolye/calis.py sunucu` starts the server.)

-I keeps the interpreter from importing anything from the current or script folder; the repo root is added here
explicitly, so only our own package and the installed packages are importable.
"""
import importlib
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True  # no __pycache__ inside the upstream clones (they are kept as downloaded)
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

for _s in (sys.stdout, sys.stderr):  # upstream code prints non-ASCII log lines
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: calis.py <adim> [args...]")
    ad = sys.argv[1]
    mod = importlib.import_module(f"atolye.{ad}" if ad in ("sunucu", "isci") else f"atolye.stages.{ad}")
    mod.main(sys.argv[2:])
