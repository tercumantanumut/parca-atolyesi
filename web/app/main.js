// Parça Atölyesi · Tezgâh: the dashboard wired to the local server (API contract in design/PLAN.md).
import { Viewer } from './viewer.js';
import { api, olaylar, ciktilar, ciktiUrl, normJob } from './api.js';

const $ = s => document.querySelector(s);
const icon = (id, cls = 'i') => `<svg class="${cls}"><use href="#i-${id}"/></svg>`;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const gb = v => { const r = Math.round(v * 10) / 10; return (Number.isInteger(r) ? String(r) : r.toFixed(1)).replace('.', ','); };
const fmtInt = n => Number(n).toLocaleString('tr-TR');
const fmtTime = s => { s = Math.max(0, Math.floor(s)); return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`; };
const fmtSure = s => s == null ? '' : s < 60 ? `${s < 10 ? (Math.round(s * 10) / 10).toString().replace('.', ',') : Math.round(s)} sn` : `${Math.floor(s / 60)} dk ${Math.round(s % 60)} sn`;
const fmtSize = b => b == null ? '' : b < 1024 * 1024 ? `${Math.max(1, Math.round(b / 1024))} KB` : `${(b / 1024 / 1024).toFixed(1).replace('.', ',')} MB`;
const fmtDate = d => {
  if (!d) return '';
  const t = typeof d === 'number' ? new Date(d < 1e12 ? d * 1000 : d) : new Date(d);
  return isNaN(t) ? String(d) : t.toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' }) + ' · ' + t.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
};

// ---------------------------------------------------------------------------------------------
// Steps. Reference time and VRAM are RTX 5090 measurements; once a step has run, its real numbers replace them.

const STAGES = [
  { id: 'gorsel',   n: '01', name: 'Görsel',   ic: 'img',   ref: 'Ön · arka' },
  { id: 'sekil',    n: '02', name: 'Şekil',    ic: 'blob',  ref: '~60 sn · 8 GB',    sn: 60,  vram: 8 },
  { id: 'doku',     n: '03', name: 'Doku',     ic: 'paint', ref: '~80 sn · 14 GB',   sn: 80,  vram: 14 },
  { id: 'parcalar', n: '04', name: 'Parçalar', ic: 'parts', ref: '~40 sn · 12 GB',   sn: 40,  vram: 12 },
  { id: 'ayrik',    n: '05', name: 'Ayrık',    ic: 'split', ref: '~8 sn',            sn: 8 },
  { id: 'xpart',    n: '06', name: 'X-Part',   ic: 'seal',  ref: '5–13 dk · ~35 GB', sn: 600, vram: 35, optional: true },
  { id: 'toon',     n: '07', name: 'Toon',     ic: 'toon',  ref: '~3 sn · Blender',  sn: 3 },
  { id: 'piksel',   n: '08', name: 'Piksel',   ic: 'px',    ref: '~1 sn · CPU',      sn: 1 },
];
const ROUTE_STEPS = {
  hafif: ['gorsel', 'sekil', 'doku', 'toon', 'piksel'],
  parcali: ['gorsel', 'sekil', 'doku', 'parcalar', 'ayrik', 'toon', 'piksel'],
};
const XPART_SN = 600;  // ~5-7 min where it fits the card, ~12 min when Windows spills (32 GB)
const ROUTE_PEAK = 14, XPART_NEED = 35;  // GB; X-Part's measured working set (GET /api/sistem: xpart_ihtiyac_gb)
const ANGLES = [{ id: 'on', name: 'Ön' }, { id: 'ucceyrek', name: '3/4' }, { id: 'yan', name: 'Yan' }];
const PX_SIZES = [160, 128, 80];
const DURUM = { bekliyor: 'wait', calisiyor: 'run', bitti: 'done', atlandi: 'skip', hata: 'err' };
const LOG_AD = { sekil: '02', doku: '03', parcalar: '04', ayrik: '05', xpart: '06', toon: '07', piksel: '08' };

// ---------------------------------------------------------------------------------------------
// State

const saved = JSON.parse(localStorage.getItem('atolye.ayar') || '{}');
const S = {
  sistem: null, sunucu: 'bekle',
  girdi: { on: null, arka: null, onUrl: null, arkaUrl: null, hata: null },
  rota: saved.rota || 'parcali', xpart: false,
  ayar: { aci: saved.aci || 'ucceyrek', boy: saved.boy || 160, palet: saved.palet || 'ozgun', tohum: randSeed() },
  job: null, log: [], t0: null, mesaj: null,
  vram: null, tepe: 0,
  mode: 'textured', explode: 0, turntable: true, hidden: new Set(), hi: -1,
  thumbs: {}, isler: [], tab: 'parts', vtab: '3d', yukleniyor: false,
  yeniden: null,         // {adim: 'toon'|'piksel'} while a re-render runs
  stamp: Date.now(),     // cache-buster for toon/piksel files (they are overwritten in place)
};
function randSeed() { return Math.floor(Math.random() * 1e6); }
function persist() { localStorage.setItem('atolye.ayar', JSON.stringify({ rota: S.rota, aci: S.ayar.aci, boy: S.ayar.boy, palet: S.ayar.palet })); }

const phase = () => {
  if (S.job) {
    const d = S.job.durum;
    if (d === 'bitti') return 'bitti';
    if (d === 'hata') return 'hata';
    return 'calisiyor';
  }
  return S.girdi.on || S.girdi.mesh ? 'hazir' : 'bos';
};
const isDone = () => ['bitti', 'hata'].includes(phase());
const step = id => S.job?.adimlar[id] || null;
const outs = () => S.job ? ciktilar(S.job) : {};
const bust = url => url ? url + (url.includes('?') ? '&' : '?') + 'v=' + S.stamp : url;

// What this machine can run, from GET /api/sistem. Honest: no GPU, missing models and VRAM all gate the routes.
// A ready mesh (GLB/OBJ/PLY/STL) skips 01-02 and the texture, so Hafif then needs no model and no GPU.
function access() {
  const s = S.sistem;
  if (!s) { const wait = { ok: false, why: null }; return { hafif: wait, parcali: wait, xpart: wait, arka: false, total: 0, blender: false, peak: {}, small: false }; }
  const total = s.gpu?.toplam_gb ?? 0, m = s.modeller || {}, gpu = !!s.gpu;
  const ortamOk = !s.ortam || Object.values(s.ortam).every(Boolean);
  const mesh = !!S.girdi.mesh, doku = dokuOn(), xneed = xpartNeed();
  const peak = { hafif: doku ? 14 : mesh ? 0 : 8, parcali: doku ? 14 : 13 };
  const gate = (need, pk) => {
    if (!need.length) return { ok: true };
    if (!gpu) return { ok: false, why: 'NVIDIA ekran kartı bulunamadı' };
    const eksik = need.find(k => !m[k]);
    if (eksik) return { ok: false, why: `${MODEL_AD[eksik]} modeli indirilmemiş` };
    if (!ortamOk) return { ok: false, why: 'Kurulum tamamlanmamış' };
    if (total < 7.5) return { ok: false, why: `En az 8 GB VRAM gerekir · kartta ${gb(total)} GB` };  // "8 GB" cards report ~7.9 GiB
    if (pk > total) return { ok: true, warn: `${pk} GB ister · kartta ${gb(total)} GB` };
    if (pk >= 13 && total <= 16) return { ok: true, warn: `Sınırda · ${gb(total)} GB'ta pay az kalır` };
    return { ok: true };
  };
  const base = [...(mesh ? [] : ['sekil']), ...(doku ? ['doku'] : [])];
  const hafif = gate(base, peak.hafif);
  const parcali = gate([...base, 'parcalar'], peak.parcali);
  const xpart = !gpu ? { ok: false, why: 'NVIDIA ekran kartı bulunamadı' }
    : !m.xpart ? { ok: false, why: 'X-Part modeli indirilmemiş' }
    : total < xneed ? { ok: true, warn: XPART_TASAR(xneed) } : { ok: true };  // runs anyway: Windows spills, slowly
  return { hafif, parcali, xpart, arka: !!m['2mv'], total, blender: !!s.blender, peak,
    small: gpu && total < ROUTE_PEAK };
}
const MODEL_AD = { sekil: 'Şekil', doku: 'Doku', parcalar: 'P3-SAM', xpart: 'X-Part', '2mv': '2mv' };
const xpartNeed = () => Math.round(S.sistem?.xpart_ihtiyac_gb ?? XPART_NEED);
const XPART_TASAR = need => `~${need} GB ister; bu kartta Windows belleğe taşır, yavaşlar`;
// texture step: on by default, off by default on cards under 14 GB (shape only), never for a ready mesh
function dokuOn() {
  if (S.girdi.mesh) return false;
  if (S.doku != null) return S.doku;
  const t = S.sistem?.gpu?.toplam_gb;
  return !(t && t < ROUTE_PEAK);
}
function plannedSteps(rota) {
  return ROUTE_STEPS[rota].filter(id => !(id === 'sekil' && S.girdi.mesh) && !(id === 'doku' && !dokuOn()));
}

// Server ids -> Turkish. Errors are {hata: id, ayrinti}; a failed job has mesaj "<adim>_hata" and the step's hata_ozeti.
const HATA = {
  on_gorsel_gerekli: 'Önce bir ön görsel bırak', gecersiz_gorsel: 'Görsel okunamadı',
  gecersiz_gorsel_boyutu: 'Görsel çok küçük ya da çok büyük (en az 64 px)', gecersiz_mesh: 'Mesh okunamadı (GLB, OBJ, PLY, STL)',
  model_yok: 'Gereken model indirilmemiş', ortam_yok: 'Kurulum tamamlanmamış', gecersiz_palet: 'Bilinmeyen palet',
  gecersiz_piksel_boy: 'Boy 16 ile 512 arasında olmalı', gecersiz_toon_aci: 'Bilinmeyen açı', gecersiz_rota: 'Bilinmeyen rota',
  gecersiz_tohum: 'Tohum bir sayı olmalı', is_bitmedi: 'İş henüz bitmedi', is_mesgul: 'Bu iş şu an meşgul, birazdan dene',
  mesh_yok: 'Bu işte mesh yok', dosya_cok_buyuk: 'Dosya çok büyük', is_yok: 'Bu iş artık yok', bulunamadi: 'Bulunamadı',
  sunucu_hatasi: 'Sunucu hatası', sunucu_durdu: 'Sunucu iş sürerken kapandı', silindi: 'İş silindi', iptal: 'İş iptal edildi',
  multipart_gerekli: 'Geçersiz istek', gecersiz_form: 'Geçersiz istek', gecersiz_json: 'Geçersiz istek',
};
const NEDEN = { rota: 'Bu rotada yok', secilmedi: 'Seçilmedi', model_yok: 'Model indirilmemiş', vram_yetersiz: 'VRAM yetmez',
  onceki_hata: 'Önceki adım başarısız', mesh_verildi: 'Hazır mesh verildi', dokulu_mesh: 'Mesh zaten dokulu',
  blender_yok: 'Blender bulunamadı' };
function hataMetni(e) {
  const kod = typeof e === 'string' ? e : e?.kod || e?.message || '';
  const ay = typeof e === 'object' ? e?.ayrinti : null;
  if (kod === 'model_yok' && ay?.eksik?.length) return `Model indirilmemiş: ${ay.eksik.map(k => MODEL_AD[k] || k).join(', ')}`;
  if (HATA[kod]) return HATA[kod];
  const m = /^(\w+?)_(hata|baslatilamadi|vram_yetmedi)$/.exec(kod);
  if (m) {
    const st = STAGES.find(x => x.id === m[1]), ad = st ? st.name : m[1];
    return m[2] === 'vram_yetmedi' ? `${ad}: ekran kartında yeterli boş VRAM yok` : `${ad} ${m[2] === 'hata' ? 'adımı başarısız' : 'başlatılamadı'}`;
  }
  if (kod.startsWith('ic_hata')) return 'İç hata';
  if (/^\d{3}$/.test(kod)) return `Sunucu yanıtı ${kod}`;
  return kod || 'Bilinmeyen hata';
}
function hataOzeti(job) {
  const a = Object.values(job?.adimlar || {}).find(x => x.durum === 'hata' && x.hata_ozeti);
  if (!a) return '';
  if (/out of memory|CUDA_ERROR_OUT_OF_MEMORY/i.test(a.hata_ozeti)) return 'VRAM yetmedi. Hafif rotayı ya da daha küçük bir görseli dene.';
  return a.hata_ozeti.trim().split('\n').pop().slice(0, 160);
}

// ---------------------------------------------------------------------------------------------
// Viewer

const viewer = new Viewer($('#view'));
viewer.on('pick', i => select(i));
viewer.on('load', () => { renderViewer(); if (isDone()) renderRight(); });

// ---------------------------------------------------------------------------------------------
// Strip

function stageState(st) {
  const p = phase(), acc = access();
  const route = S.job ? S.job.rota : S.rota;
  const xOn = S.job ? S.job.xpart : S.xpart;
  if (st.id === 'gorsel') return hasInput() || S.job ? 'done' : 'wait';
  const a = step(st.id);
  if (st.id === 'xpart' && !(route === 'parcali' && xOn) && !a?.durum) return acc.xpart.ok || S.job ? 'skip' : 'lock';
  if (st.id === 'toon' && S.sistem && !acc.blender && !S.job) return 'lock';
  if (a?.durum) return DURUM[a.durum] || 'wait';
  if (st.id !== 'xpart' && !(S.job ? ROUTE_STEPS[route] : plannedSteps(route)).includes(st.id)) return 'skip';
  if (p === 'hata') return 'skip';
  return 'wait';
}

function renderStrip() {
  $('#strip').innerHTML = STAGES.map(st => {
    const state = stageState(st), a = step(st.id), prog = a?.ilerleme ?? 0;
    const th = S.thumbs[st.id];
    const showImg = (state === 'done' || (state === 'run' && S.yeniden)) && th;
    let badge = '';
    if (state === 'done') badge = `${icon('check')}${a?.sure_sn != null ? fmtSure(a.sure_sn) : ''}${a?.bellek === 'bellekte' ? ' · bellekte' : ''}`;
    else if (state === 'run') badge = `%<span data-pct="${st.id}">${Math.floor(prog * 100)}</span>`;
    else if (state === 'lock') badge = st.id === 'toon' ? `${icon('lock')}Blender yok` : `${icon('lock')}model yok`;
    else if (state === 'skip') badge = st.id === 'xpart' ? 'kapalı' : st.id === 'sekil' && (a?.neden === 'mesh_verildi' || (!S.job && S.girdi.mesh)) ? 'mesh' : 'atlandı';
    else if (state === 'err') badge = `${icon('warn')}hata`;
    else if (state === 'wait' && S.job && st.id !== 'gorsel' && phase() === 'calisiyor') badge = 'sırada';
    const real = a && a.durum === 'bitti' && (a.sure_sn != null || a.tepe_vram_gb != null);
    const arka = S.job ? S.job.arka : !!S.girdi.arka, mesh = S.job ? S.job.mesh : !!S.girdi.mesh;
    const metric = st.id === 'gorsel' ? (S.job || hasInput() ? (mesh ? 'Hazır mesh' : arka ? 'Ön · arka' : 'Ön') : st.ref)
      : real && a.tepe_vram_gb >= 0.5 ? `tepe ${gb(a.tepe_vram_gb)} GB` : real ? (st.id === 'toon' ? 'Blender' : st.vram ? `${fmtSure(a.sure_sn)}` : 'CPU') : st.ref;
    const isPx = st.id === 'piksel';
    const why = state === 'skip' && a?.neden ? NEDEN[a.neden] || '' : state === 'err' ? hataOzeti({ adimlar: { x: a } })
      : a?.bellek === 'bellekte' ? 'Model bellekteydi: yükleme atlandı' : a?.bellek === 'yuklendi' ? 'Model diskten yüklendi' : '';
    return `<div class="st" data-s="${state}" data-id="${st.id}" ${why ? `title="${esc(why)}"` : ''}>
      <div class="th">${showImg ? `<img class="${isPx ? 'px' : ''}" src="${esc(th)}" alt="">` : `<div class="ph">${icon(st.ic)}</div>`}
        ${badge ? `<span class="badge">${badge}</span>` : ''}</div>
      <div class="base"><i data-bar="${st.id}" style="width:${state === 'done' ? 100 : state === 'run' ? prog * 100 : 0}%"></i></div>
      <div class="cap"><div class="n">${st.n}${st.optional ? '<span class="opt">isteğe bağlı</span>' : ''}</div>
        <div class="nm">${st.name}</div><div class="mt ${real ? 'real' : ''}" title="${real ? 'Bu çalıştırmanın ölçümü' : 'RTX 5090 ölçümü'}">${metric}</div></div>
    </div>`;
  }).join('');
}
function tickStrip(id) {
  const a = step(id); if (!a) return;
  const bar = document.querySelector(`[data-bar="${id}"]`); if (bar) bar.style.width = (a.durum === 'bitti' ? 100 : (a.ilerleme || 0) * 100) + '%';
  const pct = document.querySelector(`[data-pct="${id}"]`); if (pct) pct.textContent = Math.floor((a.ilerleme || 0) * 100);
}

// ---------------------------------------------------------------------------------------------
// Left: input + route

function inputSrc() {
  if (S.girdi.onUrl) return S.girdi.onUrl;
  if (!S.job) return null;
  return S.job.girdi?.on || (step('sekil')?.durum === 'bitti' ? ciktiUrl(S.job.id, 'input_rgba.png') : null);
}
const hasInput = () => !!(S.girdi.on || S.girdi.mesh);

function renderLeft() {
  const d = $('#drop'), p = phase(), acc = access(), busy = p === 'calisiyor';
  const g = S.girdi, viewingJob = !!S.job;
  const onSrc = inputSrc(), meshName = g.mesh?.name || (S.job?.mesh ? (S.job.ad || 'mesh') : null);
  d.setAttribute('aria-disabled', viewingJob);
  if (!onSrc && !meshName) {
    d.className = 'drop';
    d.setAttribute('role', 'button'); d.tabIndex = 0; d.style.gridTemplateColumns = '';
    d.innerHTML = `<div>${icon('up')}<b>Görseli bırak</b><small>PNG · JPG · ön görünüm</small><small style="display:block;opacity:.75">ya da hazır mesh: GLB · OBJ</small>${g.hata ? `<small class="bad" style="display:block;margin-top:6px">${esc(g.hata)}</small>` : ''}</div>`;
  } else {
    d.className = 'drop has' + (viewingJob ? ' small' : '');
    d.removeAttribute('role'); d.tabIndex = -1;
    const rm = w => viewingJob ? '' : `<button class="x" data-rm="${w}" aria-label="${w === 'arka' ? 'Arka görseli kaldır' : 'Kaldır'}">${icon('x')}</button>`;
    const front = meshName && !onSrc
      ? `<div class="slot front mesh" ${viewingJob ? '' : 'role="button" tabindex="0" data-pick="on" title="Değiştir"'}><span>${icon('cube')}<b>${esc(meshName)}</b><small>hazır mesh</small></span>${rm('mesh')}</div>`
      : `<div class="slot front" ${viewingJob ? '' : 'role="button" tabindex="0" data-pick="on" title="Görseli değiştir"'}><img src="${esc(onSrc)}" alt="Ön görünüm">${rm('on')}</div>`;
    // a finished 02 has the background-removed back image (2mv); before that, the upload
    const arkaSrc = g.arkaUrl || (viewingJob ? step('sekil')?.cikti?.input_back_rgba || S.job.girdi?.arka : null);
    const canBack = acc.arka && !viewingJob && !g.mesh;
    const back = arkaSrc ? `<div class="slot back set"><img src="${esc(arkaSrc)}" alt="Arka görünüm">${rm('arka')}</div>`
      : viewingJob || g.mesh ? ''
      : `<div class="back" role="button" tabindex="0" data-pick="arka" aria-disabled="${!canBack}" title="${canBack ? 'Arka görünüm ekle (isteğe bağlı)' : 'Ön + arka için Hunyuan3D-2mv modeli gerekir'}">+ arka</div>`;
    d.style.gridTemplateColumns = back ? '1fr 64px' : '1fr';
    d.innerHTML = front + back;
  }

  const route = S.job ? S.job.rota : S.rota, xOn = S.job ? S.job.xpart : S.xpart;
  const total = acc.total || 0, scale = Math.max(total, 16);
  const pct = v => Math.min(100, v / scale * 100) + '%';
  const doku = S.job ? S.job.doku : dokuOn(), mesh = S.job ? S.job.mesh : !!g.mesh;
  // a saved job shows what it ran with; gating only matters for the next run
  const jobPeak = { hafif: doku ? 14 : mesh ? 0 : 8, parcali: doku ? 14 : 13 };
  const free = { ok: true };
  const r = [
    { id: 'hafif', name: 'Hafif', d: mesh ? 'Toon + piksel · GPU modeli gerekmez' : doku ? 'Şekil + doku' : 'Yalnız şekil · doku yok',
      a: viewingJob ? free : acc.hafif, pk: viewingJob ? jobPeak.hafif : acc.peak.hafif },
    { id: 'parcali', name: 'Parçalı', d: '+ P3-SAM ile parçalar', a: viewingJob ? free : acc.parcali, pk: viewingJob ? jobPeak.parcali : acc.peak.parcali },
  ];
  // A finished job does not lock the route: choosing a route or X-Part on it prepares a new run with the same input.
  const lockAll = busy || (viewingJob && !isDone());
  $('#routes').innerHTML = r.map(x => {
    const dis = lockAll || !x.a.ok;
    return `<button class="route" role="radio" aria-checked="${route === x.id}" data-r="${x.id}" ${dis ? 'disabled' : ''} ${!x.a.ok ? 'aria-disabled="true"' : ''}>
      <span class="dot"></span><b>${x.name}</b><span class="v">${x.pk ? `tepe ${x.pk} GB` : 'CPU'}</span><span class="d">${x.d}</span>
      ${total && x.pk ? `<span class="bar" title="Kartın ${gb(total)} GB'ının ne kadarı"><i style="width:${pct(x.pk)}"></i></span>` : ''}
      ${!x.a.ok && x.a.why ? `<span class="warn">${icon('lock')}${esc(x.a.why)}</span>` : x.a.warn ? `<span class="warn">${icon('warn')}${esc(x.a.warn)}</span>` : ''}
    </button>`;
  }).join('') + (acc.small && !mesh && !viewingJob ? `<label class="opt-row"><input type="checkbox" id="dokuChk" ${dokuOn() ? 'checked' : ''}>
      <span>Doku <small>· ${ROUTE_PEAK} GB ister, bu kartta sınırda</small></span></label>` : '') + (() => {
    const xa = viewingJob && xOn ? { ok: true } : acc.xpart, on = route === 'parcali' && xOn, xneed = xpartNeed();
    const dis = !xa.ok || lockAll || route !== 'parcali';
    return `<button class="route xp ${xa.ok ? '' : 'locked'}" role="checkbox" data-xp="1" aria-checked="${on}" ${dis ? 'disabled aria-disabled="true"' : ''}
        title="${xa.ok ? (route === 'parcali' ? 'Kapalı, temiz parça meshleri' : 'Parçalı rotada açılır') : esc(xa.why || '')}">
      <span class="dot">${xa.ok ? '' : icon('lock')}</span><b>+ X-Part</b><span class="v">~${xneed} GB</span><span class="d">Kapalı, temiz parça meshleri · ${xa.warn ? '12+ dk' : '5–7 dk'}</span>
      ${!xa.ok ? (xa.why ? `<span class="warn" style="color:var(--mute)">${esc(xa.why)}</span>` : '') : route !== 'parcali' ? `<span class="warn info">Parçalı rotada açılır</span>` : xa.warn && !viewingJob ? `<span class="warn">${icon('warn')}${esc(xa.warn)}</span>` : ''}</button>`;
  })();

  // seed: only before a run, and only when a model generates the shape
  const showSeed = !viewingJob && !g.mesh;
  $('#seed').style.display = showSeed ? '' : 'none';
  if (showSeed) $('#seed').innerHTML = `<label for="tohum" title="Aynı tohum, aynı görselden aynı sonucu verir">tohum</label><input id="tohum" inputmode="numeric" value="${S.ayar.tohum}" aria-label="Tohum">
    <button data-seed="1" title="Yeni tohum" aria-label="Yeni tohum">${icon('dice')}</button>`;

  const go = $('#go');
  const est = plannedSteps(S.rota).reduce((a, id) => a + (STAGES.find(x => x.id === id).sn || 0), 0) + (S.xpart && S.rota === 'parcali' ? XPART_SN : 0);
  const routeOk = acc[S.rota]?.ok;
  go.className = 'go' + (isDone() ? ' ghost' : '');
  if (busy) {
    go.disabled = true;
    go.innerHTML = queued() ? 'Sırada…' : 'Çalışıyor…';
  } else if (isDone()) {
    go.disabled = false; go.innerHTML = `${icon('rot')}Yeniden çalıştır`;
  } else {
    go.disabled = !hasInput() || !routeOk || S.sunucu !== 'ok';
    const rw = acc[S.rota]?.why || '';
    const why = S.sunucu !== 'ok' ? 'sunucu yok' : !hasInput() || routeOk ? ''
      : /indirilmemiş/.test(rw) ? 'model eksik' : /Kurulum/.test(rw) ? 'kurulum eksik' : 'bu kartta çalışmaz';
    go.innerHTML = `${icon('play')}Başlat ${why ? `<small class="why">· ${why}</small>` : `<small title="RTX 5090 ölçümü">~${fmtTime(est)}</small>`}`;
  }
}
const queued = () => S.job?.durum === 'bekliyor' && !Object.values(S.job.adimlar).some(a => a.durum === 'calisiyor' || a.durum === 'bitti');

// ---------------------------------------------------------------------------------------------
// Viewer chrome

function renderViewer() {
  const p = phase(), done = isDone(), live = p === 'calisiyor';
  const hasModel = viewer.parts.length > 0;
  const toonReady = !!toonUrl();
  $('#empty').style.display = !hasModel && (p === 'bos' || (p === 'hazir' && !inputSrc())) ? '' : 'none';
  const ghostSrc = inputSrc();
  const showGhost = !hasModel && (p === 'hazir' || live) && ghostSrc;
  $('#ghost').innerHTML = showGhost ? `<img src="${esc(ghostSrc)}" alt="">` : '';
  $('#loading').hidden = !S.yukleniyor;
  const name = S.job ? (S.job.ad || 'Adsız iş') : '';
  const nParts = viewer.hasParts ? viewer.parts.length : 0;
  const tris = viewer.parts.reduce((a, x) => a + x.tris, 0);
  $('#vmeta').innerHTML = S.job ? `<b>${esc(name)}</b> · ${S.job.rota === 'parcali' ? 'Parçalı' : 'Hafif'}${S.job.xpart ? ' + X-Part' : ''}${hasModel ? ` · ${nParts ? nParts + ' parça · ' : ''}${fmtInt(tris)} üçgen` : ''}` : '';
  const showTabs = done && toonReady;
  if (!showTabs) S.vtab = '3d';
  $('#vtab').style.display = showTabs ? '' : 'none';
  const tp = S.vtab === 'tp';
  $('#tools').style.display = hasModel && !tp && (done || !live) ? '' : 'none';
  $('#plate').classList.toggle('on', tp);
  $('#ptools').classList.toggle('on', tp);
  $('#view').style.visibility = tp ? 'hidden' : '';
  $('#ghost').style.visibility = tp ? 'hidden' : '';
  document.querySelectorAll('#vtab button').forEach(b => b.setAttribute('aria-pressed', b.dataset.v === S.vtab));
  document.querySelectorAll('#modes button').forEach(b => {
    const m = b.dataset.m;
    b.setAttribute('aria-pressed', m === viewer.mode);
    b.disabled = (m === 'textured' && !viewer.canTexture) || (m === 'parts' && !viewer.hasParts);
    b.title = b.disabled ? (m === 'textured' ? 'Bu işte doku yok' : 'Parçalı rotada açılır') : '';
  });
  const ex = $('#explode'), canEx = viewer.canExplode;
  ex.disabled = !canEx;
  ex.title = canEx ? '' : viewer.hasParts ? 'Dokulu görünümde model bütün; Kil ya da Parçalar ile patlat' : 'Parçalı rotada açılır';
  if (!canEx && S.explode) { S.explode = 0; viewer.setExplode(0); }
  ex.value = S.explode; ex.style.setProperty('--p', S.explode * 100 + '%');
  $('#exOut').textContent = Math.round(S.explode * 100);
  $('#turn').setAttribute('aria-pressed', S.turntable);
  const al = $('#alert');
  if (S.mesaj) { al.hidden = false; al.innerHTML = `${icon('warn')}<div><b>${esc(S.mesaj.baslik)}</b><span>${esc(S.mesaj.metin || '')}</span></div>`; }
  else al.hidden = true;
  renderClock();
}

function elapsed() {
  if (!S.job) return 0;
  if (phase() !== 'calisiyor' && S.job.sure_sn != null) return S.job.sure_sn;
  const sum = Object.values(S.job.adimlar).reduce((a, x) => a + (x.sure_sn || 0), 0);
  if (phase() !== 'calisiyor' || !S.t0) return sum;
  return (Date.now() - S.t0) / 1000;
}
function estimate() {
  if (!S.job) return 0;
  return ROUTE_STEPS[S.job.rota].filter(id => !['atlandi'].includes(step(id)?.durum))
    .reduce((a, id) => a + (STAGES.find(x => x.id === id).sn || 0), 0) + (step('xpart') && step('xpart').durum !== 'atlandi' ? XPART_SN : 0);
}
function renderClock() {
  const p = phase(), c = $('#clock');
  if (p === 'calisiyor') {
    const cur = STAGES.find(st => step(st.id)?.durum === 'calisiyor');
    c.innerHTML = queued() ? `--:--<small>sırada${S.job.sira ? ` · önünde ${S.job.sira} iş` : ' · başka iş çalışıyor'}</small>`
      : `${fmtTime(elapsed())}<small>/ ~${fmtTime(estimate())} · ${cur ? cur.n + ' ' + cur.name : 'başlıyor'}</small>`;
  } else if (p === 'bitti') c.innerHTML = `${fmtTime(elapsed())}<small>${icon('check')} bitti</small>`;
  else if (p === 'hata') c.innerHTML = `${fmtTime(elapsed())}<small style="color:var(--warn)">hata</small>`;
  else c.innerHTML = '';
}

// ---------------------------------------------------------------------------------------------
// Toon + pixel plate (steps 07-08, rendered by the server; this only shows them and asks for re-renders)

function toonUrl() {
  const o = outs();
  const a = S.ayar.aci;
  return o[`toon_${a}.png`] || (step('toon')?.durum === 'bitti' && !S.yeniden ? Object.entries(o).find(([k]) => /^toon_.*\.png$/.test(k))?.[1] : null) || null;
}
function pikselUrl() {
  const o = outs();
  return o[`piksel_${S.ayar.boy}.png`] || (step('piksel')?.durum === 'bitti' ? Object.entries(o).find(([k]) => /^piksel_.*\.png$/.test(k))?.[1] : null) || null;
}
// Palettes from the server (adaptive ozgun* first, then the .hex files). Without a list, only "Özgün".
const PAL_AD = { ozgun: 'Özgün', 'ozgun-32': 'Özgün 32', 'ozgun-16': 'Özgün 16', 'pico-8': 'PICO-8', 'sweetie-16': 'Sweetie 16',
  'endesga-32': 'Endesga 32', 'gameboy-4': 'Game Boy' };
function palettes() {
  const raw = S.paletler || S.sistem?.paletler;
  const list = (Array.isArray(raw) ? raw : []).map(p => typeof p === 'string' ? { id: p } : p).map(p => ({
    id: String(p.id), ad: p.ad || PAL_AD[p.id] || p.id, n: p.renk_sayisi ?? p.renk ?? null,
    uyarlamali: p.uyarlamali ?? String(p.id).startsWith('ozgun'), renkler: p.renkler || [] }));
  if (!list.some(p => p.id === 'ozgun')) list.unshift({ id: 'ozgun', ad: 'Özgün', n: 64, uyarlamali: true, renkler: [] });
  return list;
}
function palHtml(busy) {
  const list = palettes(), cur = list.find(p => p.id === S.ayar.palet) || list[0];
  const opt = p => `<option value="${esc(p.id)}" ${p.id === cur.id ? 'selected' : ''}>${esc(p.ad)}${p.n && !/\d$/.test(p.ad) ? ` · ${p.n}` : ''}</option>`;
  const ad = list.filter(p => p.uyarlamali), hz = list.filter(p => !p.uyarlamali);
  const sw = cur.renkler.length ? `<span class="sw-strip" title="${cur.renkler.length} renk">${cur.renkler.slice(0, 32).map(c => `<i style="background:${esc(c)}"></i>`).join('')}</span>`
    : `<span class="sw-strip auto" title="Renkler görselden seçilir"></span>`;
  return `<select id="palSel" aria-label="Palet" ${busy ? 'disabled' : ''}>
    ${hz.length ? `<optgroup label="Görselden">${ad.map(opt).join('')}</optgroup><optgroup label="Hazır">${hz.map(opt).join('')}</optgroup>` : ad.map(opt).join('')}
  </select>${sw}`;
}

let plateKey = '';
const lastPlate = { t: null, px: null };
function renderPlate(force) {
  const busy = S.yeniden;
  const free = !PX_SIZES.includes(+S.ayar.boy);
  $('#angles').innerHTML = ANGLES.map(a => `<button data-a="${a.id}" aria-pressed="${S.ayar.aci === a.id}" ${busy ? 'disabled' : ''}>${a.name}</button>`).join('');
  $('#sizes').innerHTML = PX_SIZES.map(p => `<button data-px="${p}" aria-pressed="${+S.ayar.boy === p}" ${busy ? 'disabled' : ''}>${p}</button>`).join('') +
    `<input id="pxFree" type="number" min="16" max="512" step="1" placeholder="özel" aria-label="Özel boy (piksel)" value="${free ? S.ayar.boy : ''}" ${busy ? 'disabled' : ''}>`;
  $('#pals').innerHTML = palHtml(busy);
  if (S.vtab !== 'tp') return;
  // while a re-render runs, keep showing the last images under the hatch
  const t = busy ? lastPlate.t : toonUrl(), px = busy ? lastPlate.px : pikselUrl();
  if (!busy) Object.assign(lastPlate, { t, px });
  const key = [t, px, S.stamp, busy?.adim, $('#plate').clientWidth, $('#plate').clientHeight].join('|');
  if (!force && key === plateKey) return;
  plateKey = key;
  const ang = ANGLES.find(a => a.id === S.ayar.aci)?.name || S.ayar.aci;
  const toonBusy = busy && busy.adim === 'toon', pxBusy = !!busy;
  $('#plate').innerHTML = `
    <figure class="${toonBusy ? 'busy' : ''}">${t ? `<div><img id="toonImg" alt="Toon render" style="max-height:100%"></div>` : `<div class="miss">Bu açı için toon yok</div>`}
      <figcaption><b>07</b> Toon · ${ang}${toonBusy ? ' · hazırlanıyor' : ''}</figcaption></figure>
    <figure class="${pxBusy ? 'busy' : ''}">${px ? `<div id="pxBig" class="loupe"></div>` : `<div class="miss">Bu boy için sprite yok</div>`}
      <figcaption><b>08</b> Piksel · ${esc(S.ayar.boy)} px · 5×${pxBusy ? ' · hazırlanıyor' : ''}</figcaption></figure>
    <figure><div id="pxOne"></div><figcaption>gerçek boyut</figcaption></figure>`;
  if (t) loadImage(bust(t)).then(im => { const el = $('#toonImg'); if (el) el.src = cropToAlpha(im, 8); }).catch(() => {});
  if (px) loadImage(bust(px)).then(im => {
    const lp = $('#pxBig'), one = $('#pxOne'); if (!lp) return;
    const zoom = 5;
    const big = document.createElement('canvas'); big.width = im.width * zoom; big.height = im.height * zoom; big.className = 'pix';
    const bx = big.getContext('2d'); bx.imageSmoothingEnabled = false; bx.drawImage(im, 0, 0, big.width, big.height);
    big.style.maxWidth = 'none'; big.style.maxHeight = 'none';
    lp.replaceChildren(big);
    const bb = spriteBox(im);
    lp.scrollLeft = (bb.x + bb.w / 2) * zoom - lp.clientWidth / 2;
    lp.scrollTop = (bb.y + bb.h * 0.3) * zoom - lp.clientHeight / 2;
    panify(lp);
    const c1 = document.createElement('img'); c1.src = im.src; c1.className = 'pix'; c1.alt = 'Sprite, gerçek boyut';
    one.replaceChildren(c1);
  }).catch(() => {});
}

function loadImage(src) {
  return new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
}
function alphaBox(src, thr = 8) {
  const w = src.naturalWidth || src.width, h = src.naturalHeight || src.height;
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const x = c.getContext('2d', { willReadFrequently: true }); x.drawImage(src, 0, 0);
  const d = x.getImageData(0, 0, w, h).data; let x0 = w, y0 = h, x1 = -1, y1 = -1;
  for (let y = 0; y < h; y++) for (let i = 0; i < w; i++) if (d[(y * w + i) * 4 + 3] > thr) { if (i < x0) x0 = i; if (i > x1) x1 = i; if (y < y0) y0 = y; if (y > y1) y1 = y; }
  return { c, x0, y0, x1, y1, w, h };
}
// Trims transparent margins for display only; downloads keep the full frame.
function cropToAlpha(src, pad = 0) {
  const { c, x0, y0, x1, y1, w, h } = alphaBox(src);
  if (x1 < x0) return src.src;
  const a = Math.max(0, x0 - pad), b = Math.max(0, y0 - pad), e = Math.min(w - 1, x1 + pad), f = Math.min(h - 1, y1 + pad);
  const o = document.createElement('canvas'); o.width = e - a + 1; o.height = f - b + 1;
  o.getContext('2d').drawImage(c, a, b, o.width, o.height, 0, 0, o.width, o.height);
  return o.toDataURL('image/png');
}
function spriteBox(im) {
  const { x0, y0, x1, y1, w, h } = alphaBox(im, 0);
  return x1 < x0 ? { x: 0, y: 0, w, h } : { x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 };
}
function panify(el) {
  let p = null;
  el.onpointerdown = e => { p = [e.clientX, e.clientY, el.scrollLeft, el.scrollTop]; el.setPointerCapture(e.pointerId); };
  el.onpointermove = e => { if (!p) return; el.scrollLeft = p[2] - (e.clientX - p[0]); el.scrollTop = p[3] - (e.clientY - p[1]); };
  el.onpointerup = () => { p = null; };
}

// ---------------------------------------------------------------------------------------------
// Right panel

function renderRight() {
  const el = $('#right'), p = phase(), acc = access(), g = S.sistem?.gpu;
  if (isDone()) {
    const parts = viewer.hasParts ? viewer.parts : [], hp = parts.length > 0;
    if (!hp && S.tab === 'parts') S.tab = 'files';
    const tabs = `<div class="tabs" role="tablist">
        <button role="tab" data-t="parts" aria-selected="${S.tab === 'parts'}" ${hp ? '' : 'disabled'}>Parçalar <span class="c">${hp ? parts.length : '—'}</span></button>
        <button role="tab" data-t="files" aria-selected="${S.tab === 'files'}">İndir</button>
        <button role="tab" data-t="hist" aria-selected="${S.tab === 'hist'}">Geçmiş</button></div>`;
    let body = '';
    if (p === 'hata' && S.tab !== 'hist') body = `<div class="k">Günlük</div><div class="log" id="log">${logHtml()}</div>`;
    if (S.tab === 'parts' && hp) body += `<div class="phead"><span>${parts.length} parça · ${fmtInt(parts.reduce((a, x) => a + x.tris, 0))} üçgen</span><span><button data-all="1">Tümü</button> · <button data-all="0">Hiçbiri</button></span></div>
        <div class="parts" id="plist">${parts.map((x, i) => `<div class="part ${S.hidden.has(i) ? 'off' : ''} ${S.hi === i ? 'hi' : ''}" data-i="${i}">
          <span class="sw" style="background:${x.color}">${i + 1}</span><span>${esc(x.name)}</span><span class="t">${fmtInt(x.tris)}</span>
          <button data-tog="${i}" aria-label="${esc(x.name)} ${S.hidden.has(i) ? 'göster' : 'gizle'}" aria-pressed="${!S.hidden.has(i)}">${icon(S.hidden.has(i) ? 'eyeoff' : 'eye')}</button></div>`).join('')}</div>`;
    else if (S.tab === 'files') body += filesHtml();
    else if (S.tab === 'hist') body += gallery();
    el.innerHTML = tabs + body;
    if (S.tab === 'files') fillSizes();
    return;
  }
  if (p === 'calisiyor') {
    const tot = S.vram?.toplam_gb || g?.toplam_gb || 0, now = S.vram?.kullanilan_gb;
    el.innerHTML = `<div class="k">VRAM · ${esc(gpuAd())}</div>
      <div class="vram"><div class="big"><b id="vNow">${now != null ? gb(now) : '—'}</b><span>/ ${tot ? gb(tot) : '—'} GB</span><span style="margin-left:auto" id="vPeak">tepe ${gb(S.tepe)}</span></div>
        <div class="meter"><i id="vBar" style="width:0%"></i><u id="vTick" style="left:0%"></u></div>
        <div class="ticks">${tot ? [0, 1, 2, 3, 4].map(i => `<span>${Math.round(tot * i / 4)}${i === 4 ? ' GB' : ''}</span>`).join('') : ''}</div>
        <div class="note2" id="vNote"></div></div>
      <div class="k" style="margin-top:8px">Günlük</div><div class="log" id="log">${logHtml()}</div>`;
    tickVram(); return;
  }
  // idle: what each step needs against this card
  const total = acc.total, scale = Math.max(40, total || 0);
  const rows = STAGES.filter(x => x.vram).map(x => {
    const need = x.id === 'xpart' ? xpartNeed() : x.vram;
    const over = total ? need > total : false;  // X-Part still runs (spills); the others are gated by their route
    const inRoute = ROUTE_STEPS[S.rota].includes(x.id) || (x.id === 'xpart' && S.xpart);
    return `<div class="row ${over ? 'off' : ''} ${!inRoute && !over ? 'dim' : ''}"><span>${x.name}</span>
      <span class="b"><i style="width:${Math.min(100, x.vram / scale * 100)}%"></i>${total ? `<em style="left:${Math.min(100, total / scale * 100)}%"></em>` : ''}</span>
      <span class="v">${over ? icon(x.id === 'xpart' ? 'warn' : 'lock') + ' ' : ''}${need} GB</span></div>`;
  }).join('');
  const gname = g ? `${esc(gpuAd())} · ${gb(g.toplam_gb)} GB` : S.sunucu === 'ok' ? 'GPU yok' : '';
  const notes = [];
  if (S.sunucu === 'yok') notes.push(`${icon('warn')}<span>Sunucuya ulaşılamıyor. <span class="mono">baslat.ps1</span> ile başlat; sayfa kendini yeniler.</span>`);
  if (S.sistem && !acc.blender) notes.push(`${icon('warn')}<span>Blender bulunamadı: toon ve piksel adımları atlanır.</span>`);
  if (S.sistem && g && g.bos_gb != null && g.bos_gb < ROUTE_PEAK && g.toplam_gb >= ROUTE_PEAK) notes.push(`${icon('warn')}<span>Kartta şu an ${gb(g.bos_gb)} GB boş. Başka uygulamalar VRAM kullanıyor olabilir.</span>`);
  notes.push(`${icon('clock')}<span>Süreler ve VRAM RTX 5090 ölçümü. Toon ve piksel her rotada çalışır.</span>`);
  el.innerHTML = `<div class="k">VRAM ihtiyacı${gname ? ' · ' + gname : ''}</div>
    <div class="need">${rows}</div>
    ${total ? `<div class="legend"><i></i>${esc(gpuAd())} · ${gb(total)} GB</div>` : ''}
    ${notes.map(n => `<div class="note">${n}</div>`).join('')}
    <div class="k" style="margin-top:6px">Geçmiş</div>${gallery()}`;
}

function logHtml() {
  return S.log.slice(-60).map(l => `<div class="${l.err ? 'err' : ''}"><span>${l.clock ? l.clock.slice(3) : fmtTime(l.t)}</span><em>${esc(l.n || '··')}</em>${esc(l.msg)}</div>`).join('');
}
// "[doku] text" -> step number + text (the server prefixes step output with its id)
function logSatir(satir, adim) {
  const m = /^\[(\w+)\]\s*(.*)$/.exec(satir);
  const id = adim || (m && LOG_AD[m[1]] ? m[1] : null);
  const err = /error|hata|traceback|out of memory/i.test(satir);
  return { n: id ? LOG_AD[id] : '··', msg: m && LOG_AD[m[1]] ? m[2] : satir, err };
}
function appendLog(l) {
  S.log.push(l);
  const el = $('#log'); if (!el) return;
  el.insertAdjacentHTML('beforeend', `<div class="${l.err ? 'err' : ''}"><span>${fmtTime(l.t)}</span><em>${esc(l.n || '··')}</em>${esc(l.msg)}</div>`);
  while (el.children.length > 60) el.firstElementChild.remove();
}
function tickVram() {
  if (!$('#vNow')) return;
  const tot = S.vram?.toplam_gb || S.sistem?.gpu?.toplam_gb || 0, now = S.vram?.kullanilan_gb;
  $('#vNow').textContent = now != null ? gb(now) : '—';
  $('#vPeak').textContent = `tepe ${gb(S.tepe)}`;
  if (tot) { $('#vBar').style.width = Math.min(100, (now || 0) / tot * 100) + '%'; $('#vTick').style.left = Math.min(100, S.tepe / tot * 100) + '%'; }
  $('#vNote').textContent = S.vram === null ? 'VRAM okunamıyor' : '';
}

function gallery(inPop) {
  if (!S.isler.length) return `<div class="gal-empty">${S.sunucu === 'ok' ? 'Henüz iş yok.' : '—'}</div>`;
  return `<div class="gal">${S.isler.map(j => {
    const cur = S.job && S.job.id === j.id;
    const tag = j.durum === 'hata' ? '<span class="st-tag err">hata</span>' : j.durum === 'bitti' ? '' : `<span class="st-tag">${j.durum === 'calisiyor' ? 'çalışıyor' : 'sırada'}</span>`;
    const np = j.parca_sayisi ?? j.adimlar?.ayrik?.ayrinti?.parca_sayisi ?? null;
    const kapak = j.kapak || j.girdi?.on || ciktiUrl(j.id, 'input_rgba.png');
    return `<div class="run" data-job="${esc(j.id)}" role="button" tabindex="0" aria-current="${cur}" aria-label="${esc(j.ad || 'Adsız iş')} aç">
      <span class="im"><img src="${esc(kapak)}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'ph',innerHTML:'<svg class=&quot;i&quot;><use href=&quot;#i-img&quot;/></svg>'}))"></span>
      <span><b>${esc(j.ad || 'Adsız iş')}</b> ${tag}<small>${esc(fmtDate(j.olusturma))}</small><small>${j.rota === 'parcali' ? 'Parçalı' : 'Hafif'}${np ? ` · ${np} parça` : ''}</small></span>
      ${inPop || !cur ? `<button class="del" data-del="${esc(j.id)}" title="Sil" aria-label="İşi sil">${icon('x')}</button>` : ''}</div>`;
  }).join('')}</div>`;
}

// Downloads: every file the job announced, grouped. Sizes come from HEAD requests.
function filesHtml() {
  const o = outs();
  const row = (kind, name, url, cls = '') => `<a class="file ${cls}" href="${esc(bust(url))}" download="${esc(name.split('/').pop())}" data-size="${esc(url)}">
    <span class="kd">${kind}</span><span>${esc(name)}</span><span class="sz"></span>${icon('down')}</a>`;
  const rows = [];
  if (o['paket.zip']) rows.push(row('ZIP', 'paket.zip · hepsi', o['paket.zip'], 'main'));
  if (o['textured.glb']) rows.push(row('GLB', 'textured.glb', o['textured.glb']));
  if (o['shape.glb']) rows.push(row('GLB', 'shape.glb', o['shape.glb']));
  const partFiles = Object.keys(o).filter(k => /^parts\/.*\.glb$/.test(k)).sort();
  if (partFiles.length) rows.push(`<details><summary><span class="kd">Parça</span><span>parts/ · ${partFiles.length} GLB</span><span class="sz"></span>${icon('down')}</summary>
    ${partFiles.map(k => row('GLB', k.replace('parts/', ''), o[k])).join('')}</details>`);
  if (o['parts.glb']) rows.push(row('GLB', 'parts.glb · tek sahne', o['parts.glb']));
  if (o['parts.json']) rows.push(row('JSON', 'parts.json', o['parts.json']));
  const xp = Object.keys(o).filter(k => k.startsWith('xpart/')).sort();
  if (xp.length) rows.push(`<details><summary><span class="kd">X-Part</span><span>xpart/ · ${xp.length} dosya</span><span class="sz"></span>${icon('down')}</summary>
    ${xp.map(k => row('GLB', k.replace('xpart/', ''), o[k])).join('')}</details>`);
  for (const k of Object.keys(o).filter(k => /^toon_.*\.png$/.test(k)).sort()) rows.push(row('Toon', k, o[k]));
  for (const k of Object.keys(o).filter(k => /^piksel_.*\.png$/.test(k)).sort()) rows.push(row('Piksel', k, o[k]));
  for (const k of ['input_rgba.png', 'input_back_rgba.png']) if (o[k]) rows.push(row('Görsel', k, o[k]));
  // intermediates (P3-SAM masks, the uploaded originals) stay out, as in paket.zip
  const known = /^(paket\.zip|textured\.glb|shape\.glb|parts\.json|parts\.glb|parts\/.*|xpart\/.*|p3sam\/.*|toon_.*\.png|piksel_.*\.png|input_(back_)?rgba\.png|girdi_.*)$/;
  for (const k of Object.keys(o).filter(k => !known.test(k)).sort()) rows.push(row('Dosya', k, o[k]));
  const note = viewer.hasParts || S.job?.rota === 'parcali' ? '' : `<div class="note">${icon('parts')}<span>Parça GLB'leri ve parts.json Parçalı rotada üretilir.</span></div>`;
  const tex = o['textured.glb'] ? `<div class="note">${icon('paint')}<span>Dokular textured.glb içinde gömülü.</span></div>` : '';
  return rows.length ? `<div class="files">${rows.join('')}</div>${tex}${note}` : `<div class="note">${icon('warn')}<span>Bu işte indirilecek dosya yok.</span></div>`;
}
const sizeCache = new Map();
function fillSizes() {
  document.querySelectorAll('[data-size]').forEach(async a => {
    const url = a.dataset.size, k = url + '|' + S.stamp;
    if (!sizeCache.has(k)) sizeCache.set(k, fetch(bust(url), { method: 'HEAD' }).then(r => r.ok ? +r.headers.get('content-length') || null : null).catch(() => null));
    const n = await sizeCache.get(k);
    const sz = a.querySelector('.sz'); if (sz && n) sz.textContent = fmtSize(n);
  });
}

// ---------------------------------------------------------------------------------------------
// Render all

function renderAll() {
  renderHeader(); renderStrip(); renderLeft(); renderViewer(); renderRight(); renderPlate();
}
const gpuAd = () => (S.sistem?.gpu?.ad || '').replace(/^NVIDIA\s+/i, '').replace(/^GeForce\s+/i, '');
const MODEL_KISA = { sekil_21: 'Şekil (2.1)', sekil_2mv: 'Şekil (2mv)', doku: 'Doku', p3sam: 'P3-SAM' };
function renderHeader() {
  const el = $('#gpu'), g = S.sistem?.gpu;
  const tut = $('#tutBtn'), b = S.sistem?.bellek;
  tut.hidden = !b;
  if (b) {
    tut.setAttribute('aria-checked', String(!!b.modelleri_tut));
    const y = (b.yuklu || []).map(m => `${MODEL_KISA[m.ad] || m.ad} ${gb(m.gb)} GB`);
    tut.title = (b.modelleri_tut ? 'Açık: modeller işler arasında ekran kartında kalır, ikinci çalıştırma yüklemeyi atlar.'
      : 'Kapalı: her model işin son adımından sonra bellekten çıkar.') + (y.length ? `\nŞu an bellekte: ${y.join(' · ')}` : '\nŞu an bellekte model yok');
  }
  el.className = 'gpu' + (S.sunucu === 'yok' ? ' off' : S.sunucu === 'bekle' ? ' wait' : !g ? ' off' : '');
  $('#gpuName').textContent = S.sunucu === 'yok' ? 'Sunucu yok' : S.sunucu === 'bekle' ? 'Sunucuya bağlanıyor…' : g ? `${gpuAd()} · ${gb(g.toplam_gb)} GB` : 'GPU bulunamadı';
  el.title = g && g.bos_gb != null ? `Boş: ${gb(g.bos_gb)} GB${S.sistem.surum ? ' · sürüm ' + S.sistem.surum : ''}` : 'Ekran kartı';
}
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('on');
  clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove('on'), 3200);
}

// ---------------------------------------------------------------------------------------------
// Server: sistem, history, VRAM polling

async function connect() {
  try {
    S.sistem = await api.sistem(); S.sunucu = 'ok';
    if (!Array.isArray(S.sistem.paletler)) api.paletler().then(r => { S.paletler = Array.isArray(r) ? r : r?.paletler; renderPlate(true); }).catch(() => {});
    autoRoute();
    refreshHistory();
  } catch {
    S.sunucu = 'yok';
    setTimeout(connect, 3000);
  }
  renderAll();
}
async function sistemYenile() {  // kept models change after every job
  try { S.sistem = await api.sistem(); renderHeader(); } catch { /* the next poll will tell */ }
}
async function refreshHistory() {
  try {
    S.isler = (await api.isler()).sort((a, b) => String(b.olusturma || '').localeCompare(String(a.olusturma || '')));
  } catch { return; }
  if (!isDone() || S.tab === 'hist') renderRight();
  if ($('#pop').classList.contains('on')) renderPop();
}

let vramTimer = null;
function vramPolling(on) {
  if (on && !vramTimer) {
    const poll = async () => {
      if (document.hidden) return;
      try { S.vram = await api.vram(); S.tepe = Math.max(S.tepe, S.vram.kullanilan_gb || 0); }
      catch { S.vram = null; }
      tickVram();
    };
    poll(); vramTimer = setInterval(poll, 500);
  } else if (!on && vramTimer) { clearInterval(vramTimer); vramTimer = null; }
}
setInterval(() => { if (phase() === 'calisiyor') renderClock(); }, 500);

// ---------------------------------------------------------------------------------------------
// Input

const IMG_OK = /^image\/(png|jpeg|webp)$/;
// keep a runnable route selected when the input or the machine changes what can run
function autoRoute() {
  const acc = access();
  if (!acc[S.rota]?.ok) { const other = S.rota === 'hafif' ? 'parcali' : 'hafif'; if (acc[other]?.ok) S.rota = other; }
  if (S.rota !== 'parcali') S.xpart = false;
}
// a dropped GLB shows in the viewer at once (local file, before any upload)
async function previewMesh(file) {
  if (S.job) return;
  viewer.clear(); modelKey = '';
  if (!file || !/\.glb$/i.test(file.name)) { renderViewer(); return; }
  const url = URL.createObjectURL(file);
  S.yukleniyor = true; renderViewer();
  try { await viewer.loadModel({ textured: url, shape: url }, { intro: 'shape' }); viewer.setMode(viewer.canTexture ? 'textured' : 'clay', true); S.mode = viewer.mode; }
  catch { S.girdi.hata = 'Mesh okunamadı'; }
  finally { S.yukleniyor = false; URL.revokeObjectURL(url); renderAll(); }
}
const MESH_OK = /\.(glb|gltf|obj|ply|stl)$/i;
// An image goes to the front (or back) slot; a mesh file replaces the image input (it skips 01-02).
function setInput(which, file) {
  const g = S.girdi;
  if (file && which !== 'arka' && MESH_OK.test(file.name)) {
    g.hata = null; g.mesh = file;
    for (const w of ['on', 'arka']) { if (g[w + 'Url']) URL.revokeObjectURL(g[w + 'Url']); g[w] = null; g[w + 'Url'] = null; }
    autoRoute(); renderAll(); previewMesh(file); return;
  }
  if (which === 'mesh') { g.mesh = null; autoRoute(); previewMesh(null); renderAll(); return; }
  if (file && !IMG_OK.test(file.type)) { g.hata = 'PNG, JPG, WEBP ya da GLB, OBJ bırak'; renderLeft(); return; }
  g.hata = null;
  if (file && which === 'on' && g.mesh) { g.mesh = null; previewMesh(null); }
  if (g[which + 'Url']) URL.revokeObjectURL(g[which + 'Url']);
  g[which] = file || null; g[which + 'Url'] = file ? URL.createObjectURL(file) : null;
  if (which === 'on' && !file && g.arka) setInput('arka', null);
  autoRoute(); renderAll();
}
// Leaves a finished job for a new run with the same input (the local file, or the job's own input image fetched
// back) and the given route / X-Part choice.
async function prepareRerun(rota, xp) {
  const id = S.job.id;
  let file = S.girdi.on;
  if (!file) { try { const b = await (await fetch(ciktiUrl(id, 'input_rgba.png'))).blob(); file = new File([b], (S.job.ad || 'girdi') + '.png', { type: 'image/png' }); } catch { file = null; } }
  leaveJob(); S.rota = rota; S.xpart = rota === 'parcali' && xp; S.ayar.tohum = randSeed();
  if (file && !S.girdi.on) setInput('on', file); else renderAll();
}
function leaveJob() {
  if (closeStream) { closeStream(); closeStream = null; }
  S.job = null; S.log = []; S.t0 = null; S.mesaj = null; S.thumbs = {}; S.tepe = 0; S.yeniden = null;
  S.hidden = new Set(); S.hi = -1; S.explode = 0; S.vtab = '3d';
  viewer.clear(); vramPolling(false); lastPlate.t = lastPlate.px = null; modelKey = '';
  history.replaceState(null, '', location.pathname + location.search);
}

// ---------------------------------------------------------------------------------------------
// Run

let closeStream = null;
async function start() {
  const acc = access(), g = S.girdi;
  if (!hasInput() || !acc[S.rota]?.ok) return;
  const t = $('#tohum'); if (t) S.ayar.tohum = parseInt(t.value, 10) || 0;
  if (S.rota === 'parcali' && S.xpart && acc.xpart.warn
    && !confirm(`X-Part ${acc.xpart.warn}. Adım 12 dakikadan uzun sürebilir. Başlatılsın mı?`)) return;
  persist();
  const form = { on: g.mesh ? null : g.on, arka: acc.arka && !g.mesh ? g.arka : null, mesh: g.mesh || null, rota: S.rota,
    xpart: S.rota === 'parcali' && S.xpart && acc.xpart.ok, doku: dokuOn(),
    toon_aci: S.ayar.aci, piksel_boy: S.ayar.boy, palet: S.ayar.palet, tohum: S.ayar.tohum };
  $('#go').disabled = true;
  let r;
  try { r = await api.baslat(form); }
  catch (e) { toast(`Başlatılamadı: ${hataMetni(e)}`); renderLeft(); return; }
  const id = String(r.id), file = g.mesh || g.on;
  S.job = { id, durum: 'bekliyor', rota: form.rota, xpart: form.xpart, doku: form.doku, mesh: !!form.mesh, adimlar: {}, arka: !!form.arka,
    ad: file?.name?.replace(/\.[^.]+$/, '') || null, girdi: {},
    ayarlar: { toon_aci: form.toon_aci, piksel_boy: form.piksel_boy, palet: form.palet, tohum: form.tohum } };
  S.log = []; S.t0 = Date.now(); S.tepe = 0; S.thumbs = { gorsel: g.onUrl }; S.mesaj = null;
  viewer.clear(); modelKey = '';
  history.replaceState(null, '', '#is=' + encodeURIComponent(id));
  follow(id);
  renderAll();
  refreshHistory();
  // the saved state has the queue position and, for a mesh, the mesh itself (shown before any step runs)
  try {
    const j = await api.is(id);
    if (S.job?.id === id) {
      for (const [k, v] of Object.entries(j.adimlar)) if (!S.job.adimlar[k]) S.job.adimlar[k] = v;
      Object.assign(S.job, { sira: j.sira, cikti: j.cikti, girdi: j.girdi, mesh: j.mesh, doku: j.doku });
      if (S.job.mesh) loadOutputs({ live: true, intro: 'shape' });
      renderStrip(); renderClock();
    }
  } catch { /* the stream carries on */ }
}

// Live run: SSE events drive the strip, log, VRAM polling and the viewer, step by step.
function follow(id) {
  if (closeStream) closeStream();
  vramPolling(true);
  closeStream = olaylar(id, e => onEvent(id, e), () => {
    // stream dropped (server restarted?): fall back to the saved state
    if (S.job?.id === id && phase() === 'calisiyor') setTimeout(() => openJob(id, { keep: true }), 1500);
  });
}
function onEvent(id, e) {
  if (!S.job || S.job.id !== id) return;
  const job = S.job;
  if (e.tur === 'adim' && e.adim) {
    const prev = job.adimlar[e.adim] || {};
    const a = job.adimlar[e.adim] = { ...prev, ...e };
    if (a.durum === 'calisiyor' && job.durum === 'bekliyor') job.durum = 'calisiyor';
    if (a.tepe_vram_gb) S.tepe = Math.max(S.tepe, a.tepe_vram_gb);
    if (prev.durum !== a.durum) {
      renderStrip(); renderLeft(); renderClock();
      if (a.durum === 'bitti') onStepDone(e.adim, true);
      if (a.durum === 'hata') appendLog({ t: elapsed(), n: LOG_AD[e.adim], msg: hataMetni(`${e.adim}_hata`), err: true });
    } else tickStrip(e.adim);
  } else if (e.tur === 'log') {
    appendLog({ t: e.t ?? elapsed(), ...logSatir(e.satir ?? '', e.adim) });
  } else if (e.tur === 'bitti') {
    job.durum = 'bitti'; vramPolling(false);
    syncJob(id); sistemYenile();
  } else if (e.tur === 'hata') {
    job.durum = 'hata'; vramPolling(false);
    S.mesaj = { baslik: hataMetni(e.mesaj || 'hata'), metin: hataOzeti(job) };
    if (S.log.at(-1)?.msg !== hataMetni(e.mesaj || 'hata')) appendLog({ t: elapsed(), n: '!', msg: hataMetni(e.mesaj || 'hata'), err: true });
    S.tab = 'files';
    syncJob(id);
  }
}
async function syncJob(id) {
  try {
    const j = await api.is(id);
    if (S.job?.id === id) {
      S.job = { ...j, ad: j.ad || S.job.ad };
      if (j.durum === 'hata') S.mesaj = { baslik: hataMetni(j.mesaj || 'hata'), metin: hataOzeti(j) };
    }
  } catch { /* keep the streamed state */ }
  await loadOutputs({ live: false });
  renderAll(); refreshHistory();
}

// Loads whatever model outputs exist into the viewer and makes the strip thumbnails from them.
let modelKey = '';
async function loadOutputs({ live, intro = null } = {}) {
  const job = S.job; if (!job) return;
  const o = outs(), done = id => step(id)?.durum === 'bitti';
  const model = {
    // a job made from a ready mesh has shape.glb (and textured.glb if the mesh had a texture) from the start
    shape: done('sekil') ? (o['shape.glb'] || ciktiUrl(job.id, 'shape.glb')) : job.mesh ? o['shape.glb'] || null : null,
    textured: done('doku') ? (o['textured.glb'] || ciktiUrl(job.id, 'textured.glb')) : job.mesh ? o['textured.glb'] || null : null,
    parts: null,
  };
  if (done('ayrik')) {
    try {
      const pj = await (await fetch(o['parts.json'] || ciktiUrl(job.id, 'parts.json'))).json();
      model.parts = (pj.parts || []).map((p, i) => {
        const file = String(p.file || `part_${String(i).padStart(2, '0')}.glb`), rel = file.includes('/') ? file : 'parts/' + file;
        return { url: o[rel] || ciktiUrl(job.id, rel),
        guess: p.guess || p.ad || null, faces: p.faces || null, renk: p.renk || null };
      });
    } catch (err) { console.warn('parts.json okunamadı', err); }
  }
  // X-Part's closed meshes replace the P3-SAM pieces in the viewer when they exist (no texture: Dokulu stays whole)
  if (done('xpart')) {
    const xs = Object.keys(o).filter(k => /^xpart\/parts\/part_\d+\.glb$/.test(k)).sort();
    if (xs.length) model.parts = xs.map(k => ({ url: o[k], guess: null, faces: null, renk: null }));
  }
  const key = job.id + '|' + !!model.shape + !!model.textured + (model.parts?.length || 0);
  if (key === modelKey && viewer.parts.length) { refreshPixelThumbs(); return; }
  if (!model.shape && !model.textured) { refreshPixelThumbs(); return; }
  modelKey = key;
  S.yukleniyor = true; renderViewer();
  try {
    await viewer.loadModel(model, { intro: live ? intro : null, frameKey: job.id });
    if (S.job?.id !== job.id) return;
    S.hidden = new Set(); S.hi = -1;
    if (!live) S.mode = viewer.canTexture ? 'textured' : 'clay';
    else if (intro === 'tex') S.mode = 'textured';
    viewer.setMode(S.mode, true); S.mode = viewer.mode;
    makeThumbs();
  } catch (err) {
    console.error(err);
    S.mesaj = { baslik: 'Model yüklenemedi', metin: String(err.message || err) };
  } finally { S.yukleniyor = false; }
  refreshPixelThumbs();
  renderStrip(); renderViewer();
  if (isDone()) renderRight();
}
function makeThumbs() {
  const t = S.thumbs, has = id => step(id)?.durum === 'bitti';
  t.gorsel = inputSrc() || (S.job?.mesh ? viewer.snapshot({ mode: viewer.canTexture ? 'textured' : 'clay' }) : null);
  if (has('sekil')) t.sekil = viewer.snapshot({ mode: 'clay' });
  if (has('doku') && viewer.canTexture) t.doku = viewer.snapshot({ mode: 'textured' });
  // once X-Part's meshes replace the P3-SAM pieces in the viewer, 04/05 keep the thumbnails they already have
  const xp = has('xpart');
  if (has('parcalar') && viewer.hasParts && !(xp && t.parcalar)) t.parcalar = viewer.snapshot({ mode: 'parts' });
  if (has('ayrik') && viewer.hasParts && !(xp && t.ayrik)) t.ayrik = viewer.snapshot({ mode: 'parts', explode: 0.45 });
  if (xp && viewer.hasParts) t.xpart = viewer.snapshot({ mode: 'parts', explode: 0.45 });
}
function refreshPixelThumbs() {
  const tu = toonUrl(), pu = pikselUrl();
  if (tu) S.thumbs.toon = bust(tu); if (pu) S.thumbs.piksel = bust(pu);
}
function onStepDone(id, live) {
  const intro = { sekil: 'shape', doku: 'tex', ayrik: 'parts', xpart: 'parts' }[id];
  if (intro) loadOutputs({ live, intro });
  else if (id === 'parcalar') { /* parts show once 05 has written them */ }
  else { refreshPixelThumbs(); renderStrip(); renderViewer(); renderPlate(); }
}

// The saved log of a finished job (is.log in its folder), for the Günlük panel of a failed run.
async function loadLog(id) {
  try {
    const r = await fetch(ciktiUrl(id, 'is.log'), { cache: 'no-store' }); if (!r.ok) return;
    const lines = (await r.text()).split(/\r?\n/).filter(Boolean).slice(-60);
    if (S.job?.id !== id) return;
    S.log = lines.map(l => { const m = /^(\d\d:\d\d:\d\d) (.*)$/.exec(l); return { t: null, clock: m?.[1], ...logSatir(m ? m[2] : l) }; });
    if ($('#log')) $('#log').innerHTML = logHtml();
  } catch { /* no log */ }
}

// Opens a past or running job (Geçmiş, or a reload with #is=<id>).
async function openJob(id, { keep = false } = {}) {
  let j;
  try { j = await api.is(id); }
  catch (e) {
    if (e.status === 404) { toast('Bu iş artık yok'); history.replaceState(null, '', location.pathname); refreshHistory(); }
    else toast(`İş açılamadı: ${hataMetni(e)}`);
    return;
  }
  if (!keep) {
    leaveJob(); setInput('on', null);
  }
  S.job = j; modelKey = keep ? modelKey : '';
  S.ayar.aci = j.ayarlar.toon_aci || S.ayar.aci; S.ayar.boy = j.ayarlar.piksel_boy || S.ayar.boy; S.ayar.palet = j.ayarlar.palet || S.ayar.palet;
  if (!toonUrl()) { const k = Object.keys(outs()).find(k => /^toon_.*\.png$/.test(k)); if (k) S.ayar.aci = k.slice(5, -4); }
  if (!pikselUrl()) { const k = Object.keys(outs()).find(k => /^piksel_.*\.png$/.test(k)); if (k) S.ayar.boy = k.slice(7, -4); }
  for (const a of Object.values(j.adimlar)) if (a.tepe_vram_gb) S.tepe = Math.max(S.tepe, a.tepe_vram_gb);
  if (j.durum === 'hata') S.mesaj = { baslik: hataMetni(j.mesaj || 'hata'), metin: hataOzeti(j) };
  S.log = []; if (j.durum !== 'calisiyor' && j.durum !== 'bekliyor') loadLog(id);
  history.replaceState(null, '', '#is=' + encodeURIComponent(id));
  S.tab = viewer.hasParts ? 'parts' : 'files';
  renderAll();
  if (phase() === 'calisiyor') {
    S.t0 = Date.now() - (j.sure_sn || 0) * 1000;
    follow(id);
  }
  await loadOutputs({ live: false });
  if (isDone()) S.tab = viewer.hasParts ? 'parts' : 'files';
  renderAll();
}

// Re-render 07/08 with a new angle, size or palette. The GPU steps are not re-run.
// The server answers when the render is done (with the whole job); meanwhile we poll for the step progress.
async function rerender(kind, patch) {
  if (!S.job || !isDone() || S.yeniden) return;
  const prev = { ...S.ayar };
  Object.assign(S.ayar, patch); persist();
  const id = S.job.id;
  S.yeniden = { adim: kind, t0: Date.now(), seen: false, n: 0 };
  for (const k of kind === 'toon' ? ['toon', 'piksel'] : ['piksel']) {
    S.job.adimlar[k] = { ...(S.job.adimlar[k] || {}), durum: 'bekliyor', ilerleme: 0 };
  }
  renderStrip(); renderPlate(true);
  const progress = setInterval(async () => {
    try {
      const j = await api.is(id);
      if (S.job?.id !== id || !S.yeniden) return;
      for (const k of ['toon', 'piksel']) if (['calisiyor', 'bitti'].includes(j.adimlar[k]?.durum) && S.job.adimlar[k]?.durum !== 'bitti') S.job.adimlar[k] = j.adimlar[k];
      renderStrip();
    } catch { /* keep waiting */ }
  }, 700);
  let r;
  try {
    r = kind === 'toon' ? await api.toon(id, S.ayar.aci) : await api.piksel(id, +S.ayar.boy, S.ayar.palet);
  } catch (e) {
    clearInterval(progress);
    S.ayar = prev; S.yeniden = null; persist();
    toast(`${kind === 'toon' ? 'Toon' : 'Piksel'} yenilenemedi: ${hataMetni(e)}`);
    await syncJob(id); renderPlate(true); return;
  }
  clearInterval(progress);
  if (r && r.adimlar) finishRerender(normJob(r));
  else pollRerender(id, kind);   // a server that answers at once: poll until the steps settle
}
function finishRerender(j) {
  if (S.job?.id !== j.id) return;
  const failed = ['toon', 'piksel'].find(k => j.adimlar[k]?.durum === 'hata');
  if (failed) toast(`${failed === 'toon' ? 'Toon' : 'Piksel'} adımı hata verdi`);
  S.yeniden = null; S.stamp = Date.now();
  S.job = { ...j, ad: j.ad || S.job.ad };
  refreshPixelThumbs(); renderStrip(); renderPlate(true);
  if (S.tab === 'files') renderRight();
}
// Polls GET /api/is/{id} until the re-render settles (works whether or not the SSE stream replays old events).
async function pollRerender(id, kind) {
  const y = S.yeniden; if (!y || S.job?.id !== id) return;
  let j;
  try { j = await api.is(id); } catch { setTimeout(() => pollRerender(id, kind), 1000); return; }
  if (S.job?.id !== id) return;
  y.n++;
  const watch = kind === 'toon' ? ['toon', 'piksel'] : ['piksel'];
  const busyNow = j.durum === 'calisiyor' || j.durum === 'bekliyor' || watch.some(k => ['calisiyor', 'bekliyor'].includes(j.adimlar[k]?.durum));
  if (busyNow) y.seen = true;
  const settled = !busyNow && (y.seen || y.n >= 4);
  for (const k of watch) if (j.adimlar[k]) S.job.adimlar[k] = j.adimlar[k];
  S.job.cikti = j.cikti; S.job.durum = settled ? j.durum : 'bitti';
  if (!settled) {
    if (!y.seen) for (const k of watch) S.job.adimlar[k] = { ...S.job.adimlar[k], durum: 'calisiyor' };
    renderStrip(); setTimeout(() => pollRerender(id, kind), 600); return;
  }
  // toon re-renders the sprite only if the server chains it; otherwise ask for it
  if (kind === 'toon' && !y.chained && !pikselUrl()) {
    y.chained = true;
    try { await api.piksel(id, +S.ayar.boy, S.ayar.palet); y.seen = false; y.n = 0; setTimeout(() => pollRerender(id, kind), 600); return; } catch { /* show what we have */ }
  }
  finishRerender(j);
}

// ---------------------------------------------------------------------------------------------
// Parts

function select(i) { viewer.highlight(i); S.hi = i; document.querySelectorAll('.part').forEach(p => p.classList.toggle('hi', +p.dataset.i === i)); }
function toggle(i) { S.hidden.has(i) ? S.hidden.delete(i) : S.hidden.add(i); viewer.setVisible(i, !S.hidden.has(i)); renderRight(); }
function all(show) { viewer.parts.forEach((p, i) => { viewer.setVisible(i, show); show ? S.hidden.delete(i) : S.hidden.add(i); }); renderRight(); }

// ---------------------------------------------------------------------------------------------
// Events

function renderPop() { $('#pop').innerHTML = `<div class="k" style="margin-bottom:10px">Geçmiş</div>${gallery(true)}`; }
document.addEventListener('click', async e => {
  const t = e.target.closest('button, [data-job], [data-pick], [data-i]'); if (!t) return;
  if (t.id === 'tutBtn') {
    const yeni = t.getAttribute('aria-checked') !== 'true';
    try { await api.ayar({ modelleri_tut: yeni }); await sistemYenile(); toast(yeni ? 'Modeller işler arasında bellekte kalacak' : 'Modeller her işten sonra bellekten çıkacak'); }
    catch (err) { toast(`Ayar değişmedi: ${hataMetni(err)}`); }
    return;
  }
  if (t.dataset.del) {
    e.stopPropagation();
    if (!confirm('Bu iş ve çıktıları silinsin mi?')) return;
    try { await api.sil(t.dataset.del); } catch (err) { toast(`Silinemedi: ${hataMetni(err)}`); return; }
    if (S.job?.id === t.dataset.del) { leaveJob(); renderAll(); }
    refreshHistory(); return;
  }
  if (t.dataset.rm) { e.stopPropagation(); setInput(t.dataset.rm, null); return; }
  if (t.dataset.pick) { if (t.getAttribute('aria-disabled') === 'true') return; $(t.dataset.pick === 'arka' ? '#fileArka' : '#fileOn').click(); return; }
  if (t.dataset.job) { $('#pop').classList.remove('on'); $('#histBtn').setAttribute('aria-expanded', 'false'); if (S.job?.id !== t.dataset.job) openJob(t.dataset.job); return; }
  if (t.dataset.r) {
    const rota = t.dataset.r, xp = rota === 'hafif' ? false : (isDone() ? S.job.xpart : S.xpart);
    if (isDone()) { await prepareRerun(rota, xp); persist(); return; }
    S.rota = rota; S.xpart = xp; persist(); renderAll();
  }
  else if (t.dataset.xp) {
    if (isDone()) { await prepareRerun('parcali', !S.job.xpart); return; }
    S.xpart = !S.xpart; renderAll();
  }
  else if (t.dataset.seed) { S.ayar.tohum = randSeed(); renderLeft(); }
  else if (t.id === 'go') {
    if (isDone()) await prepareRerun(S.job.rota, S.job.xpart);
    else start();
  }
  else if (t.dataset.m) { viewer.setMode(t.dataset.m); S.mode = viewer.mode; renderViewer(); }
  else if (t.id === 'turn') { S.turntable = !S.turntable; viewer.setTurntable(S.turntable); renderViewer(); }
  else if (t.id === 'reset') viewer.resetView();
  else if (t.dataset.v) { S.vtab = t.dataset.v; renderViewer(); renderPlate(true); }
  else if (t.dataset.t) { S.tab = t.dataset.t; renderRight(); }
  else if (t.dataset.tog) toggle(+t.dataset.tog);
  else if (t.dataset.all) all(t.dataset.all === '1');
  else if (t.dataset.a) { if (t.dataset.a !== S.ayar.aci) rerender('toon', { aci: t.dataset.a }); }
  else if (t.dataset.px) { if (+t.dataset.px !== +S.ayar.boy) rerender('piksel', { boy: +t.dataset.px }); }
  else if (t.id === 'histBtn') { const p = $('#pop'); renderPop(); p.classList.toggle('on'); t.setAttribute('aria-expanded', p.classList.contains('on')); if (p.classList.contains('on')) refreshHistory(); }
  else if (t.dataset.i != null && !e.target.closest('button')) select(+t.dataset.i === S.hi ? -1 : +t.dataset.i);
});
document.addEventListener('change', e => {
  if (e.target.id === 'fileOn' || e.target.id === 'fileArka') {
    const f = e.target.files[0]; e.target.value = '';
    if (f) { if (S.job && isDone()) leaveJob(); setInput(e.target.id === 'fileOn' ? 'on' : 'arka', f); }
  } else if (e.target.id === 'pxFree') {
    const v = Math.round(+e.target.value);
    if (v >= 16 && v <= 512 && v !== +S.ayar.boy) rerender('piksel', { boy: v });
  } else if (e.target.id === 'dokuChk') {
    S.doku = e.target.checked; autoRoute(); renderAll();
  } else if (e.target.id === 'palSel') {
    if (e.target.value !== S.ayar.palet) rerender('piksel', { palet: e.target.value });
  } else if (e.target.id === 'tohum') S.ayar.tohum = parseInt(e.target.value, 10) || 0;
});
document.addEventListener('keydown', e => {
  const t = e.target;
  if ((e.key === 'Enter' || e.key === ' ') && t.matches?.('#drop[role=button], [data-pick], [data-job]')) { e.preventDefault(); t.click(); }
  if (e.key === 'Enter' && e.ctrlKey && !$('#go').disabled) $('#go').click();
  if (e.key === 'Escape' && $('#pop').classList.contains('on')) { $('#pop').classList.remove('on'); $('#histBtn').setAttribute('aria-expanded', 'false'); }
});
$('#drop').addEventListener('click', e => { if (!e.target.closest('[data-pick],[data-rm]') && $('#drop').getAttribute('role') === 'button') $('#fileOn').click(); });
// drag and drop: onto the drop zone, or anywhere on the page when nothing is running. Two files = front + back.
const canDrop = () => phase() !== 'calisiyor';
document.addEventListener('dragover', e => { if (!canDrop() || !e.dataTransfer?.types.includes('Files')) return; e.preventDefault(); $('#drop').classList.add('over'); });
document.addEventListener('dragleave', e => { if (!e.relatedTarget) $('#drop').classList.remove('over'); });
document.addEventListener('drop', e => {
  $('#drop').classList.remove('over');
  if (!canDrop() || !e.dataTransfer?.files.length) return;
  e.preventDefault();
  const files = [...e.dataTransfer.files];
  const onBack = e.target.closest?.('.back');
  if (S.job && isDone()) leaveJob();
  if (onBack && access().arka) setInput('arka', files[0]);
  else { setInput('on', files[0]); if (files[1] && access().arka) setInput('arka', files[1]); }
});
$('#explode').addEventListener('input', e => {
  S.explode = +e.target.value; viewer.setExplode(S.explode);
  e.target.style.setProperty('--p', S.explode * 100 + '%'); $('#exOut').textContent = Math.round(S.explode * 100);
});
document.addEventListener('mouseover', e => { const p = e.target.closest('.part'); if (p) { viewer.highlight(+p.dataset.i); } });
document.addEventListener('mouseout', e => { const p = e.target.closest('.part'); if (p && !p.contains(e.relatedTarget)) viewer.highlight(S.hi); });
document.addEventListener('click', e => { if ($('#pop').classList.contains('on') && !e.target.closest('#pop, #histBtn')) { $('#pop').classList.remove('on'); $('#histBtn').setAttribute('aria-expanded', 'false'); } });
window.addEventListener('resize', () => renderPlate());
window.addEventListener('hashchange', () => { const id = new URLSearchParams(location.hash.slice(1)).get('is'); if (id && S.job?.id !== id) openJob(id); });

// ---------------------------------------------------------------------------------------------

renderAll();
await connect();
const startId = new URLSearchParams(location.hash.slice(1)).get('is');
if (startId && S.sunucu === 'ok') await openJob(startId);
window.__atolye = { S, viewer, openJob, renderAll };
window.__ready = true;
