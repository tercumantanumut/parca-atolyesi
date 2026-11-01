# Sorun giderme

Önce iki yere bak:

- **Kurulum sorunlarında:** `.atolye\kayit\kurulum.log`. Kurulumun yazdığı her satır burada.
- **Bir iş takıldıysa ya da hata verdiyse:** paneldeki **Günlük**, ya da diskte `cikti\<iş-kimliği>\is.log`.
  Başarısız adımın son satırları panelde de özetlenir.

## Kurulum

### "running scripts is disabled on this system" / betik çalışmıyor

PowerShell betikleri varsayılan olarak engeller. Komutları bu rehberdeki gibi
`powershell -ExecutionPolicy Bypass -File ...` ile çalıştır. Bu izin yalnız o komut için geçerlidir.

### "git bulunamadı"

Git'i <https://git-scm.com/download/win> adresinden kur, PowerShell'i **kapatıp yeniden aç,** komutu tekrar
çalıştır.

### "uv bulunamadı"

`kur.ps1` uv'yi kendisi kurar. Kurulum engellendiyse uv'yi el ile kur:

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### İndirme koptu, yarıda kaldı, çok yavaş

Sorun değil. **Aynı komutu yeniden çalıştır.** İnmiş dosyalar atlanır, yarım kalan dosya (`.part`) kaldığı yerden
devam eder. Bağlantı koparsa betik kendisi de birkaç kez yeniden dener.

Önce zorunlu grupları indirip sonra devam etmek istersen:

```powershell
powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1 indir sekil doku parcalar
```

### "özet tutmadı" (dosya bozuk indi)

Bozuk dosya `<ad>.bozuk` adıyla bırakılır. O dosyayı sil ve indirmeyi yeniden çalıştır. Bütün dosyaları baştan
kontrol etmek için:

```powershell
powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1 dogrula --tam
```

### "HTTP 401 / 403 / 404"

Bağlantın Hugging Face'e ya da GitHub'a ulaşamıyor olabilir: şirket ağı, proxy, DNS engeli. Tarayıcıda
<https://huggingface.co/tencent/Hunyuan3D-2.1> açılıyor mu, bak. Modeller "gated" değil, hesap gerekmez.

### "Visual Studio C++ ortamı bulunamadı"

`atolye.toml` içindeki `vsvars` yolu yanlış. Visual Studio Installer'da **"C++ ile masaüstü geliştirme"**
iş yükünün kurulu olduğundan emin ol, sonra `vcvars64.bat` dosyasının gerçek yerini yaz. Sık görülen yollar:

```toml
vsvars = "C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Auxiliary/Build/vcvars64.bat"
vsvars = "C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Auxiliary/Build/vcvars64.bat"
```

Sonra yalnız ortam adımını yeniden çalıştır:

```powershell
powershell -ExecutionPolicy Bypass -File kurulum\kur.ps1 ortam
```

### Eklentiler derlenmiyor (nvcc, CUDA hataları)

- `atolye.toml` içindeki `cuda` yolu kurduğun CUDA Toolkit klasörünü göstermeli ve içinde `bin\nvcc.exe`
  olmalı.
- **RTX 50 serisi:** CUDA Toolkit 12.8'den eskiyse eklenti, kartın sürücüsünün ilk çalıştırmada derlediği ara
  koda (PTX) göre üretilir. Bu bilerek böyle, çalışır. Toolkit 12.8 ya da üstüyse doğrudan kartın kendi mimarisi
  için derlenir.
- Mimariyi kendin seçmek istersen `atolye.toml` içinde `cuda_arch = "8.6"` gibi yaz (kartının değeri:
  `nvidia-smi --query-gpu=compute_cap --format=csv,noheader`).
- Hatanın tamamı `.atolye\kayit\kurulum.log` dosyasında.

### "DOĞRULAMA: EKSİK VAR"

Tabloda `eksik` yazan grubun dosyaları tam inmemiş. `kur.ps1 indir` ile tamamla. `2mv` ve `xpart` isteğe
bağlıdır. Onlar eksikse yalnız o özellikler kapalı kalır.

## Panel

### "Sunucu yok" / sayfa açılmıyor

- `baslat.ps1` penceresi açık mı? Kapattıysan sunucu da durdu. Yeniden başlat.
- "Önce kurulum: kurulum/kur.ps1" yazıyorsa Python ortamı yok: kurulumu tamamla.
- Adres `http://127.0.0.1:8731`. Başka bir program 8731 portunu kullanıyorsa `atolye.toml` içinde portu değiştir:

  ```toml
  [sunucu]
  port = 8740
  ```

### Bir rota kilitli

Kilidin yanında nedeni yazar:

| Yazı | Çözüm |
|---|---|
| NVIDIA ekran kartı bulunamadı | `nvidia-smi` çalışıyor mu? Sürücüyü güncelle |
| … modeli indirilmemiş | `kurulum\kur.ps1 indir` |
| Kurulum tamamlanmamış | `kurulum\kur.ps1 ortam` |
| En az 8 GB VRAM gerekir | Kartın bu iş için küçük. Hazır bir mesh verirsen Hafif rota yine çalışır |
| X-Part modeli indirilmemiş | `kurulum\kur.ps1 indir xpart`. X-Part artık her kartta seçilebilir; ~35 GB'tan az VRAM'de uyarı çıkar ve yavaş çalışır. Bkz. [rotalar-ve-vram.md](rotalar-ve-vram.md) |

### 07 Toon "Blender yok"

`atolye.toml` içinde Blender yolunu yaz (düz eğik çizgiyle) ve sunucuyu yeniden başlat:

```toml
[yollar]
blender = "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"
```

Blender 4.2 ya da daha yenisi gerekir.

## Çalışırken

### Bir adım dakikalardır bitmiyor

Neredeyse her zaman **VRAM taşması**dır. Windows'ta bellek yetmeyince hata yerine paylaşılan sistem belleği
kullanılır ve adım 20–50 kat yavaşlar.

- Görev Yöneticisi → Performans → GPU → "Paylaşılan GPU belleği" artıyor mu?
- Ekran kartını kullanan diğer uygulamaları kapat: oyunlar, başka yapay zekâ araçları, video düzenleyiciler,
  çok sekmeli tarayıcılar.
- Küçük kartta **Doku**'yu kapat ya da **Hafif** rotaya geç.
- Normal süreler (RTX 5090): şekil ~1 dk, doku ~1,5 dk, parçalar ~20 sn. Daha yavaş kartta birkaç katı olabilir,
  ama 10 katı olmamalı.

### "VRAM yetmedi"

Adım "out of memory" ile durdu. Yukarıdaki maddeler geçerli. Ayrıca bir önceki iş hâlâ çalışıyor olabilir:
Geçmiş'e bak.

### "Sunucu iş sürerken kapandı"

İş sürerken `baslat.ps1` penceresi kapandı ya da bilgisayar uyudu. Sunucuyu yeniden başlat ve aynı görselle
işi yeniden başlat.

### "Görsel çok küçük ya da çok büyük"

Görsel en az 64 × 64 piksel, en çok 64 megapiksel olmalı. Dosya en fazla 300 MB olabilir.

## Sonuç beklediğim gibi değil

| Belirti | Ne yap |
|---|---|
| Şekil bozuk, eksik, fazladan yumrular var | Tohumu değiştir (zar). 2–5 deneme çoğu zaman yeter |
| Bir kol, etek ya da beyaz giysi kesilmiş | Arka plan temizliği yemiş. `input_rgba.png`'ye bak. Düz açık bir arka plan ya da şeffaf PNG ver. Bkz. [gorsel-ipuclari.md](gorsel-ipuclari.md#arka-plan) |
| Dokuda sert gölge ve parlama var | Görseldeki ışık dokuya geçti. Daha düz ışıklı bir görsel kullan |
| Arka taraf saçma | Model arkayı tahmin ediyor. Karakterse **+ arka** ile arka görseli de ver |
| Parçalar çok ince ya da çok kaba | P3-SAM'in ayrıntı düzeyi meshten meshe değişir. Yeni bir şekil tohumu dene. Komut satırından `parcalar --birlestir` küçük parçaları birleştirir ([adim-adim.md](adim-adim.md), "İleri seviye" bölümü) |
| Parça adları yanlış (`accessory` çok) | Adlar kaba tahmin. İnsansı olmayan modellerde çoğu `accessory` çıkar. Adları kendin ver |
| Sprite'ta ayrıntılar kayboldu | Boyu büyüt (160 ya da üstü) ya da daha kalın hatlı bir görsel kullan |
| Sprite renkleri soluk ya da tuhaf | Paleti değiştir: `Özgün` görselin kendi renklerini kullanır |

## Disk doluyor

Her iş `cikti\` altında birkaç on MB yer kaplar. X-Part'lı işler daha fazla. Gereksiz işleri panelin
Geçmiş'inden sil. İş klasörüyle birlikte silinir.

## Hâlâ çözülmediyse

Sorunu bildirirken şunları ekle: ekran kartı ve VRAM'i, Windows sürümü, `nvidia-smi` çıktısının üstü, hangi
rota, ve `.atolye\kayit\kurulum.log` ya da `cikti\<iş>\is.log` dosyasının son 50 satırı.
