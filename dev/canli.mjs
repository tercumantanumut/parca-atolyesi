// Dev-only: drives the UI against the REAL server (atolye sunucu --web <this web/>) and screenshots each state
// into _scratch/shots/canli_*. Uses what runs without model weights today: a ready mesh -> Blender toon -> pixel.
// Run: BASE=http://127.0.0.1:8741 MESH=<hazir.glb> node dev/canli.mjs [--sil]
//   --sil deletes the jobs this run created (through the API) when it is done.
import { chromium } from 'playwright';  // cd dev && npm install (dev/package.json)
import { mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SHOTS = join(HERE, '..', '_scratch', 'shots');
const BASE = process.env.BASE || 'http://127.0.0.1:8741';
const MESH = process.env.MESH || '';
const IMG = process.env.IMG || join(HERE, '..', 'ornekler', 'maceraci.png');
const SIZES = (process.env.SIZES || '1440x900,1920x1080').split(',').map(s => s.split('x').map(Number));
mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch({ args: ['--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist'] });
const errors = [], made = [];
const t0 = Date.now(), log = (...a) => console.log(`[${((Date.now() - t0) / 1000).toFixed(0)}s]`, ...a);

for (const [w, h] of SIZES) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();
  page.on('pageerror', e => errors.push(`${w}: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`${w}: ${m.text()}`); });
  page.on('dialog', d => d.accept());
  const snap = n => page.screenshot({ path: join(SHOTS, `canli_${n}_${w}.png`) }).then(() => log('shot', n, w));
  await page.goto(BASE + '/');
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 30000 });
  await page.waitForTimeout(800);
  await snap('bos');
  await page.setInputFiles('#fileOn', IMG); await page.waitForTimeout(500);
  await snap('gorsel-modelyok');
  await page.setInputFiles('#fileOn', MESH); await page.waitForTimeout(500);
  await page.click('[data-r="hafif"]'); await page.waitForTimeout(300);  // the route is remembered across visits
  await snap('mesh-hazir');
  await page.click('#go');
  await page.waitForFunction(() => window.__atolye.S.job?.adimlar?.toon?.durum === 'calisiyor', null, { timeout: 60000 });
  made.push(await page.evaluate(() => window.__atolye.S.job.id));
  await page.waitForTimeout(2500); await snap('mesh-toon-calisiyor');
  await page.waitForFunction(() => window.__atolye.S.job?.durum === 'bitti' || window.__atolye.S.job?.durum === 'hata', null, { timeout: 180000 });
  await page.waitForTimeout(2500);
  log('durum', await page.evaluate(() => window.__atolye.S.job.durum));
  await snap('mesh-bitti');
  if (await page.evaluate(() => window.__atolye.S.job.durum) === 'bitti') {
    await page.click('[data-v="tp"]'); await page.waitForTimeout(1500); await snap('mesh-toon-piksel');
    await page.click('[data-a="yan"]'); await page.waitForTimeout(1500); await snap('mesh-yeniden-toon');
    await page.waitForFunction(() => !window.__atolye.S.yeniden, null, { timeout: 120000 }); await page.waitForTimeout(1500);
    await snap('mesh-yan');
    await page.selectOption('#palSel', 'pico-8');
    await page.waitForFunction(() => !window.__atolye.S.yeniden, null, { timeout: 60000 });
    await page.click('[data-px="80"]');
    await page.waitForFunction(() => !window.__atolye.S.yeniden, null, { timeout: 60000 }); await page.waitForTimeout(1500);
    await snap('mesh-yan-80-pico8');
    await page.click('[data-t="files"]'); await page.waitForTimeout(800); await snap('mesh-indir');
    await page.click('[data-v="3d"]'); await page.waitForTimeout(800);
  }
  // reload restores the job from #is=<id>
  await page.reload(); await page.waitForFunction(() => window.__ready === true && window.__atolye.viewer.parts.length > 0, null, { timeout: 60000 });
  await page.waitForTimeout(2000); await snap('mesh-yenile');
  await page.click('#histBtn'); await page.waitForTimeout(600); await snap('gecmis');
  await ctx.close();
}
if (process.argv.includes('--sil')) for (const id of made) { await fetch(`${BASE}/api/is/${id}`, { method: 'DELETE' }); log('silindi', id); }
await browser.close();
console.log(errors.length ? 'ERRORS:\n' + [...new Set(errors)].join('\n') : 'no page errors');
