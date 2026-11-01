# Kurulum

Parça Atölyesi kendi bilgisayarında, kendi NVIDIA ekran kartınla çalışır. Kurulum betiği Python ortamını
hazırlar, gereken iki küçük eklentiyi derler ve model ağırlıklarını doğrudan yayıncılarından (Hugging Face,
GitHub) indirir. Modeller bu depoda yok, olmayacak da.

> Kısaca: **Windows'ta tek komutla kurulur.** Önce birkaç araç lazım (aşağıda). İndirme ~21–35 GB ve internet
> hızına göre birkaç saat sürebilir. Yarıda kalırsa aynı komutu yeniden çalıştırman yeterli, kaldığı yerden devam
> eder.

## 1. Neler gerekiyor?

| Ne | Neden | Not |
|---|---|---|
| **NVIDIA ekran kartı**, en az 8 GB VRAM | Modeller GPU'da çalışır | Rotalar ve VRAM için [rotalar-ve-vram.md](rotalar-ve-vram.md) |
| **Güncel NVIDIA sürücüsü** (CUDA 12.8 destekli, R570 ve üstü) | PyTorch 2.11 + CUDA 12.8 kullanıyoruz | `nvidia-smi` sağ üstte "CUDA Version: 12.8" ya da üstünü göstermeli |
| **Windows 10/11, 64 bit** | Kurulum betiği şimdilik Windows için | Linux için [aşağıdaki notlar](#linux-notları) |
| **Git** | Hunyuan kodunu sabit bir sürümden çeker | <https://git-scm.com/download/win> |
| **CUDA Toolkit 12.x** (nvcc) | Doku adımının rasterleştirici eklentisini derlemek için | <https://developer.nvidia.com/cuda-downloads>. 12.6 ve 12.8 olur |
| **Visual Studio 2022** "C++ ile masaüstü geliştirme" | Aynı eklentiler için C++ derleyicisi | Community ya da yalnız "Build Tools" yeter |
| **Blender 4.2 veya üstü** | 07 Toon adımı (Blender'ı arka planda, pencere açmadan çağırırız) | <https://www.blender.org/download/>. Yoksa 07 ve 08 çalışmaz, gerisi çalışır |
| **Boş disk**, ~60 GB | Modeller ~21 GB (her şeyle ~35 GB), torch ~3 GB, Python ortamı ve çıktılar | SSD önerilir: modeller her adımda diskten yüklenir |

Python kurmana gerek yok. Betik, [uv](https://docs.astral.sh/uv/) ile kendi Python 3.12'sini getirir, uv yoksa
onu da kurar.

## 2. Depoyu indir

PowerShell aç (Başlat → "PowerShell") ve deponun duracağı klasöre geç:

```powershell
git clone https://github.com/tercumantanumut/parca-atolyesi.git parca-atolyesi
cd parca-atolyesi
```


Bundan sonraki bütün komutlar **depo kökünden** (`parca-atolyesi` klasörü) çalışır.

## 3. Ayar dosyasını oluştur ve kontrol et

```powershell
powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1 ayar
notepad atolye.toml
```

İlk komut `atolye.ornek.toml` dosyasını `atolye.toml` adıyla kopyalar. Bilgisayarına özel bütün yollar bu tek
dosyada durur. Çoğu zaman yalnız üç satıra bakman yeter:

```toml
[yollar]
blender = "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"

[kurulum]
cuda = "C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.6"
vsvars = "C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Auxiliary/Build/vcvars64.bat"
```

- **blender:** kendi `blender.exe` yolun. Boş bırakırsan PATH'te `blender` aranır.
- **cuda:** kurduğun CUDA Toolkit klasörü (`v12.6`, `v12.8` …).
- **vsvars:** Visual Studio'nun `vcvars64.bat` dosyası. Yalnız Build Tools kurduysan yol genelde şudur:
  `C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Auxiliary/Build/vcvars64.bat`.
- Yollarda **düz eğik çizgi** (`/`) kullan. Ters eğik çizgi (`\`) TOML'da kaçış karakteridir ve hata verir.
- Modelleri başka bir diske koymak istersen: `modeller = "D:/atolye/modeller"`.

## 4. Kur

```powershell
powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1
```

Bu komut sırayla şunları yapar (`hepsi` komutu):

1. Model ağırlıklarını **arka planda** indirmeye başlar. Dosyalar sabit bir sürümden iner ve indikten sonra
   özetleri (hash) kontrol edilir.
2. Bu sırada Python ortamını kurar: `.atolye/venv` içine torch 2.11 + CUDA 12.8 ve gereken paketler.
3. Hunyuan3D kodunu sabit bir sürümden `.atolye/kod/` altına çeker. Bu klasöre dokunmayız, yalnız okuruz.
4. Doku adımının iki eklentisini derler (`custom_rasterizer_kernel`, `mesh_inpaint_processor`).
5. İndirme bitince her dosyayı kontrol eder ve tablo halinde yazar.

Sonunda doğrulama tablosu gelir. En alttaki satır `DOĞRULAMA: TAMAM` olmalı. Bir RTX 5090 makinesindeki gerçek
`kurulum.log`'un son satırları (yollar kısaltıldı):

```text
2026-11-01 23:30:20 [dogrula] başladı: dogrula | modeller=C:\...\parca-atolyesi\modeller veri=C:\...\parca-atolyesi\.atolye
2026-11-01 23:30:20 [dogrula] sekil       8.20 GB  tamam
2026-11-01 23:30:20 [dogrula] doku       11.50 GB  tamam
2026-11-01 23:30:20 [dogrula] parcalar    0.89 GB  tamam
2026-11-01 23:30:20 [dogrula] 2mv         4.93 GB  tamam  (isteğe bağlı)
2026-11-01 23:30:20 [dogrula] xpart       9.04 GB  tamam  (isteğe bağlı)
2026-11-01 23:30:20 [dogrula] DOĞRULAMA: TAMAM
```

**40 GB'tan az VRAM'in varsa** X-Part'ı hiç indirme, 9 GB kazanırsın:

```powershell
powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1 hepsi --xpart-yok
```

Kayıt (log) hem ekrana hem `.atolye\kayit\kurulum.log` dosyasına yazılır.

### Ne kadar iner, ne kadar sürer?

| Grup | Boyut | Ne için | Zorunlu mu |
|---|---|---|---|
| `sekil` | 8,2 GB | Hunyuan3D-2.1 şekil + arka plan temizleme (u2net) | Evet |
| `doku` | 11,5 GB | Hunyuan3D-2.1 PBR boyama + DINOv2 + Real-ESRGAN | Evet |
| `parcalar` | 0,9 GB | P3-SAM + Sonata (parçalara ayırma) | Evet |
| `2mv` | 4,9 GB | Ön + arka görselden şekil (Hunyuan3D-2mv) | Hayır |
| `xpart` | 9,0 GB | Kapalı parça meshleri (yalnız 40 GB+ kartlar) | Hayır |

Toplam: zorunlular ~21 GB, hepsi ~35 GB. Saniyede 5 MB ile ~35 GB yaklaşık 2 saat sürer. Ayrıca torch tekerleği
2,8 GB iner.

### Parça parça kurmak

Hepsini tek komutla kurmak zorunda değilsin. Her alt komut tek başına da çalışır ve tekrar çalıştırılabilir:

```powershell
powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1 indir                 # yalnız model ağırlıkları
powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1 indir sekil doku      # yalnız bu gruplar
powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1 indir --xpart-yok     # X-Part hariç hepsi
powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1 ortam                 # yalnız Python ortamı ve eklentiler
powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1 dogrula               # dosyalar yerinde mi (boyut)
powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1 dogrula --tam         # her dosyanın özetini de kontrol et (yavaş)
```

İnternet koparsa ya da bilgisayar kapanırsa **aynı komutu yeniden çalıştır.** İnmiş dosyalar atlanır, yarım
kalan dosya (`.part`) kaldığı yerden devam eder.

## 5. Başlat

```powershell
powershell -ExecutionPolicy Bypass -File baslat.ps1
```

Pencerede şu satır çıkınca tarayıcıda **<http://127.0.0.1:8731>** adresini aç:

```
Parça Atölyesi: http://127.0.0.1:8731/  (durdurmak için Ctrl+C)
```

Sunucu yalnız kendi bilgisayarından erişilebilir (`127.0.0.1`). Durdurmak için o pencerede **Ctrl+C**. Panelin
kullanımı: [panel.md](panel.md).

İlk deneme için `ornekler\maceraci.png` dosyasını panele sürükle, **Parçalı** rotayı seç ve **Başlat**'a bas.

## Klasörler

| Klasör | İçinde ne var | Git'te mi |
|---|---|---|
| `atolye/` | Sunucu, iş sırası, adımlar | Evet |
| `blender/` | Toon render betiği | Evet |
| `web/` | Panel (tarayıcı arayüzü) | Evet |
| `kurulum/` | Kurulum betikleri, paket listeleri | Evet |
| `paletler/` | Hazır piksel paletleri (`.hex`) | Evet |
| `ornekler/` | Denemek için üç örnek görsel | Evet |
| `modeller/` | İndirilen model ağırlıkları | Hayır |
| `.atolye/` | Python ortamı, kod kopyaları, derlenen eklentiler, kayıtlar | Hayır |
| `cikti/` | Her işin çıktıları (`cikti/<iş-kimliği>/`) | Hayır |
| `atolye.toml` | Senin ayarların | Hayır |

Her şeyi silmek istersen depo klasörünü silmen yeterli. Kurulum klasörün dışına yalnız iki şey bırakır:
`uv`'nin kendisi (`%USERPROFILE%\.local\bin\uv.exe`) ve uv'nin önbelleği (`%LOCALAPPDATA%\uv`). Yer açmak
istersen önbelleği `uv cache clean` ile temizleyebilirsin.

## Linux notları

Kurulum betiği Windows'ta denendi. Linux için de aynı betik var: `bash kurulum/kur.sh` (başlatmak için
`bash baslat.sh`). Linux'ta kendi torch tekerleklerini (`manylinux_2_28_x86_64`, özetleri sabit) seçer, eklentileri
Linux kaynaklarından derler; Visual Studio gerekmez. Ama Linux'ta uçtan uca **denenmedi.** Betik takılırsa
aşağıdaki el ile kurulum, betiğin yaptıklarının adım adım karşılığıdır. Deneyen olursa sonucu paylaşırsa çok iyi
olur.

Gerekenler: NVIDIA sürücüsü (CUDA 12.8 destekli), CUDA Toolkit 12.x (`nvcc`), `gcc`/`g++`, `git`, Blender 4.2+
ve [uv](https://docs.astral.sh/uv/).

```bash
# depo kökünden
uv run --no-project --python 3.12 python -I kurulum/kur.py ayar          # atolye.toml oluşur; blender ve cuda yollarını düzenle
uv run --no-project --python 3.12 python -I kurulum/kur.py indir --xpart-yok

# Python ortamı (kur.py ortam'ın Linux karşılığı, el ile)
uv venv .atolye/venv --python 3.12 --seed
PY=.atolye/venv/bin/python
uv pip install --python $PY torch==2.11.0+cu128 torchvision==0.26.0+cu128 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python $PY -r kurulum/gereksinimler.txt -c kurulum/kisitlar.txt --no-build-isolation-package basicsr
uv pip install --python $PY torch_scatter torch_cluster -c kurulum/kisitlar.txt -f https://data.pyg.org/whl/torch-2.11.0+cu128.html

# Hunyuan kodu, betikle aynı sabit sürümler
kod() { mkdir -p .atolye/kod/$1 && git -C .atolye/kod/$1 init -q && git -C .atolye/kod/$1 remote add origin $2 \
  && git -C .atolye/kod/$1 fetch -q --depth 1 origin $3 && git -C .atolye/kod/$1 checkout -q FETCH_HEAD; }
kod Hunyuan3D-2.1  https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1  82920d643c0dc2f7bfd7255f45f62d386edfe60c
kod Hunyuan3D-Part https://github.com/Tencent-Hunyuan/Hunyuan3D-Part e96be065375438962375b55326416291342958a7
kod Hunyuan3D-2    https://github.com/Tencent-Hunyuan/Hunyuan3D-2    f8db63096c8282cb27354314d896feba5ba6ff8a

# eklentiler (TORCH_CUDA_ARCH_LIST: kartının compute capability'si, ör. RTX 30 = 8.6, RTX 40 = 8.9)
mkdir -p .atolye/derleme && cd .atolye/derleme
CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.6 ../venv/bin/python -I ../../kurulum/eklenti_derle.py \
  build_ext --build-lib . --build-temp tmp
cd ../..

# başlat
uv run --no-project --python 3.12 python -I kurulum/kur.py baslat
```

Kartının compute capability değerini `nvidia-smi --query-gpu=compute_cap --format=csv,noheader` gösterir.
