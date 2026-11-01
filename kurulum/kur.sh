#!/usr/bin/env bash
# Parça Atölyesi kurulumu, Linux (DENENMEDİ). Depo kökünden: bash kurulum/kur.sh [hepsi|indir|ortam|kod|dogrula|baslat]
set -euo pipefail
kok="$(cd "$(dirname "$0")/.." && pwd)"
uv="$(command -v uv || echo "$HOME/.local/bin/uv")"
if [ ! -x "$uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  uv="$HOME/.local/bin/uv"
fi
[ $# -eq 0 ] && set -- hepsi
exec "$uv" run --no-project --python 3.12 python -I "$kok/kurulum/kur.py" "$@"
