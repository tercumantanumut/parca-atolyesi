# Rotalar ve VRAM

Parça Atölyesi'nde iki rota var: **Hafif** ve **Parçalı.** Hangisini seçeceğin ekran kartının belleğine (VRAM)
ve ne istediğine bağlı. Panel kartının VRAM'ini okur ve çalışamayacak rotaları kilitler. Bu sayfa da nedenini
anlatıyor.

Adımlar sırayla, **her biri kendi işleminde** çalışır. Bir adım bitince belleğini tamamen geri verir. O yüzden
gereken VRAM, adımların toplamı değil, **en çok isteyen adımın tepesi** kadardır.

## Kısa tablo

| Kartın VRAM'i | Ne çalışır | Ne alırsın |
|---|---|---|
| **8 GB** | Hafif, **doku kapalı** (yalnız şekil) | Dokusuz mesh, kil renginde toon, piksel |
| **12 GB** | Hafif, yalnız şekil (rahat). Doku ve Parçalı panelde uyarıyla açılır, ama 13–14 GB istedikleri için taşar ve yavaşlar | Dokusuz mesh. Sabırla: doku ya da parçalar |
| **16 GB** | **Hafif** ve **Parçalı**, dokulu | Her şey (16 GB'ta pay az); X-Part çok yavaş, denemedik |
| **24–32 GB** | Hafif ve Parçalı, rahat; **+ X-Part** yavaş | Her şey; X-Part belleği taşırır, ~13 dk sürer |
| **40 GB ve üstü** | Hepsi, **+ X-Part** hızlı | Kapalı, temiz parça meshleri, ~5–7 dk |

### 16 GB'lık kartta panel ne gösterir?

Örnek: RTX 4060 Ti 16 GB, RTX 5070 Ti. Bu tablo panelin koduna (`web/app/main.js`) dayanıyor. 16 GB'lık bir kartta
ekran görüntüsü almadık. Kart kendini 15,9 ya da 16 GB olarak bildirir, uyarılarda o sayı yazar.

| Kart | Durum | Panelde yazan |
|---|---|---|
| **Hafif** | Seçilebilir, dokulu | `tepe 14 GB` · ⚠ `Sınırda · 16 GB'ta pay az kalır` |
| **Parçalı** | Seçilebilir, dokulu | `tepe 14 GB` · ⚠ `Sınırda · 16 GB'ta pay az kalır` |
| **+ X-Part** | Parçalı'da seçilebilir (model indirildiyse) | `~35 GB` · `Kapalı, temiz parça meshleri · 12+ dk` · ⚠ `~35 GB ister; bu kartta Windows belleğe taşır, yavaşlar` |

- **Doku** kutusu çıkmaz. O kutu yalnız 14 GB'tan küçük kartlarda görünür. 16 GB'ta doku hep açıktır.
- X-Part seçiliyken **Başlat**'a basınca panel onay ister: "Adım 12 dakikadan uzun sürebilir. Başlatılsın mı?"
- X-Part modeli indirilmemişse kart kilitli görünür: `X-Part modeli indirilmemiş`.

## Hafif rota

**Hunyuan3D-2.1 ile şekil + PBR doku, ardından toon ve piksel. Parçalara ayırma yok.**

```
01 Görsel → 02 Şekil → 03 Doku → 07 Toon → 08 Piksel
```

- **Tepe VRAM ~14 GB** (03 Doku adımı). **12–16 GB kartlar için.**
- 14 GB'tan küçük kartlarda panelde **Doku** kutusu belirir ve **kapalı** gelir. Kapalıyken tepe **~8 GB**:
  yalnız şekil üretilir, toon render dokusuz (kil rengi) olur. **8 GB kartlar** için bu yol var.
- **12 GB'ta doku:** kutuyu açabilirsin, ama 14 GB'lık adım karta sığmaz. Windows hata vermek yerine fazlasını
  sistem belleğine taşır ve adım çok yavaşlar (saniyeler yerine dakikalar). Bunu ölçmedik. Denersen sabırlı ol.
- **8 GB'ta şekil de sınırda:** şekil adımı RTX 5090'da 8,2–8,5 GB'a çıktı. 8 GB'lık kartta biraz taşabilir ve
  yavaşlayabilir.
- Hazır bir mesh verirsen (GLB, OBJ, PLY, STL) Hafif rota hiçbir GPU modeli kullanmaz, yalnız toon + piksel
  yapar.

## Parçalı rota

**Hafif'in yaptığı her şey + P3-SAM ile parçalara ayırma + her parça için ayrı GLB.**

```
01 Görsel → 02 Şekil → 03 Doku → 04 Parçalar (P3-SAM) → 05 Ayrık → 07 Toon → 08 Piksel
                                                          ↘ 06 X-Part (isteğe bağlı, ~35 GB)
```

- **Tepe VRAM yine ~14 GB** (03 Doku). P3-SAM ~13 GB ister ama kendi başına çalışır, dokuyla aynı anda değil.
- **16 GB'ta** çalışır, ama ekranın, tarayıcının ve açık oyunların da VRAM kullandığını unutma. Panel bu yüzden
  "Sınırda" der. Diğer GPU uygulamalarını kapat.
- **Doku kapalıyken** (küçük kartlar) tepe ~13 GB (P3-SAM): dokusuz şekil ve dokusuz parçalar. 12 GB'lık kartta
  panel bunu "13 GB ister" uyarısıyla açar. Çalışır ama taşma yüzünden yavaşlar.
- P3-SAM'in kullandığı Sonata modelinin ağırlıkları ticari olmayan bir lisansla geliyor. Ticari bir oyun
  yapıyorsan önce [lisanslar.md](lisanslar.md#sonata-ve-parçalı-rota-ticari-kullanım) sayfasını oku.

### + X-Part (her kartta seçilebilir, ~35 GB ister)

X-Part her parçayı **kapalı, kendi başına duran bir mesh** olarak baştan üretir. Gövdenin arkasında kalan,
görünmeyen yüzeyleri de doldurur. Bunun bedeli büyük:

- **Tepe ~35 GB** (octree 384). 40 GB ve üstü kartta **~5–7 dakika**.
- Panel X-Part'ı **her kartta seçtirir.** Kartın bu kadar belleği yoksa uyarır ("~35 GB ister; bu kartta Windows
  belleğe taşır, yavaşlar") ve başlamadan onay ister. Windows kalanını paylaşılan sistem belleğine taşır; adım
  biter ama yavaşlar. RTX 5090'da (32 GB) ölçtük: P3-SAM ön çalışması 43 sn + yükleme 31 sn + üretim 710 sn, toplam ~13 dakika, tepe 35,4 GB, 12 kapalı parça. Daha küçük kartlarda daha da uzun sürer; denemedik.
- X-Part parçaları **yeni geometri**dir: UV'leri ve dokuları yoktur. Renkli parçalar istiyorsan 05 Ayrık'ın
  dokulu parçalarını kullan.
- X-Part'ı kullanmayacaksan hiç indirme (9 GB): `kurulum\kur.ps1 hepsi --xpart-yok`.

## Ön + arka görsel (isteğe bağlı)

Karakterin arkadan çizimi de varsa panelde **+ arka** ile ekleyebilirsin. Şekil o zaman Hunyuan3D-2mv ile iki
görselden üretilir, sırt daha doğru çıkar. Doku yine 2.1 ile, ön görselden boyanır. Bunun için `2mv` model
grubu inmiş olmalı (4,9 GB, varsayılan kurulumda iner). İnmemişse şekil yalnız ön görselden üretilir ve
günlükte bunu söyleyen bir satır çıkar. RTX 5090'da 2mv ~17 sn yükleme + ~31 sn çalışma, **~9,5 GB** (2.1'in 7,6 GB'ından biraz fazla).

## Ölçümler (RTX 5090, 32 GB)

Paneldeki referans süreler ve VRAM değerleri bu ölçümlerden geliyor. Hepsi **RTX 5090 ölçümü.** Daha yavaş
kartlarda süreler uzar, VRAM aşağı yukarı aynı kalır.

| Adım | Model yükleme | Çalışma | Tepe VRAM |
|---|---|---|---|
| 02 Şekil (Hunyuan3D-2.1, octree 384, 50 adım) | ~20 sn | ~34 sn | 7,6 GB |
| 03 Doku (2.1 PBR boyama, 6 görünüm × 512 px) | ~15–22 sn | ~55–60 sn | 13,5 GB (15 GB sınırla da aynı hızda) |
| 04 Parçalar (P3-SAM) | ~1,5 sn | 16–27 sn | 12–13 GB |
| 05 Ayrık (parça başına GLB) | – | ~8 sn | CPU |
| 06 X-Part (octree 384) | ~31 sn | ~710 sn (32 GB kartta, taşarak); 40 GB+ kartta ~5–7 dk | 35,4 GB |
| 07 Toon (Blender, EEVEE) | – | ~2–3 sn | < 0,2 GB |
| 08 Piksel | – | < 1 sn | CPU |

**Kullanılan ve ayrılan bellek.** PyTorch belleği önbellekli yönetir: kartta yer varsa gerçekten kullandığından
fazlasını ayırır ve elinde tutar (Doku adımı RTX 5090'da ~13,5 GB kullanıp ~20,4 GB ayırıyordu). Windows'ta bu
tehlikelidir: kart dolunca hata vermez, sessizce sistem belleğine taşar ve adım 20–50 kat yavaşlar. Bu yüzden
atölyenin GPU adımları, başlarken kartta **boş olan VRAM'i** (eksi küçük bir pay) PyTorch'a üst sınır olarak verir.
Sınıra gelen PyTorch önbelleğini boşaltıp devam eder; iş gerçekten sığmıyorsa da yavaşlamak yerine hemen
"VRAM yetmedi" hatası verir. Panel her adımın **kullandığı** belleği (tepe) gösterir; ayrılan ve kart düzeyinde
ölçülen değerler adımın ayrıntısında (`*.json`) durur. RTX 5090'da Doku adımını 15 GB sınırla çalıştırdık: aynı
sürede bitti (16 GB'lık kartın durumu). 11 GB sınırla hemen "VRAM yetmedi" dedi. Gerçek bir 16 GB kartta ayrıca
ölçmedik; ekranın ve tarayıcının da VRAM kullandığını unutma.

Kabaca toplam süre (RTX 5090, model yükleme dahil): **Hafif ~2,5 dakika, Parçalı ~3 dakika,** X-Part ile
**+5–7 dakika** (40 GB+ kart), 32 GB'ta **+~13 dakika.** Atölye X-Part'ı octree 384 ile çalıştırır.

### "Neden bu kadar yavaş?" Bellek taşması

Windows'ta VRAM yetmeyince genellikle "out of memory" hatası almazsın. Sürücü fazlasını sessizce **paylaşılan
sistem belleğine** taşır ve adım 20–50 kat yavaşlar. Bir GPU adımı tablodaki süreden çok daha uzun sürüyorsa
sebep neredeyse her zaman budur:

- Görev Yöneticisi → Performans → GPU: "Paylaşılan GPU belleği" dolmaya başladıysa taşma var.
- Diğer GPU kullanan uygulamaları kapat (oyunlar, başka yapay zekâ araçları, donanım hızlandırmalı tarayıcı
  sekmeleri).
- Doku'yu kapat ya da Hafif rotaya geç.

Daha fazlası: [sorun-giderme.md](sorun-giderme.md).
