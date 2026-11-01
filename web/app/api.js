// API client for the local server (same origin). Contract: design/PLAN.md, "API contract".
// The server sends stable ids; every word a user reads is chosen on the web side.

export const ADIMLAR = ['sekil', 'doku', 'parcalar', 'ayrik', 'xpart', 'toon', 'piksel'];

// Errors are {hata: <stable id>, ayrinti}; the id is kept on the Error for the Turkish text (main.js hataMetni).
async function json(res) {
  if (!res.ok) {
    let kod = null, ayrinti = null;
    try { const j = await res.json(); kod = j.hata || j.mesaj || null; ayrinti = j.ayrinti ?? null; } catch { /* not json */ }
    const e = new Error(kod || String(res.status)); e.status = res.status; e.kod = kod; e.ayrinti = ayrinti; throw e;
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  sistem: () => fetch('/api/sistem', { cache: 'no-store' }).then(json),
  paletler: () => fetch('/api/paletler', { cache: 'no-store' }).then(json),
  vram: () => fetch('/api/vram', { cache: 'no-store' }).then(json),
  isler: () => fetch('/api/isler', { cache: 'no-store' }).then(json).then(r => (Array.isArray(r) ? r : r?.isler || []).map(normJob)),
  is: id => fetch(`/api/is/${encodeURIComponent(id)}`, { cache: 'no-store' }).then(json).then(normJob),
  sil: id => fetch(`/api/is/${encodeURIComponent(id)}`, { method: 'DELETE' }).then(json),
  baslat(form) {
    const fd = new FormData();
    for (const [k, v] of Object.entries(form)) if (v != null && v !== '') fd.append(k, v instanceof Blob ? v : String(v));
    return fetch('/api/is', { method: 'POST', body: fd }).then(json);
  },
  toon: (id, aci) => post(`/api/is/${encodeURIComponent(id)}/toon`, { aci }),
  piksel: (id, boy, palet) => post(`/api/is/${encodeURIComponent(id)}/piksel`, { boy, palet }),
  ayar: d => post('/api/ayar', d),
};
function post(url, body) {
  return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(json);
}

// SSE: one stream per job. Calls on(evt) with every parsed event; returns a close() function.
// EventSource reconnects by itself; after {tur:"bitti"|"hata"} we close it so it does not replay forever.
export function olaylar(id, on, onDrop) {
  const es = new EventSource(`/api/is/${encodeURIComponent(id)}/olaylar`);
  let closed = false;
  es.onmessage = m => {
    let e; try { e = JSON.parse(m.data); } catch { return; }
    on(e);
    if (e.tur === 'bitti' || e.tur === 'hata') { closed = true; es.close(); }
  };
  es.onerror = () => { if (!closed && es.readyState === EventSource.CLOSED) onDrop?.(); };
  return () => { closed = true; es.close(); };
}

// Job state, read tolerantly: adimlar may be a map {sekil:{...}} or a list [{adim:"sekil",...}].
export function normJob(j) {
  if (!j) return j;
  const adimlar = {};
  const src = j.adimlar || j.adim || {};
  if (Array.isArray(src)) for (const a of src) adimlar[a.adim || a.id] = a;
  else Object.assign(adimlar, src);
  const ay = j.ayarlar || {};
  return {
    ...j,
    id: String(j.id),
    durum: j.durum === 'iptal' ? 'hata' : (j.durum || 'bekliyor'),
    rota: j.rota || ay.rota || 'hafif',
    xpart: !!(j.xpart ?? ay.xpart),
    doku: ay.doku !== false && j.doku !== false,
    mesh: !!(j.girdi?.mesh || ay.model === 'mesh'),
    olusturma: j.olusturma || j.tarih || j.baslangic || null,
    ayarlar: { toon_aci: ay.toon_aci || j.toon_aci || 'ucceyrek', piksel_boy: ay.piksel_boy || j.piksel_boy || 160,
      palet: ay.palet || j.palet || 'ozgun', tohum: ay.tohum ?? j.tohum ?? null },
    adimlar,
    arka: !!(j.arka ?? j.girdi?.arka),
    ad: j.ad || j.isim || j.girdi?.ad || null,
  };
}

// Every output url a job has announced, newest wins: from the steps' cikti objects plus the fixed names.
export function ciktilar(job) {
  const out = {};
  const add = c => {
    if (!c || typeof c !== 'object') return;
    for (const v of Object.values(c).flat()) {
      if (typeof v !== 'string') continue;
      out[fileKey(v)] = /^(\/|https?:)/.test(v) ? v : ciktiUrl(job.id, v);
    }
  };
  add(job.cikti);
  for (const id of ADIMLAR) add(job.adimlar[id]?.cikti);
  if (job.girdi) add({ on: job.girdi.on, arka: job.girdi.arka });
  return out;
}
const fileKey = url => url.split('?')[0].replace(/^.*\/cikti\/[^/]+\//, '');
export const ciktiUrl = (id, name) => `/cikti/${encodeURIComponent(id)}/${name}`;
