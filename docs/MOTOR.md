# Motor: arka uç ve kurulum

Bu sayfa atölyenin arka ucunu anlatır: kurulumun ne indirip neyi derlediği, sunucunun ve iş kuyruğunun nasıl
çalıştığı, her adımın gerçekte ne kadar sürdüğü ve ne kadar VRAM kullandığı. Arayüz için
[ARAYUZ.md](ARAYUZ.md), API sözleşmesi için `design/PLAN.md` ("API contract" ve "API additions").

## Parçalar

```
kurulum/kur.ps1, kur.sh     önyükleyici: uv'yi bulur ya da kurar, kur.py'yi Python 3.12 ile çalıştırır
kurulum/kur.py              kurulum (yalnız standart kütüphane): ayar, indir, ortam, kod, dogrula, hepsi, baslat
kurulum/kaynaklar.py        ne indirilecek: torch tekerlekleri, sabitlenmiş kod kopyaları, model grupları
kurulum/eklenti_derle.py    doku adımının iki yerel eklentisi (yamalı kopyalardan)
atolye/ayar.py              atolye.toml (tek ayar dosyası; ortam değişkeni yok)
atolye/modeller.py          hangi model grubu diskte tam (GET /api/sistem için, çevrimdışı)
atolye/gpu.py               VRAM ölçümü: NVML, yoksa nvidia-smi
atolye/hy_ortam.py          Hunyuan kodunu çevrimdışı ve dokunmadan çalıştıran yamalar
atolye/stages/*.py          adımlar: sekil, doku, parcalar, ayrik, xpart, toon, piksel
atolye/isler.py             işler, olaylar, kuyruk (aynı anda tek GPU işi)
atolye/sunucu.py            HTTP sunucu (yalnız standart kütüphane): API, SSE, çıktılar, web/
blender/toon_still.py       Blender'da (arka planda) cel gölgeli tek kare
paletler/*.hex              piksel adımının hazır paletleri
tests/                      pytest (GPU gerektirmez; GPU adımlarının yerine tests/sahte_adim.py)
```

## Kurulum nasıl çalışır

`kurulum\kur.ps1` (Linux'ta `kurulum/kur.sh`, denenmedi) uv'yi bulur, yoksa kurar; sonra `kur.py`'yi uv'nin
getirdiği Python 3.12 ile `-I` (yalıtılmış) çalıştırır. `kur.py hepsi`:

1. **ayar:** `atolye.toml` yoksa `atolye.ornek.toml`'dan kopyalar. Bütün yollar buradadır: `modeller`, `veri`
   (venv, kod kopyaları, derlenen eklentiler, tekerlekler, kayıtlar), `cikti`, `blender`.
2. **indir** (arka planda, ortamla aynı anda): model grupları sırayla: `sekil` (8,2 GB) → `doku` (11,5 GB) →
   `parcalar` (0,9 GB) → `2mv` (4,9 GB, isteğe bağlı) → `xpart` (9,0 GB, isteğe bağlı, en son; `--xpart-yok` ile
   atlanır). Hugging Face dosyaları bir commit'e sabitlidir. Her dosya `.part` olarak iner, kopan bağlantıda
   `Range` ile kaldığı yerden sürer (60 deneme, artan bekleme), bitince Hub'ın o commit'teki listesine göre
   doğrulanır (büyük dosyalarda sha256, küçüklerde git blob sha1), sonra adını alır. Liste
   `<modeller>/.liste/` altına yazılır; doğrulanan dosyalar bir kez hash'lenir (`dogrulanan.json`). Real-ESRGAN
   yayınlanan sha256 ile, u2net rembg'nin md5'i ile doğrulanır.
3. **ortam:** `uv venv` (3.12) → torch 2.11.0+cu128 ve torchvision 0.26.0+cu128 tekerlekleri (sabit sha256 ile,
   platforma göre) → `gereksinimler.txt` + `kisitlar.txt` → torch_scatter / torch_cluster (PyG cu128) → kod
   kopyaları (Hunyuan3D-2.1 @ 82920d6, Hunyuan3D-Part @ e96be06, Hunyuan3D-2 @ f8db630; `git fetch --depth 1`
   sabit SHA) → eklentiler.
4. **eklentiler:** `custom_rasterizer_kernel` (CUDA) ve `mesh_inpaint_processor` (C++/pybind11), kod
   kopyasından alınıp yamalanan kopyalardan `<veri>/derleme`'ye. İki yama: `rasterizer.h` nvcc altında
   `<torch/types.h>` (MSVC + nvcc 12.x'in `'std': ambiguous symbol` hatası), `rasterizer_gpu.cu`'da z-buffer
   `int64` okunup `uint64_t*`'ye çevrilir (torch ≥ 2.3'ün `expected scalar type UInt64 but found Long` hatası).
   `TORCH_CUDA_ARCH_LIST` kendiliğinden seçilir: kartın compute capability'si; RTX 50 + CUDA < 12.8 ise
   `9.0+PTX` (sürücü JIT ile derler). Windows'ta Visual Studio 2022 C++ araçları (`vcvars64.bat`) ve CUDA
   Toolkit 12.x gerekir (yollar `atolye.toml [kurulum]`).
5. **dogrula:** her grubu boyutla (ya da `--tam` ile hash'le) denetler, tablo basar.

Her adım yeniden çalıştırılabilir; biten iş atlanır. Kayıt: `<veri>/kayit/kurulum.log`.

**Bağlantılar ya da sembolik linkler kullanılmaz.** Ağır klasörler `atolye.toml`'daki mutlak ya da depo köküne
göre yollarda durur; birden fazla çalışma kopyası aynı modelleri yol vererek paylaşır.

## Çalıştırma

```
baslat.ps1                                   # ya da: python -I kurulum/kur.py baslat
<venv>\Scripts\python.exe -m atolye          # depo kökünden, aynı şey
```

Sunucu `http://127.0.0.1:8731` (yalnız yerel). Tek bir adımı elle çalıştırmak:
`<venv>\Scripts\python.exe -I atolye\calis.py <adim> --help`.

## Bir iş nasıl yürür

- `POST /api/is` görseli (ya da hazır mesh'i) `<cikti>/<id>/` altına yazar, rotaya göre her adımın başlangıç
  durumunu çıkarır (`bekliyor` ya da nedeniyle `atlandi`) ve işi kuyruğa koyar. Tek bir koşucu iş parçacığı
  işleri sırayla alır: **aynı anda tek GPU işi.**
- Model adımları (02 Şekil, 03 Doku, 04 Parçalar) **uzun ömürlü GPU işçilerinde** çalışır
  (`atolye/isci.py`, sunucu ilk lazım olduğunda başlatır, stdin'den satır satır JSON komut alır). İki işçi var:
  `hy21` (2.1 şekil, 2mv, 2.1 boyama) ve `part` (P3-SAM). Hunyuan3D-2.1 ile Hunyuan3D-Part aynı adlı üst
  paketler (`utils`, `models`) taşıdığı için aynı Python sürecinde yaşayamaz. 05, 06 X-Part, 07 ve 08 eskisi gibi
  ayrı süreçtir (`<venv>/python -I atolye/calis.py <adim> ...`). Sunucu kapanınca işçiler stdin'leri kapandığı
  için kendiliğinden çıkar.
- **Modelleri bellekte tut** (`atolye.toml [bellek] modelleri_tut`, varsayılan açık; panelin üstündeki anahtar
  bunu `POST /api/ayar` ile değiştirir, seçim `<veri>/durum.json`'da kalır): işçi yüklediği pipeline'ı işler
  arasında ekran kartında tutar, ikinci iş yüklemeyi atlar. Kapalıyken bir model, işin onu kullanan son
  adımından sonra boşaltılır. Bir adımdan önce kartta (NVML ile ölçülen) boş VRAM modelin ölçülmüş ihtiyacından
  (`atolye/ihtiyac.py`) azsa önce **öbür** işçinin tuttuğu modeller, sonra işçinin kendi modelleri en uzun süredir
  kullanılmayandan başlayarak boşaltılır; işin sonraki adımlarının modeli en son gider. X-Part'tan önce iki işçi de
  her şeyi boşaltır. Adım olayında `bellek: "bellekte" | "yuklendi"`, günlükte "model bellekte / yüklendi /
  boşaltıldı" satırları çıkar. Boşaltma tamdır (gc + `torch.cuda.empty_cache`); yeniden yükleme diskten olur.
- **GPU kilidi:** her GPU adımı `<veri>/gpu.kilit` dosyasını kilitler; elle başlatılan bir adım sunucunun adımını
  (ya da tersi) bekler.
- Adımlar stdout'a küçük bir satır protokolü basar: `@@faz a b`, `@@cubuk a b <tqdm etiketi>` (o tqdm çubuğu
  adımın a..b aralığına eşlenir), `@@ilerleme x`, `@@sonuc {json}`. Koşucu tqdm yüzdelerini adım ilerlemesine,
  diğer satırları günlüğe çevirir (biten her çubuk tek satır), sonucu adımın `ayrinti`'sine koyar.
- Her olay işin olay listesine eklenir ve SSE ile yayınlanır (`id:` numaralı; `Last-Event-ID` ile kaldığı yerden).
  Yeni bağlanan önce bir anlık görüntü alır. İş durumu her adım değişiminde `is.json`'a yazılır; sunucu yeniden
  açılınca işler diskten yüklenir, yarıda kalan iş `sunucu_durdu` hatasıyla kapanır, bekleyenler kuyruğa döner.
- 07/08'i yeniden çizdirmek (`POST /api/is/{id}/toon|piksel`) eşzamanlıdır (birkaç saniye), GPU adımlarını
  tekrar çalıştırmaz. Sonunda `paket.zip` yeniden yazılır.

### VRAM: sınır koyma ve dürüst ölçüm

Kartın boş belleği **NVML ile** okunur: WDDM'de `torch.cuda.mem_get_info()` yalnız kendi sürecinin payını
gösterir, öbür işçinin tuttuğu modelleri görmez (bu yüzden ilk denemede P3-SAM 35 sn yerine 20 dk sürdü).
Windows'ta (WDDM) kart dolunca CUDA hata vermez: sürücü sessizce sistem belleğine taşar, adım 20–50 kat
yavaşlar. PyTorch'un önbellekli ayırıcısı da kullandığından fazlasını tutar (Doku: 13,5 GB kullanıp 20,4 GB
ayırıyordu). Bu yüzden her GPU adımı başlarken `torch.cuda.set_per_process_memory_fraction` ile ayırıcıyı
kartta **boş olan VRAM'e** (eksi 0,4 GB) sınırlar. Sınıra gelen ayırıcı önbelleğini boşaltıp devam eder; gerçekten
sığmayan adım taşmak yerine hemen `<adim>_vram_yetmedi` hatası verir. `atolye.toml [sinirlar]`:
`vram_tasma = true` sınırı kaldırır, `vram_siniri_gb = 15` küçük bir kartı denemek için sabit sınır koyar.

Panelde ve API'de `tepe_vram_gb` adımın **kullandığı** en yüksek bellektir (torch allocated). `ayrinti` içinde
`tepe_ayrilan_gb` (torch reserved) ve `tepe_vram_olculen_gb` (kart düzeyinde, 250 ms'de bir örneklenen artış)
da durur. GPU'suz adımlarda (07 Blender, 08) `tepe_vram_gb` kart düzeyindeki artıştır. Bütün boyutlar GiB'dir
(2^30 bayt; "32 GB" RTX 5090 31,84 görünür).

## Adımlar

| # | Adım | Ne yapar | Çıktılar |
|---|---|---|---|
| 01 | Görsel | Yükleme; arka plan 02'de temizlenir | `girdi_on.png` (`girdi_arka.png`) |
| 02 | Şekil | Arka plan (`auto`: saydamsa dokunmaz, kenarı düz açık renkse flood-fill, değilse u2net), kare kırpma; Hunyuan3D-2.1 (ya da ön + arka ile 2mv) | `input_rgba.png`, `input_back_rgba.png`, `shape.glb`, `sekil.json` |
| 03 | Doku | 2.1 PBR boyama: ~40k yüzlü yeniden örgü, 6 görünüm × 512, 2048² atlas; OBJ'yi glTF PBR'a çevirir (taban renk + metal/pürüz, JPEG) | `textured.glb`, `doku.json`, `doku/` (ara dosyalar) |
| 04 | Parçalar | P3-SAM, `shape.glb` üzerinde (`prompt_bs 8`) | `p3sam/` (renkli bölütleme, yüz kimlikleri, kutular), `p3sam.json` |
| 05 | Ayrık | Dokulu mesh'in her yüzü en yakın etiketli P3-SAM yüzünün parçasını alır (KD-ağacı); parça başına GLB, her birinde atlasın yalnız o parçanın kullandığı kısmı (gerisi siyah, sıkışır) | `parts/part_XX.glb`, `parts.glb` (tek atlas, görüntüleyici için), `parts.json` |
| 06 | X-Part | Önce birleştirmeli P3-SAM, sonra X-Part (octree 384); ≥ 40 GB kart | `xpart/parts.glb`, `xpart/parts_explode.glb`, `xpart/parts/` |
| 07 | Toon | Blender (arka planda, `--factory-startup`), ortografik, şeffaf, 1024²: albedo × 3 tonlu sıcak ışık rampası + soğuk kenar ışığı (emisyon, ışıksız), bulanıklaştırılmış normaller, ters kabuk dış çizgi | `toon_<on|ucceyrek|yan>.png` |
| 08 | Piksel | Gövde `boy` px, sabit ızgara, blok çoğunluk alfası, OKLab'da palete oturtma, temizlik, 1 px seçici dış çizgi | `piksel_<boy>.png` |

Paletler: `ozgun` / `ozgun-32` / `ozgun-16` (toon karesinden OKLab k-means; renklerin sekizde biri dış çizgi için
koyu tonlar), `endesga-32`, `pico-8`, `sweetie-16`, `gameboy-4`. Kanvas: yükseklik `boy × 1,6` (16'ya yuvarlı;
160 → 256), ayaklar alttan ~%8 yukarıda, nesne genişse kanvas genişler.

## Ölçümler

RTX 5090 (32 GB), Windows 11, sürücü 610.88, torch 2.11.0+cu128, CUDA Toolkit 12.6 (eklentiler `9.0+PTX`).
Örnekler `ornekler/`. Süre = duvar saati, model yükleme dahil; parantezde yükleme + çalışma. VRAM GiB:
kullanılan / ayrılan / kart düzeyinde.

| Adım | Ölçüm | VRAM |
|---|---|---|
| 02 Şekil, 2.1 | 58,7–60,6 sn (18–20 + 34–35) | 7,6 / 8,5 / 9,0 |
| 02 Şekil, 2mv (ön + arka) | ~52 sn (16,8 + 30,6); işçide yükleme 18 sn | 9,5 / 11,2 / – |
| 03 Doku | 74–92 sn (15–22 + 55–71) | 13,4 / 20,4 / 21,1 |
| 03 Doku, 15 GB sınırla | 56,9 sn çalışma (sınırsızla aynı) | 13,5 / 14,5 / – |
| 03 Doku, 11 GB sınırla | ~50 sn sonra `vram_yetmedi` | – |
| 04 Parçalar (maceraci) | 35–41 sn (1,6 + 27); 17–21 parça | 12,2 / 17,6 / 18,2 |
| 05 Ayrık | 7–8 sn (CPU) | – |
| 06 X-Part (maceraci, octree 384, 32 GB kart) | P3-SAM ön çalışma 43 sn + yükleme 31 sn + üretim 710 sn; 12 kapalı parça | 35,4 / 46,5 / kart dolu (taşıyor) |
| 07 Toon | 1,7–3,5 sn (Blender açılışı dahil) | ≤ 0,9 (kart) |
| 08 Piksel | 0,3–0,8 sn | – |
| **Hafif rota** (tas_golem, hazine_sandigi) | 136–155 sn | tepe 13,5 |
| **Hafif rota, modeller bellekte** (ikinci iş) | 90 sn (Şekil 35 sn, Doku 53 sn; yükleme 0) | bellekte 6,9 + 6,6 GB |
| **Parçalı rota, modeller bellekte** (tas_golem) | 138 sn (Şekil 35, Doku 55, P3-SAM 40 sn) | P3-SAM 12,2 (yanında 13,5 GB tutulurken, taşmadan) |
| **Parçalı + X-Part** (maceraci, sunucudan) | 979 sn; X-Part 780 sn (iki işçi önce her şeyi boşaltır) | X-Part 36,8 (kart dolu, taşıyor) |
| **Parçalı rota** (maceraci) | 178–187 sn | tepe 13,4 |

Kurulum (bu makinede, ~4 MB/s): ortam 27 dk (torch tekerleği 2,75 GB dahil; uv önbelleği paketlerin bir kısmını
hızlandırdı), modeller: `sekil` 36 dk, `doku` 41 dk, `parcalar` 3 dk, `2mv` 19 dk.

## Testler

```
<venv>\Scripts\python.exe -m pytest -q tests
```

GPU gerekmez: piksel (kanvas, palet, dış çizgi), ayrık (etiket aktarımı, parça dokusu maskesi, insan biçimli
tahminler), kurulum (kaldığı yerden indirme, bozuk özet, git blob sha1, grup durumu, platform tekerlekleri),
plan (atlanan adımlar ve nedenleri) ve uçtan uca sunucu (çok parçalı yükleme, SSE ve `Last-Event-ID`, kuyruk
sırası, hata yayılımı, yeniden çizim, hazır mesh, CORS, yol aşımı). GPU adımlarının yerine `tests/sahte_adim.py`
aynı argümanları, dosyaları ve satır protokolünü üretir; 05/07/08 gerçek çalışır (Blender yoksa ilgili testler
atlanır). Canlı arayüz denetimi: `dev/canli.mjs` (hazır mesh) ve `dev/canli_gpu.mjs` (gerçek görselle GPU
adımları, `ROTA=hafif|parcali`).

## Açık konular

- **Linux denenmedi.** `kur.sh`, Linux tekerlekleri ve Linux eklenti kaynakları hazır, ama uçtan uca
  çalıştırılmadı.
- **16 GB kart.** Doku'nun 15 GB sınırla aynı hızda bittiği ölçüldü; gerçek bir 16 GB kartta (ekran ve tarayıcı
  da VRAM kullanırken) denenmedi.
- **Parça adları** (`guess`) dik duran insan biçimli karakter için kutu sezgisidir; çok aksesuarlı karakterde
  çoğu parça `accessory` olur, botlar ayak sayılmayabilir.
- **Büyük şekil dosyaları.** 2.1 şekli 0,6–1,6 milyon yüzlüdür (`shape.glb` 17–28 MB); görüntüleyici yükler ama
  ağırdır. Dokulu mesh ve parçalar 40k yüzdür.
- **İş silme.** Çalışan bir adım silinince süreç öldürülür; Windows'ta 07'nin açtığı Blender alt süreci bir an
  yaşayabilir.
- **Bellekte tutulan modeller** (Şekil 6,9 GB + Doku 6,6 GB + P3-SAM 0,4 GB) boşta da ekran kartında yer kaplar;
  aynı anda oyun ya da başka bir GPU işi çalıştıracaksan panelden kapat.
- **X-Part 32 GB kartta** paylaşılan belleğe taşarak ~13 dk sürer; ilk denemelerden biri yarıda sessizce kapandı
  (hata satırı yok), ikincisi bitti. 40 GB+ kartta ölçülmedi.
- **Sonata CC BY-NC 4.0** (P3-SAM'in omurgası): Parçalı rotanın ticari kullanımı ayrıca değerlendirilmeli
  (`docs/lisanslar.md`).
