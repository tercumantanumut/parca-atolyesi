# Lisanslar

Bu sayfa üç şeyi ayırır: **bizim kodumuz**, **indirilen modeller** ve **çağırdığımız araçlar.** Hepsinin
kuralları farklı. Çıktıları bir oyunda kullanacaksan özellikle model lisansları kısmını oku.

> Buradaki özetler anlamayı kolaylaştırmak için. Hukuki tavsiye değiller. Bağlayıcı olan, bağlantısı verilen
> özgün lisans metinleridir.

## Bizim kodumuz: MIT


Bu depodaki kod (`atolye/`, `blender/`, `kurulum/`, `web/app/`, belgeler) **MIT lisanslı.** Kısaca: kullan,
değiştir, sat, kendi projene kat. Tek şart, lisans metnini ve telif satırını kopyalarda tutmak. Garanti yok.

`web/vendor/three/` içindeki three.js de MIT lisanslı (`web/vendor/three/LICENSE`).

## Modeller: bu depoda yok, kurulum indirir

Bu depo **hiçbir model ağırlığını içermez ve yeniden dağıtmaz.** `kurulum\kur.ps1` modelleri doğrudan
yayıncılarının sayfalarından (Hugging Face ve GitHub) indirir. Modeller indirildiği anda kendi lisansları
geçerli olur: bu lisansları sen, kullanan kişi olarak kabul etmiş olursun.

| Model | Ne yapar | Lisans |
|---|---|---|
| [Hunyuan3D-2.1](https://huggingface.co/tencent/Hunyuan3D-2.1) | 02 Şekil, 03 Doku | [Tencent Hunyuan 3D 2.1 Community License](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE) |
| [Hunyuan3D-Part](https://huggingface.co/tencent/Hunyuan3D-Part) (P3-SAM, X-Part) | 04 Parçalar, 06 X-Part | [Tencent Hunyuan 3D-Part Community License](https://huggingface.co/tencent/Hunyuan3D-Part/blob/main/LICENSE.txt) |
| [Hunyuan3D-2mv](https://huggingface.co/tencent/Hunyuan3D-2mv) (isteğe bağlı) | Ön + arka görselden şekil | [Tencent Hunyuan 3D 2.0 Community License](https://huggingface.co/tencent/Hunyuan3D-2mv/blob/main/LICENSE) |
| [Sonata](https://huggingface.co/facebook/sonata) (Meta) | P3-SAM'in kullandığı 3B nokta bulutu omurgası | Ağırlıklar **CC BY-NC 4.0** (ticari olmayan), kod Apache 2.0 ([kaynak](https://github.com/facebookresearch/sonata#license)) |
| [DINOv2 giant](https://huggingface.co/facebook/dinov2-giant) (Meta) | Doku adımında görseli anlamak | Apache 2.0 |
| [Real-ESRGAN x4plus](https://github.com/xinntao/Real-ESRGAN) | Doku adımında görünümleri büyütmek | BSD 3-Clause |
| [U²-Net](https://github.com/xuebinqin/U-2-Net) ([rembg](https://github.com/danielgatis/rembg) üzerinden) | Arka plan temizleme (gerektiğinde) | Apache 2.0 (rembg: MIT) |

### Tencent Hunyuan 3D Community License: Türkçe özet

Hunyuan3D-2.1, Hunyuan3D-Part ve Hunyuan3D-2mv aynı kalıpta üç ayrı lisansla gelir. Maddeler aynı, yalnız model
adları değişir. Özetle:

- **Bölge sınırı.** Lisans **Avrupa Birliği, Birleşik Krallık ve Güney Kore'de geçerli değil.** Lisansın
  "Bölge" (Territory) dediği yer, dünyanın geri kalanı. Türkiye bölgenin içinde.
- **Çıktılar da bölgeyle sınırlı.** Modelleri ve **çıktılarını** bölge dışında kullanmak, çoğaltmak, dağıtmak ya
  da göstermek lisansın kapsamında değil (madde 5c). Örneğin AB'de de satılan bir oyunda bu modellerle
  üretilmiş varlıklar varsa durum belirsizleşir. Oyununu nerede yayınlayacağını düşünerek karar ver.
- **Çıktılar senin.** Tencent ürettiğin çıktılar üzerinde hak iddia etmez. Çıktılardan ve nasıl kullandığından
  sen sorumlusun (madde 6d).
- **Başka yapay zekâyı eğitmek yok.** Modelleri ya da çıktılarını Hunyuan dışında bir yapay zekâ modelini
  geliştirmek veya eğitmek için kullanamazsın (madde 5b).
- **Büyük şirket eşiği.** Model yayınlandığında ürünlerinin aylık aktif kullanıcısı 1 milyonu geçiyorsa, önce
  Tencent'ten ayrı lisans istemen gerekir (madde 4). Bağımsız geliştiricileri ilgilendirmez.
- **Kabul Edilebilir Kullanım Politikası** (lisansın Ek A'sı). Kısaca: yasa dışı işler, başkalarına zarar,
  çocukları istismar, taciz, kötü amaçlı yazılım, askerî kullanım, seçimleri etkilemeye yönelik sahte içerik ve
  başkasının kimliğine bürünme yasak. Oyun geliştiricileri için önemli bir madde daha var: makine üretimi
  içeriği herkese açık bir yerde yayınlıyorsan, bunun **makine üretimi olduğunu açıkça belirtmelisin** (madde
  12). Steam gibi mağazaların yapay zekâ beyanı da zaten bunu ister.
- **Modelin kendisini dağıtacaksan** (bu depo dağıtmıyor): lisansın bir kopyasını ve bir "Notice" dosyası
  vermen, değiştirdiğin dosyaları işaretlemen gerekir. "Powered by Tencent Hunyuan" ibaresi önerilir, zorunlu
  değil.
- Garanti yok. Uyuşmazlıklarda Hong Kong hukuku geçerli.

Tam metinler: [2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE) ·
[Part](https://huggingface.co/tencent/Hunyuan3D-Part/blob/main/LICENSE.txt) ·
[2.0 / 2mv](https://huggingface.co/tencent/Hunyuan3D-2mv/blob/main/LICENSE). Kurulumdan sonra aynı metinler
`modeller/` altında, her modelin klasöründe de durur.

### Sonata ve Parçalı rota: ticari kullanım

P3-SAM (04 Parçalar adımı) Meta'nın **Sonata** modelini omurga olarak yükler. Meta, Sonata ağırlıklarını
**CC BY-NC 4.0** ile yayınlıyor: **ticari olmayan** kullanım. Yani:

- **Hafif rota** (şekil + doku + toon + piksel) Sonata'yı hiç kullanmaz.
- **Parçalı rota** kullanır. Parçalarını ticari bir oyunda kullanmayı düşünüyorsan önce bu lisansı oku ve
  durumunu kendin değerlendir. Bu konuda kesin bir yorum yapmıyoruz.

## Blender: GPL, yalnız çağırıyoruz

[Blender](https://www.blender.org/about/license/) GPL lisanslı. Blender'ı bu depoya koymuyoruz, kurulumu da
indirmiyor. Kendi Blender'ını kurarsın, Parça Atölyesi onu ayrı bir işlem olarak, pencere açmadan çağırır
(`blender -b --factory-startup -P blender/toon_still.py`). Blender'la ürettiğin görsellerin sahibi sensin. GPL,
Blender'ın çıktılarını kapsamaz.

## Python paketleri

Kurulum `.atolye/venv` içine PyTorch, diffusers, transformers, trimesh, Open3D gibi açık kaynak paketleri kurar.
Her biri kendi lisansıyla gelir. Hiçbiri bu depoya kopyalanmaz.

## Örnek görseller

`ornekler/` içindeki üç görsel bu depo için yapay zekâ (Gemini) ile üretildi. Özgürce kullanabilirsin.
