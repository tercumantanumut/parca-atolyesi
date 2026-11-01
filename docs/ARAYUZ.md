# Arayüz (web/)

Parça Atölyesi'nin tarayıcı arayüzü: tasarım yönü **A · Tezgâh** (kâğıt ve mürekkep, amber çizgiler, mono etiketler).
Derleme adımı yok, paket yöneticisi yok. Düz HTML + CSS + ES modülleri; three.js yerel olarak `web/vendor/` içinde.
Sunucu (`atolye/sunucu.py`) bu klasörü `/` adresinden sunar; arayüz API'ye aynı adresten, göreli yollarla konuşur.

```
python -I atolye/calis.py sunucu          # http://127.0.0.1:8731/
python -I atolye/calis.py sunucu --web <klasör>   # başka bir web/ kopyasıyla
```

## Dosyalar

| Dosya | Ne yapar |
|---|---|
| `web/index.html` | İskelet: başlık, 8 adımlı şerit, sol (girdi + rota), orta (3D / Toon · Piksel), sağ (VRAM, günlük, parçalar, indir, geçmiş) |
| `web/app/tezgah.css` | Tezgâh görünümü (tasarımdaki CSS + gerçek uygulama durumları) |
| `web/app/main.js` | Durum, çizim, olaylar, API akışı |
| `web/app/api.js` | API istemcisi: istekler, SSE akışı, iş durumunu esnek okuma (`normJob`), çıktı adresleri (`ciktilar`) |
| `web/app/viewer.js` | 3D görüntüleyici: GLB yükleme, Dokulu / Kil / Parçalar, patlatma yayı, parça seçme, varış animasyonları, şerit küçük resimleri |
| `web/vendor/three/` | three.js 0.187.0 (MIT), yalnız kullanılan dosyalar |

## Ekran

- **Şerit (01–08):** her adımın kartı. Çalıştırmadan önce RTX 5090 ölçümleri görünür (süre · VRAM). Bir adım bitince
  kartı o adımın gerçek çıktısıyla dolar ve altındaki yazı bu çalıştırmanın ölçümüne döner (`tepe 13,1 GB`).
  Durumlar: bekliyor, `%` ile çalışıyor, ✓ süre, atlandı (nedeni üzerine gelince), kapalı, kilitli (`model yok`,
  `Blender yok`), hata.
- **Sol:** görseli bırak (ön, isteğe bağlı arka) ya da hazır bir mesh (GLB · OBJ · PLY · STL). Rota kartları
  (Hafif, Parçalı, + X-Part), tohum, Başlat. Bir iş açıkken o işin seçimleri görünür.
- **Orta:** 3D görünüm (döndür, sıfırla, Dokulu / Kil / Parçalar, Patlat). İş bitince **Toon · Piksel** sekmesi:
  toon render | 5× büyüteç (sürüklenebilir) | gerçek boyut. Altında açı (Ön · 3/4 · Yan), boy (160 · 128 · 80 · özel
  16–512) ve palet (görselden: Özgün 64/32/16; hazır: `.hex` paletleri, renk şeridiyle).
- **Sağ:** çalıştırmadan önce adım başına VRAM ihtiyacı ve kartın sınırı (kırmızı çizgi); çalışırken canlı VRAM
  (500 ms), tepe işareti ve günlük; bitince Parçalar (göster/gizle, üzerine gelince vurgula, tıklayınca seç),
  İndir (dosyalar ve boyutları), Geçmiş.

## Dürüst VRAM kapıları (`GET /api/sistem`)

| Durum | Arayüz |
|---|---|
| GPU yok | GPU gerektiren rotalar kilitli: "NVIDIA ekran kartı bulunamadı" |
| Model indirilmemiş (`modeller.*`) | O rotanın kartı kilitli, hangi model eksikse yazar; Başlat "model eksik" der |
| Kurulum eksik (`ortam.*`) | "Kurulum tamamlanmamış" |
| < 14 GB kart | "Doku" seçeneği belirir, kapalı gelir: yalnız şekil (8 GB) ya da şekil + P3-SAM (13 GB) |
| ≤ 16 GB, Parçalı | "Sınırda · 16 GB'ta pay az kalır" |
| < `xpart_ihtiyac_gb` (35,4) | + X-Part seçilebilir, uyarılı: "~35 GB ister; bu kartta Windows belleğe taşır, yavaşlar"; Başlat onay ister |
| `blender: false` | 07 Toon kilitli, sağda not |
| `modeller["2mv"]: false` | "+ arka" kapalı (ön + arka için 2mv gerekir) |
| Hazır mesh | Hafif hiçbir GPU modeli istemez (toon + piksel). Parçalı yalnız P3-SAM ister |

Bir rota çalışamıyorsa arayüz çalışabilen diğer rotaya geçer. Sunucuya ulaşılamazsa başlık "Sunucu yok" der ve sayfa
3 saniyede bir yeniden dener.

## API kullanımı

Sözleşme `design/PLAN.md` içinde; arayüz gerçek sunucunun davranışına göre yazıldı:

- `POST /api/is` (multipart: `on` | `mesh`, `arka`, `rota`, `xpart`, `doku`, `toon_aci`, `piksel_boy`, `palet`,
  `tohum`) → `{id}`. Ardından `GET /api/is/{id}` ile sıra (`sira`) ve, mesh ise, `cikti.shape` hemen okunur.
- `GET /api/is/{id}/olaylar` (SSE): `adim` olayları şeridi ve görüntüleyiciyi sürer, `log` günlüğe gider,
  `bitti` / `hata` akışı kapatır. Yeni bağlantıda sunucu anlık durumu baştan gönderir; arayüz bunu olduğu gibi
  uygular. Akış koparsa iş durumu `GET /api/is/{id}` ile yeniden okunur.
- Çıktılar adım bitince sırayla görünür: `sekil` → `shape.glb` (alttan yükselen çizgiyle), `doku` → `textured.glb`
  (yukarıdan inen doku), `ayrik` → `parts.json` + `parts/part_XX.glb` (parçalar renklenip yerine oturur). Parçalar
  kendi dokularını taşıyorsa (ayrik böyle yazar) doğrudan; taşımıyorsa doku, `textured.glb` ile yüz yüze eşlenip
  aktarılır; eşleşme tutmazsa "Dokulu" görünümde bütün mesh gösterilir.
- `POST /api/is/{id}/toon` `{aci}` ve `/piksel` `{boy, palet}`: sunucu iş bitince yanıt verir (iş durumuyla).
  Bekleme sürerken `GET /api/is/{id}` ile 07/08 ilerlemesi şeritte gösterilir. Aynı adlı dosyanın üstüne yazıldığı
  için resimler önbellek kırıcıyla (`?v=`) yeniden yüklenir.
- `GET /api/vram` yalnız iş çalışırken, sekme görünürken 500 ms'de bir.
- `GET /api/isler` (Geçmiş: `kapak`, `girdi.ad`, tarih, rota), `DELETE /api/is/{id}` (onaydan sonra).
- Hatalar `{hata: <kimlik>, ayrinti}` gelir; Türkçe metin arayüzde (`HATA`, `hataMetni` · `main.js`). Başarısız
  adımın `hata_ozeti` içinde "out of memory" varsa "VRAM yetmedi" önerisi gösterilir.
- Sayfa adresi `#is=<id>` taşır: yenileyince iş geri açılır.

Ayarlar (`rota`, açı, boy, palet) tarayıcıda `localStorage` içinde (`atolye.ayar`) saklanır.

## Geliştirme (dev/, uygulamaya dahil değil)

`dev/` klasörü yalnız arayüzü denemek içindir; sunucu bunu sunmaz. Kurulum ve komutlar: [dev/README.md](../dev/README.md).

- `dev/canli_gpu.mjs`: gerçek sunucuya karşı bir görselle bir rotayı baştan sona çalıştırır, her durumun ekran
  görüntüsünü `_scratch/shots/` içine alır.
- `dev/canli.mjs`: GPU modeli gerekmeyen yolu dener (hazır mesh → Blender toon → piksel → yeniden render → indir →
  yenile → geçmiş). `--sil` kendi açtığı işleri siler.

## Erişilebilirlik

Klavye: görsel alanı, "+ arka", rota kartları, geçmiş kartları Enter / Boşluk ile çalışır; Ctrl+Enter Başlat'a
basar; Esc geçmiş penceresini kapatır. Odak halkası görünür. Anlam yalnız renkle verilmez: kilitli, atlandı, hata
durumları simge ve yazıyla da belirtilir. Düzen 1280×800'de kırılmaz.
