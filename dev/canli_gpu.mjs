// Dev-only: drives the UI against the REAL server with a real image through the GPU steps, one route per run,
// and screenshots each state into _scratch/shots/gpu_<ad>_*. Needs the weights for the chosen route.
// Run: BASE=http://127.0.0.1:8731 ROTA=hafif|parcali IMG=<on.png> [ARKA=<arka.png>] [XPART=1] [AD=maceraci] node dev/canli_gpu.mjs
import { chromium } from 'playwright';  // cd dev && npm install (dev/package.json)
import { mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SHOTS = join(HERE, '..', '_scratch', 'shots');
const BASE = process.env.BASE || 'http://127.0.0.1:8731';
const ROTA = process.env.ROTA || 'hafif';
const IMG = process.env.IMG || join(HERE, '..', 'ornekler', 'maceraci.png');
const ARKA = process.env.ARKA || '';
const AD = `${process.env.AD || 'is'}_${ROTA}`;
const [W, H] = (process.env.SIZE || '1440x900').split('x').map(Number);
mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch({ args: ['--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist'] });
const errors = [];
const t0 = Date.now(), log = (...a) => console.log(`[${((Date.now() - t0) / 1000).toFixed(0)}s]`, ...a);
const ctx = await browser.newContext({ viewport: { width: W, height: H } });
const page = await ctx.newPage();
page.on('pageerror', e => errors.push(e.message));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('dialog', d => d.accept());
const snap = n => page.screenshot({ path: join(SHOTS, `gpu_${AD}_${n}.png`) }).then(() => log('shot', n));
const job = () => page.evaluate(() => window.__atolye.S.job && JSON.parse(JSON.stringify(window.__atolye.S.job)));

await page.goto(BASE + '/');
await page.waitForFunction(() => window.__ready === true, null, { timeout: 30000 });
await page.setInputFiles('#fileOn', IMG);
if (ARKA) await page.setInputFiles('#fileArka', ARKA);
await page.waitForTimeout(500);
await page.click(`[data-r="${ROTA}"]`);
await page.waitForTimeout(300);
if (process.env.XPART) { await page.click('[data-xp]'); await page.waitForTimeout(300); }
await snap('hazir');
await page.click('#go');
await page.waitForFunction(() => window.__atolye.S.job?.id, null, { timeout: 30000 });
const id = (await job()).id;
log('is', id);
const goruldu = new Set();
for (;;) {
  const j = await job();
  for (const [a, s] of Object.entries(j?.adimlar || {})) {
    if (s.durum === 'calisiyor' && !goruldu.has(a)) {
      goruldu.add(a);
      await page.waitForTimeout(a === 'toon' || a === 'piksel' ? 300 : 4000);
      await snap(`calisiyor_${a}`);
    }
  }
  if (j && (j.durum === 'bitti' || j.durum === 'hata')) break;
  await page.waitForTimeout(1000);
  if (Date.now() - t0 > 30 * 60e3) { log('zaman aşımı'); break; }
}
await page.waitForTimeout(3000);
const son = await job();
log('durum', son.durum, Object.fromEntries(Object.entries(son.adimlar).map(([a, s]) => [a, `${s.durum} ${s.sure_sn ?? ''}s ${s.tepe_vram_gb ?? ''}GB`])));
await snap('bitti');
if (son.durum === 'bitti') {
  for (const m of ['clay', 'parts']) {
    const b = await page.$(`#modes [data-m="${m}"]`);
    if (b && !(await b.isDisabled())) { await b.click(); await page.waitForTimeout(1500); await snap(`3d_${m}`); }
  }
  const ex = await page.$('#explode');
  if (ex && !(await ex.isDisabled())) {
    await ex.fill('1'); await ex.dispatchEvent('input'); await page.waitForTimeout(2500); await snap('3d_patlat');
  }
  await page.click('[data-v="tp"]'); await page.waitForTimeout(2000); await snap('toon_piksel');
  await page.click('[data-t="files"]'); await page.waitForTimeout(800); await snap('indir');
}
await browser.close();
console.log(errors.length ? 'ERRORS:\n' + [...new Set(errors)].join('\n') : 'no page errors');
