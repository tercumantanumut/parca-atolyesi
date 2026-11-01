# dev/ (geliştiriciler için)

Paneli gerçek sunucuya karşı tarayıcıda süren kontroller. Kurulum: `cd dev && npm install && npx playwright install chromium`.

- `canli_gpu.mjs`: bir görselle bir rotayı baştan sona çalıştırır ve her durumun ekran görüntüsünü alır.
  `BASE=http://127.0.0.1:8731 ROTA=hafif|parcali IMG=../ornekler/maceraci.png node canli_gpu.mjs`
- `canli.mjs`: GPU modeli gerekmeyen yolu dener (hazır mesh -> toon -> piksel). `MESH=<hazir.glb> node canli.mjs`

Ekran görüntüleri `_scratch/shots/` klasörüne düşer (git'e girmez).
