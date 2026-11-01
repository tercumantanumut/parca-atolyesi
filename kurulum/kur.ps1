# Parça Atölyesi kurulumu (Windows). Depo kökünden:
#   powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1            # hepsi: ortam + modeller + doğrulama
#   powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1 indir      # yalnız model ağırlıkları
#   powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1 ortam      # yalnız Python ortamı ve eklentiler
#   powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1 dogrula --tam
# Yarıda kalırsa aynı komutu yeniden çalıştırın: inenler atlanır, yarım dosyalar kaldığı yerden sürer.
$ErrorActionPreference = "Stop"
$kok = Split-Path -Parent $PSScriptRoot
Set-Location $kok

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) { $uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe" }
if (-not (Test-Path $uv)) {
    Write-Host "uv kuruluyor (https://astral.sh/uv)..."
    powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "git bulunamadı: https://git-scm.com/download/win adresinden kurun."
}
if ($args.Count -eq 0) { $args = @("hepsi") }
# The installer itself only needs the standard library; uv provides a Python 3.12 for it if none is installed.
& $uv run --no-project --python 3.12 python -I (Join-Path $kok "kurulum\kur.py") @args
exit $LASTEXITCODE
