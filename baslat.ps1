# Parça Atölyesi'ni başlatır: http://127.0.0.1:8731 (kurulumdan sonra). Durdurmak için Ctrl+C.
$ErrorActionPreference = "Stop"
$kok = $PSScriptRoot
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) { $uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe" }
& $uv run --no-project --python 3.12 python -I (Join-Path $kok "kurulum\kur.py") baslat
exit $LASTEXITCODE
