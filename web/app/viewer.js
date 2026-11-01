// 3D viewer: loads a job's real outputs (shape.glb, textured.glb, parts/*.glb + parts.json) and shows them
// textured, as clay or part-coloured, with an explode spring, part picking and short arrival animations.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const GUESS_TR = { legs: 'Bacak', top: 'Üst', head: 'Baş', accessory: 'Aksesuar', torso: 'Gövde', body: 'Gövde',
  hair: 'Saç', arm: 'Kol', 'arm.L': 'Kol · sol', 'arm.R': 'Kol · sağ', 'foot.L': 'Ayak · sol', 'foot.R': 'Ayak · sağ',
  'hand.L': 'El · sol', 'hand.R': 'El · sağ', weapon: 'Silah', tail: 'Kuyruk', wing: 'Kanat' };

// Shader patch: per-fragment reveal (shape rising), texture sweep, part colour, hover highlight and dimming.
const PATCH_VERT = ['#include <common>', '#include <common>\nvarying float vLY;'];
const PATCH_VERT2 = ['#include <begin_vertex>', '#include <begin_vertex>\nvLY = transformed.y;'];
const PATCH_FRAG_HEAD = `#include <common>
varying float vLY;
uniform vec3 uClay; uniform vec3 uPart; uniform float uTexAmt; uniform float uPartAmt; uniform float uHasMap;
uniform float uReveal; uniform float uSweep; uniform float uSweepOn; uniform vec3 uGlow; uniform float uBand;
uniform float uHi; uniform vec3 uHiColor; uniform float uDim;`;
const PATCH_FRAG_MAP = `#include <map_fragment>
if (vLY > uReveal) discard;
float tAmt = uTexAmt * uHasMap * step(uSweep, vLY);
vec3 baseC = mix(uClay, diffuseColor.rgb, tAmt);
baseC = mix(baseC, uPart, uPartAmt);
diffuseColor.rgb = baseC * (1.0 - uDim);`;
const PATCH_FRAG_EMIT = `#include <emissivemap_fragment>
float bandA = (1.0 - smoothstep(0.0, uBand, abs(vLY - uReveal))) * step(uReveal, 1e4);
float bandB = (1.0 - smoothstep(0.0, uBand, abs(vLY - uSweep))) * uSweepOn;
totalEmissiveRadiance += uGlow * (bandA * 2.2 + bandB * 1.6) + uHiColor * uHi;`;

function makeMaterial(map, clay, partColor, glow, hiColor) {
  const m = new THREE.MeshStandardMaterial({ color: 0xffffff, map: map || null, roughness: 0.62, metalness: 0.0,
    side: THREE.DoubleSide });
  const u = {
    uClay: { value: new THREE.Color(clay) }, uPart: { value: new THREE.Color(partColor) },
    uTexAmt: { value: 1 }, uPartAmt: { value: 0 }, uHasMap: { value: map ? 1 : 0 },
    uReveal: { value: 1e5 }, uSweep: { value: -1e5 }, uSweepOn: { value: 0 }, uGlow: { value: new THREE.Color(glow) },
    uBand: { value: 0.03 }, uHi: { value: 0 }, uHiColor: { value: new THREE.Color(hiColor) }, uDim: { value: 0 },
  };
  m.userData.u = u;
  m.onBeforeCompile = sh => {
    Object.assign(sh.uniforms, u);
    sh.vertexShader = sh.vertexShader.replace(...PATCH_VERT).replace(...PATCH_VERT2);
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', PATCH_FRAG_HEAD)
      .replace('#include <map_fragment>', PATCH_FRAG_MAP).replace('#include <emissivemap_fragment>', PATCH_FRAG_EMIT);
  };
  return m;
}

// Shadow pass twin of makeMaterial: discards the same not-yet-revealed fragments so shadows match.
function makeDepthMaterial(u) {
  const m = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking, side: THREE.DoubleSide });
  m.onBeforeCompile = sh => {
    sh.uniforms.uReveal = u.uReveal;
    sh.vertexShader = sh.vertexShader.replace(...PATCH_VERT).replace(...PATCH_VERT2);
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying float vLY; uniform float uReveal;')
      .replace('void main() {', 'void main() {\n if (vLY > uReveal) discard;');
  };
  return m;
}

function goldenColors(n, s = 0.55, l = 0.62, hue0 = 0.07) {
  const out = [];
  for (let i = 0; i < n; i++) out.push(new THREE.Color().setHSL((hue0 + i * 0.381966) % 1, s, l));
  return out;
}

const loader = new GLTFLoader();
const loadGLB = url => new Promise((res, rej) => loader.load(url, res, undefined, rej));

// All meshes of a glTF baked into world space and merged into one geometry (Hunyuan outputs are one mesh;
// this keeps other GLBs working too). The first mesh's colour map is kept.
function bakeMeshes(gltf) {
  const geos = [], mats = [];
  gltf.scene.updateMatrixWorld(true);
  gltf.scene.traverse(o => { if (o.isMesh) { const g = o.geometry.clone(); g.applyMatrix4(o.matrixWorld); geos.push(g); mats.push(o.material); } });
  if (!geos.length) throw new Error('GLB içinde mesh yok');
  const geometry = geos.length === 1 ? geos[0] : mergeSimple(geos);
  const mat = Array.isArray(mats[0]) ? mats[0][0] : mats[0];
  return { geometry, map: mat?.map || null };
}
function mergeSimple(geos) {
  const parts = geos.map(g => g.index ? g.toNonIndexed() : g);
  const n = parts.reduce((a, g) => a + g.attributes.position.count, 0);
  const pos = new Float32Array(n * 3), uv = parts.every(g => g.attributes.uv) ? new Float32Array(n * 2) : null;
  let o = 0;
  for (const g of parts) {
    pos.set(g.attributes.position.array, o * 3);
    if (uv) uv.set(g.attributes.uv.array, o * 2);
    o += g.attributes.position.count;
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  if (uv) out.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  out.computeVertexNormals();
  return out;
}

// Copies UVs and normals from the textured mesh onto a part, triangle by triangle, when the parts are a
// partition of the textured mesh's faces. Returns how many triangles had no twin.
const Q = 4000;
function triKey(pos, a, b, c) {
  const x = Math.round((pos.getX(a) + pos.getX(b) + pos.getX(c)) / 3 * Q);
  const y = Math.round((pos.getY(a) + pos.getY(b) + pos.getY(c)) / 3 * Q);
  const z = Math.round((pos.getZ(a) + pos.getZ(b) + pos.getZ(c)) / 3 * Q);
  return x + ',' + y + ',' + z;
}
function buildTexIndex(geo) {
  if (!geo.attributes.normal) geo.computeVertexNormals();
  const pos = geo.attributes.position, index = geo.index;
  const idx = index ? (t, k) => index.getX(t * 3 + k) : (t, k) => t * 3 + k;
  const count = index ? index.count / 3 : pos.count / 3;
  const map = new Map();
  for (let t = 0; t < count; t++) map.set(triKey(pos, idx(t, 0), idx(t, 1), idx(t, 2)), t);
  return { map, pos, idx, uv: geo.attributes.uv, nor: geo.attributes.normal };
}
function transferUV(partGeo, texIndex) {
  const g = partGeo.index ? partGeo.toNonIndexed() : partGeo;
  const pos = g.attributes.position, n = pos.count;
  const uv = new Float32Array(n * 2), nor = new Float32Array(n * 3);
  let miss = 0;
  for (let i = 0; i < n; i += 3) {
    const key = triKey(pos, i, i + 1, i + 2);
    let twin = texIndex.map.get(key);
    if (twin === undefined) {   // centroid fell on a quantisation edge: try the neighbouring cells
      const [kx, ky, kz] = key.split(',').map(Number);
      for (let dx = -1; dx <= 1 && twin === undefined; dx++) for (let dy = -1; dy <= 1 && twin === undefined; dy++)
        for (let dz = -1; dz <= 1 && twin === undefined; dz++) twin = texIndex.map.get(`${kx + dx},${ky + dy},${kz + dz}`);
    }
    if (twin === undefined) { miss++; continue; }
    for (let c = 0; c < 3; c++) {
      const px = pos.getX(i + c), py = pos.getY(i + c), pz = pos.getZ(i + c);
      let best = 0, bd = Infinity;
      for (let k = 0; k < 3; k++) {
        const v = texIndex.idx(twin, k);
        const d = (texIndex.pos.getX(v) - px) ** 2 + (texIndex.pos.getY(v) - py) ** 2 + (texIndex.pos.getZ(v) - pz) ** 2;
        if (d < bd) { bd = d; best = v; }
      }
      uv[(i + c) * 2] = texIndex.uv.getX(best); uv[(i + c) * 2 + 1] = texIndex.uv.getY(best);
      nor[(i + c) * 3] = texIndex.nor.getX(best); nor[(i + c) * 3 + 1] = texIndex.nor.getY(best); nor[(i + c) * 3 + 2] = texIndex.nor.getZ(best);
    }
  }
  g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  g.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
  return { geometry: g, miss, total: n / 3 };
}

const triCount = g => (g.index ? g.index.count : g.attributes.position.count) / 3;

export function partName(guess, i, all) {
  if (!guess) return `Parça ${String(i + 1).padStart(2, '0')}`;
  const base = GUESS_TR[guess] || guess;
  const same = all.filter(g => (GUESS_TR[g] || g) === base).length;
  if (same < 2) return base;
  const nth = all.slice(0, i + 1).filter(g => (GUESS_TR[g] || g) === base).length;
  return `${base} ${nth}`;
}

export class Viewer {
  constructor(container, opts = {}) {
    this.o = Object.assign({
      clay: 0xd3c9b8, glow: 0xe08a12, hi: 0xffffff, partS: 0.5, partL: 0.62, partHue: 0.08,
      shadow: 0.16, exposure: 1.02, env: 0.75, key: 2.2, fill: 0.6, rim: 1.2, fov: 28, autoRotate: 1.4, frameY: -0.1,
    }, opts);
    this.el = container;
    const r = this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    r.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    r.outputColorSpace = THREE.SRGBColorSpace;
    r.toneMapping = THREE.NeutralToneMapping; r.toneMappingExposure = this.o.exposure;
    r.shadowMap.enabled = true; r.shadowMap.type = THREE.PCFShadowMap;
    container.appendChild(r.domElement);
    Object.assign(r.domElement.style, { display: 'block', width: '100%', height: '100%', outline: 'none' });

    const scene = this.scene = new THREE.Scene();
    const pm = new THREE.PMREMGenerator(r);
    scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environmentIntensity = this.o.env;

    this.camera = new THREE.PerspectiveCamera(this.o.fov, 1, 0.05, 100);
    this.camera.position.set(0, 1.1, 6.5);
    const c = this.controls = new OrbitControls(this.camera, r.domElement);
    c.enableDamping = true; c.dampingFactor = 0.08; c.enablePan = false;
    c.autoRotate = true; c.autoRotateSpeed = this.o.autoRotate; c.minDistance = 2.2; c.maxDistance = 14;
    c.minPolarAngle = 0.25; c.maxPolarAngle = Math.PI * 0.56;

    scene.add(new THREE.HemisphereLight(0xffffff, 0x6b5f50, this.o.fill));
    const key = new THREE.DirectionalLight(0xfff4e6, this.o.key);
    key.position.set(2.6, 4.5, 3.2);
    key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0004; key.shadow.normalBias = 0.02;
    Object.assign(key.shadow.camera, { left: -2.5, right: 2.5, top: 2.5, bottom: -2.5, near: 0.5, far: 14 });
    key.shadow.radius = 6;
    scene.add(key);
    const rim = new THREE.DirectionalLight(0xdfe8ff, this.o.rim); rim.position.set(-3, 2.5, -3.5); scene.add(rim);

    this.floor = new THREE.Mesh(new THREE.PlaneGeometry(14, 14), new THREE.ShadowMaterial({ opacity: this.o.shadow }));
    this.floor.rotation.x = -Math.PI / 2; this.floor.receiveShadow = true; scene.add(this.floor);

    this.root = new THREE.Group(); scene.add(this.root);
    this.parts = []; this.whole = null; this.mode = 'clay'; this.explodeT = 0; this.texAmt = 0; this.partAmt = 0;
    this.texT = 0; this.partT = 0; this.build = null; this.intro = null; this.listeners = {};
    this.camDist = 6.5; this.distMul = 1; this.hiIdx = -1; this.map = null; this.hasParts = false;
    this.partsTextured = false; this.loadToken = 0;

    this._resize = () => {
      const w = container.clientWidth || 1, h = container.clientHeight || 1;
      r.setSize(w, h, false); this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
    };
    new ResizeObserver(this._resize).observe(container); this._resize();

    // click to pick a part (ignored if the pointer moved, i.e. an orbit drag)
    let down = null;
    r.domElement.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
    r.domElement.addEventListener('pointerup', e => {
      if (!this.hasParts || !down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
      const rect = r.domElement.getBoundingClientRect();
      const p = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
      const rc = new THREE.Raycaster(); rc.setFromCamera(p, this.camera);
      const hit = rc.intersectObjects(this.parts.filter(x => x.mesh.visible).map(x => x.mesh))[0];
      this.emit('pick', hit ? this.parts.findIndex(x => x.mesh === hit.object) : -1);
    });

    this.clock = new THREE.Timer();
    const loop = () => { requestAnimationFrame(loop); this.clock.update(); this.step(Math.min(0.05, this.clock.getDelta())); };
    loop();
  }

  on(ev, fn) { (this.listeners[ev] ||= []).push(fn); }
  emit(ev, v) { (this.listeners[ev] || []).forEach(f => f(v)); }

  clear() {
    this.loadToken++;
    for (const o of [...this.root.children]) { o.geometry?.dispose(); o.material?.dispose(); }
    this.root.clear(); this.parts = []; this.whole = null; this.map = null; this.hasParts = false;
    this.partsTextured = false; this.intro = null; this.build = null; this.framedKey = null;
    this.emit('load', this.parts);
  }

  // model: { shape, textured, parts: [{url, guess, faces}] } (urls; any may be missing). Resolves with the parts.
  // frameKey: keep the camera when reloading the same job (shape -> textured -> parts arrive one by one).
  async loadModel(model, { intro = null, frameKey = null } = {}) {
    const token = ++this.loadToken;
    const baseUrl = model.textured || model.shape;
    const [base, ...partGltfs] = await Promise.all([
      baseUrl ? loadGLB(baseUrl) : Promise.resolve(null),
      ...(model.parts || []).map(p => loadGLB(p.url)),
    ]);
    if (token !== this.loadToken) return this.parts;   // a newer load started meanwhile

    let baseMesh = null;
    if (base) baseMesh = bakeMeshes(base);
    const map = model.textured && baseMesh?.map ? baseMesh.map : null;
    if (map) { map.colorSpace = THREE.SRGBColorSpace; map.anisotropy = 8; }

    for (const o of [...this.root.children]) { o.geometry?.dispose(); o.material?.dispose(); }
    this.root.clear(); this.parts = []; this.whole = null; this.map = map;

    const pieces = [];  // {geometry, map, guess}
    let miss = 0, total = 0;
    if (partGltfs.length) {
      const texIndex = map && baseMesh.geometry.attributes.uv ? buildTexIndex(baseMesh.geometry) : null;
      let ownMaps = 0;
      partGltfs.forEach((g, i) => {
        let { geometry, map: own } = bakeMeshes(g);
        geometry.deleteAttribute('color');
        if (own && geometry.attributes.uv) { own.colorSpace = THREE.SRGBColorSpace; ownMaps++; }
        else if (texIndex) {
          const r = transferUV(geometry, texIndex);
          miss += r.miss; total += r.total;
          // new geometry (X-Part's closed parts) has no textured twin: keep it, with its own normals, untextured
          if (r.miss > r.total / 2) { own = null; geometry.computeVertexNormals(); } else { geometry = r.geometry; own = map; }
        }
        else { own = null; geometry.computeVertexNormals(); }
        pieces.push({ geometry, map: own, guess: model.parts[i].guess, faces: model.parts[i].faces, renk: model.parts[i].renk });
      });
      // parts carry the texture when they have their own maps or nearly every face found its textured twin
      this.partsTextured = ownMaps === partGltfs.length || (!!texIndex && miss / Math.max(1, total) < 0.02);
      if (!this.partsTextured && map) {
        // keep the textured mesh whole for "Dokulu"; the parts stay clay / coloured
        pieces.forEach(p => { p.map = null; });
        this.whole = this.addMesh(baseMesh.geometry, map, new THREE.Color(this.o.clay));
      }
      this.hasParts = true;
    } else if (baseMesh) {
      if (!baseMesh.geometry.attributes.normal) baseMesh.geometry.computeVertexNormals();
      pieces.push({ geometry: baseMesh.geometry, map, guess: null, faces: null });
      this.hasParts = false; this.partsTextured = !!map;
    }
    if (miss) console.warn('UV aktarımı: eşi bulunmayan üçgen', miss, '/', total);

    // part colours: the server's (parts.json "renk", same as its previews), else a golden-ratio walk
    const gold = goldenColors(pieces.length, this.o.partS, this.o.partL, this.o.partHue);
    const cols = pieces.map((p, i) => (p.renk && /^#[0-9a-f]{6}$/i.test(p.renk) ? new THREE.Color(p.renk) : gold[i]));
    const box = new THREE.Box3();
    const guesses = pieces.map(p => p.guess);
    pieces.forEach((p, i) => {
      p.geometry.computeBoundingBox(); box.union(p.geometry.boundingBox);
      const mesh = this.addMesh(p.geometry, p.map, cols[i]);
      const c = new THREE.Vector3(); p.geometry.boundingBox.getCenter(c);
      this.parts.push({ i, mesh, name: this.hasParts ? partName(p.guess, i, guesses) : 'Model',
        tris: p.faces || triCount(p.geometry), color: '#' + cols[i].getHexString(), centroid: c,
        off: new THREE.Vector3(), vel: new THREE.Vector3(), k: 70 + ((i * 37) % 40), visible: true, partAmt: 0 });
    });
    if (this.whole) { this.whole.geometry.computeBoundingBox(); box.union(this.whole.geometry.boundingBox); }

    // normalise: height 2, feet on y = 0, centred on x/z
    const size = box.getSize(new THREE.Vector3()), center = box.getCenter(new THREE.Vector3());
    const s = 2 / Math.max(1e-6, size.y);
    this.scale = s; this.raw = { min: box.min.y, max: box.max.y, h: size.y };
    this.root.scale.setScalar(s);
    this.root.position.set(-center.x * s, -box.min.y * s, -center.z * s);
    for (const p of this.parts) {
      const d = p.centroid.clone().sub(center);
      const dn = d.lengthSq() > 1e-8 ? d.clone().normalize() : new THREE.Vector3(0, 1, 0);
      p.dir = d.multiplyScalar(0.8).add(dn.multiplyScalar(size.y * 0.07)); p.dir.y *= 0.75;
    }
    this.bounds = { w: size.x * s, h: 2, d: size.z * s };
    const radius = Math.max(1.05, Math.hypot(this.bounds.w, 2, this.bounds.d) / 2);
    this.camDist = radius / Math.tan(THREE.MathUtils.degToRad(this.o.fov / 2)) * 1.05;
    if (!frameKey || frameKey !== this.framedKey) {
      this.controls.target.set(0, 1 + this.o.frameY, 0);
      const az = this.controls.getAzimuthalAngle();
      this.camera.position.set(Math.sin(az) * this.camDist, 1.25, Math.cos(az) * this.camDist);
      this.distMul = 1; this.controls.update();
    }
    this.framedKey = frameKey;
    this.hiIdx = -1;
    this.setMode(this.mode, true);
    this.setExplode(0, true);
    if (intro) this.playIntro(intro);
    this.emit('load', this.parts);
    return this.parts;
  }

  addMesh(geometry, map, color) {
    const mesh = new THREE.Mesh(geometry, makeMaterial(map, this.o.clay, color, this.o.glow, this.o.hi));
    mesh.castShadow = true; mesh.receiveShadow = true;
    mesh.customDepthMaterial = makeDepthMaterial(mesh.material.userData.u);
    this.root.add(mesh);
    return mesh;
  }

  get canTexture() { return !!this.map; }
  // explode moves the parts; with a whole textured mesh shown instead, there is nothing to move
  get canExplode() { return this.hasParts && !(this.mode === 'textured' && this.whole); }

  setMode(mode, instant) {
    if (mode === 'textured' && !this.map) mode = 'clay';
    if (mode === 'parts' && !this.hasParts) mode = this.map ? 'textured' : 'clay';
    this.mode = mode;
    this.texT = mode === 'textured' ? 1 : 0; this.partT = mode === 'parts' ? 1 : 0;
    if (instant) { this.texAmt = this.texT; this.partAmt = this.partT; }
    const wholeOn = !!this.whole && mode === 'textured';
    if (this.whole) this.whole.visible = wholeOn;
    for (const p of this.parts) p.mesh.visible = p.visible && !wholeOn;
    if (wholeOn) this.setExplode(0);
  }
  setExplode(v, instant) {
    this.explodeT = v;
    if (instant) for (const p of this.parts) { p.off.copy(p.dir).multiplyScalar(v); p.vel.set(0, 0, 0); }
  }
  setVisible(i, v) {
    this.parts[i].visible = v;
    this.parts[i].mesh.visible = v && !(this.whole && this.whole.visible);
  }
  setTurntable(v) { this.controls.autoRotate = v; }
  highlight(i) { this.hiIdx = i; }

  // Arrival animations, played once when a step's output lands: the shape rises with a glowing line, the texture
  // sweeps down, the parts light up bottom-up then settle.
  playIntro(kind) {
    const dur = { shape: 1.6, tex: 1.5, parts: 2.6 }[kind];
    if (!dur) return;
    this.intro = { kind, t: 0, dur };
  }
  introBuild(dt) {
    const it = this.intro; if (!it) return null;
    it.t += dt;
    const p = Math.min(1, it.t / it.dur);
    if (p >= 1) { this.intro = null; return null; }
    const b = { reveal: 2, sweep: -1, sweepOn: 0, seg: 0, explode: null };
    const e = 1 - Math.pow(1 - p, 2);
    if (it.kind === 'shape') b.reveal = e;
    if (it.kind === 'tex') { b.sweep = 1 - e; b.sweepOn = 1; }
    if (it.kind === 'parts') { b.seg = Math.min(1.01, p / 0.55); b.explode = p < 0.45 ? 0 : p < 0.8 ? 0.3 : 0; }
    return b;
  }

  step(dt) {
    const k = 1 - Math.exp(-dt * 9);
    const b = this.introBuild(dt);
    this.texAmt += (this.texT - this.texAmt) * k;
    this.partAmt += (this.partT - this.partAmt) * k;
    const raw = this.raw || { min: 0, max: 1, h: 1 };
    const explodeT = b && b.explode != null ? b.explode : this.explodeT;
    const meshes = this.whole ? [...this.parts, { mesh: this.whole, whole: true }] : this.parts;
    for (const p of meshes) {
      const u = p.mesh.material.userData.u;
      let pa = this.partAmt;
      if (!p.whole) {
        // springs (slightly under-damped), stiffness varies per part so they don't move in lockstep
        const target = p.dir.clone().multiplyScalar(explodeT);
        const acc = target.sub(p.off).multiplyScalar(p.k).sub(p.vel.clone().multiplyScalar(2 * Math.sqrt(p.k) * 0.72));
        p.vel.addScaledVector(acc, dt); p.off.addScaledVector(p.vel, dt);
        p.mesh.position.copy(p.off);
        if (b && b.seg > 0) {
          const order = (p.centroid.y - raw.min) / raw.h;
          pa = b.seg > 1 ? 1 : THREE.MathUtils.smoothstep(b.seg * 1.15 - order, 0, 0.06);
        }
        p.partAmt += (pa - p.partAmt) * (b ? 1 : k); pa = p.partAmt;
      }
      u.uPartAmt.value = p.whole ? 0 : pa;
      u.uTexAmt.value = this.texAmt;
      u.uReveal.value = b && b.reveal < 2 ? raw.min + b.reveal * raw.h * 1.02 : 1e5;
      u.uSweep.value = b && b.sweepOn ? raw.min + b.sweep * raw.h : -1e5;
      u.uSweepOn.value = b ? b.sweepOn : 0;
      u.uBand.value = raw.h * 0.012;
      const hiT = !p.whole && this.hiIdx === p.i ? 0.35 : 0;
      u.uHi.value += (hiT - u.uHi.value) * k;
      u.uDim.value += ((this.hiIdx >= 0 && !p.whole && this.hiIdx !== p.i ? 0.35 : 0) - u.uDim.value) * k;
    }
    // camera eases out while parts fly apart
    const want = 1 + Math.max(0, explodeT) * 0.5, prev = this.distMul;
    this.distMul += (want - this.distMul) * k * 0.6;
    const off = this.camera.position.clone().sub(this.controls.target);
    off.multiplyScalar(this.distMul / prev);
    this.camera.position.copy(this.controls.target).add(off);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  resetView() {
    const d = this.camDist * this.distMul;
    this.camera.position.set(0, 1.25, d);
  }

  // Off-screen still of the loaded mesh in a given look (strip thumbnails for steps 02-05).
  snapshot({ mode = 'clay', explode = 0, yaw = 18, w = 240, h = 300 } = {}) {
    if (!this.parts.length) return null;
    const r = this._snapRenderer ||= (() => {
      const x = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
      x.outputColorSpace = THREE.SRGBColorSpace; x.toneMapping = THREE.NeutralToneMapping;
      x.toneMappingExposure = this.o.exposure; return x;
    })();
    r.setPixelRatio(1); r.setSize(w, h, false);
    const cam = new THREE.PerspectiveCamera(this.o.fov, w / h, 0.05, 100);
    const d = this.camDist * (1 + explode * 0.5) * 0.98, a = THREE.MathUtils.degToRad(yaw);
    cam.position.set(Math.sin(a) * d, 1.15, Math.cos(a) * d); cam.lookAt(0, 1, 0);
    const useWhole = !!this.whole && mode === 'textured';
    const meshes = [...this.parts.map(p => p.mesh), ...(this.whole ? [this.whole] : [])];
    const save = meshes.map(m => ({ m, pos: m.position.clone(), vis: m.visible,
      u: Object.fromEntries(Object.entries(m.material.userData.u).map(([k, v]) => [k, v.value?.clone ? v.value.clone() : v.value])) }));
    this.floor.visible = false;
    for (const p of this.parts) {
      p.mesh.position.copy(p.dir).multiplyScalar(explode);
      p.mesh.visible = !useWhole;
    }
    if (this.whole) this.whole.visible = useWhole;
    for (const m of meshes) {
      const u = m.material.userData.u;
      u.uTexAmt.value = mode === 'textured' ? 1 : 0; u.uPartAmt.value = mode === 'parts' && m !== this.whole ? 1 : 0;
      u.uReveal.value = 1e5; u.uSweep.value = -1e5; u.uSweepOn.value = 0; u.uHi.value = 0; u.uDim.value = 0;
    }
    r.render(this.scene, cam);
    const url = r.domElement.toDataURL('image/png');
    for (const sv of save) {
      sv.m.position.copy(sv.pos); sv.m.visible = sv.vis;
      for (const [k, v] of Object.entries(sv.u)) { const t = sv.m.material.userData.u[k]; if (t.value?.copy) t.value.copy(v); else t.value = v; }
    }
    this.floor.visible = true;
    return url;
  }
}
