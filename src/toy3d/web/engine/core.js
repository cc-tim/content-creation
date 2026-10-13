// toy3d core (E11): math, seeded canvases, mesh helpers and the look's materials, ported verbatim
// from the frozen r7-3d snapshot's scene.js (look A only). Every colour and material value comes
// from the bank (P2-R9); geometry stays here. Seeded throughout: same bank, same world.
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

export { THREE };
export const V3 = (x, y, z) => new THREE.Vector3(x, y, z);
export const D2R = THREE.MathUtils.degToRad;
export const lerp = THREE.MathUtils.lerp;
export const clamp01 = (x) => Math.min(1, Math.max(0, x));
export const sstep = (a, b, x) => { const t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); };
export function mulberry32(a) {
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
// Identities, not picks: a textured material's untinted base and an emissive screen's black body.
export const UNTINTED = new THREE.Color(1, 1, 1);
export const BLACK = new THREE.Color(0, 0, 0);

// A bank colour ('#rrggbb') at alpha `a`, as a canvas colour string.
export function rgba(hex, a) {
  if (!/^#[0-9a-fA-F]{6}$/.test(hex)) throw new Error(`toy3d: ${hex} is not a #rrggbb colour (one with alpha comes from the code)`);
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

// A palette's every value must be a colour (or a list of them): THREE.Color would only warn.
const COLOUR = /^#[0-9a-fA-F]{6}$|^rgba?\(\s*[0-9.]+(\s*,\s*[0-9.]+){2,3}\s*\)$/;
export function checkPalette(pal, where) {
  for (const [k, v] of Object.entries(pal)) {
    for (const c of Array.isArray(v) ? v : [v]) {
      if (typeof c !== 'string' || !COLOUR.test(c)) throw new Error(`toy3d bank: ${where}.${k}: not a colour '${c}'`);
    }
  }
  return pal;
}

// ---- strict bank reads: a key the bank lacks throws; a key the engine never reads is reported ----
export function strict(obj, where, seen = new Set()) {
  const leaves = [];
  const walk = (o, path) => {
    for (const [k, v] of Object.entries(o)) {
      const p = `${path}.${k}`;
      if (v && typeof v === 'object' && !Array.isArray(v)) walk(v, p); else leaves.push(p);
    }
  };
  walk(obj, where);
  const wrap = (o, path) => new Proxy(o, {
    get(t, k) {
      if (typeof k === 'symbol' || k === 'toJSON' || k === 'then') return t[k];
      if (!(k in t)) throw new Error(`toy3d bank: ${path}.${String(k)} is missing`);
      const v = t[k], p = `${path}.${String(k)}`;
      if (v && typeof v === 'object' && !Array.isArray(v)) return wrap(v, p);
      seen.add(p);
      return v;
    },
  });
  return { value: wrap(obj, where), unread: () => leaves.filter((p) => !seen.has(p)) };
}

// ---- textures (all seeded canvases) -------------------------------------------------------
export function canvasTex(w, h, draw, { repeat = [1, 1], srgb = true } = {}) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(...repeat);
  t.anisotropy = 8;
  return t;
}

// ---- materials: the look's vinyl (soft goods, characters) and painted wood (furniture, house) ----
export function materials(style, pal) {
  const S = style.materials.soft, Pm = style.materials.prop;
  const grainTex = canvasTex(512, 512, (g, w, h) => {
    const r = mulberry32(31);
    g.fillStyle = pal.grain_ground; g.fillRect(0, 0, w, h);
    const dark = pal.grain_dark, light = pal.grain_light;
    for (let i = 0; i < 70; i++) {
      const y0 = r() * h, a = 0.05 + r() * 0.08, isDark = r() < 0.7;
      g.strokeStyle = isDark ? rgba(dark, a) : rgba(light, a);
      g.lineWidth = 1 + r() * 3;
      g.beginPath();
      for (let x = 0; x <= w; x += 16) g.lineTo(x, y0 + Math.sin(x * 0.012 + i) * 6 + Math.sin(x * 0.041 + i * 2) * 2);
      g.stroke();
    }
  });
  function soft(color, o = {}) { // characters + soft goods
    const c = new THREE.Color(color);
    return new THREE.MeshPhysicalMaterial({ color: c, roughness: S.roughness, clearcoat: S.clearcoat, clearcoatRoughness: S.clearcoat_roughness,
      sheen: S.sheen, sheenRoughness: S.sheen_roughness, sheenColor: c.clone().lerp(UNTINTED, S.sheen_mix), ...o });
  }
  function prop(color, o = {}) { // furniture, house
    return new THREE.MeshStandardMaterial({ color, roughness: Pm.roughness, ...o });
  }
  const wood = (color) => prop(color, { map: grainTex });
  return { soft, prop, wood, faceRoughness: style.materials.face.roughness };
}

// ---- mesh helpers -------------------------------------------------------------------------
export function mk(geo, mat, parent, pos, opts = {}) {
  const m = new THREE.Mesh(geo, mat);
  if (pos) m.position.set(...pos);
  m.castShadow = opts.cast ?? true;
  m.receiveShadow = opts.recv ?? true;
  if (parent) parent.add(m);
  return m;
}
export const rbox = (w, h, d, r, mat, parent, pos) => mk(new RoundedBoxGeometry(w, h, d, 4, r), mat, parent, pos);
export const sph = (r, mat, parent, pos, scale) => { const m = mk(new THREE.SphereGeometry(r, 32, 24), mat, parent, pos); if (scale) m.scale.set(...scale); return m; };
export const lathe = (pts, mat, parent, pos, segs = 48, phi0 = 0, phiL = Math.PI * 2) =>
  mk(new THREE.LatheGeometry(pts.map(([x, y]) => new THREE.Vector2(x, y)), segs, phi0, phiL), mat, parent, pos);
export function tube(points, r, mat, parent) {
  return mk(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points.map((p) => V3(...p))), 32, r, 10, false), mat, parent);
}
export function limb(l1, l2, r1, r2, m1, m2, end) {
  const j1 = new THREE.Group();
  const g1 = new THREE.CapsuleGeometry(r1, l1, 8, 20); g1.translate(0, -l1 / 2, 0); mk(g1, m1, j1);
  const j2 = new THREE.Group(); j2.position.y = -l1; j1.add(j2);
  const g2 = new THREE.CapsuleGeometry(r2, l2, 8, 20); g2.translate(0, -l2 / 2, 0); mk(g2, m2, j2);
  const e = new THREE.Group(); e.position.y = -l2; j2.add(e);
  if (end) e.add(end);
  return { j1, j2, e };
}
// box with world-scaled UVs (wallpaper/plank textures tile at a fixed physical size)
export function worldBox(x0, x1, y0, y1, z0, z1, mats, tile, parent) {
  const g = new THREE.BoxGeometry(x1 - x0, y1 - y0, z1 - z0);
  g.translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
  const p = g.attributes.position, n = g.attributes.normal, uv = g.attributes.uv;
  for (let i = 0; i < p.count; i++) {
    const ax = Math.abs(n.getX(i)), az = Math.abs(n.getZ(i));
    if (az > 0.5) uv.setXY(i, p.getX(i) / tile, p.getY(i) / tile);
    else if (ax > 0.5) uv.setXY(i, p.getZ(i) / tile, p.getY(i) / tile);
    else uv.setXY(i, p.getX(i) / tile, p.getZ(i) / tile);
  }
  return mk(g, mats, parent);
}
// orient a surface detail in its parent's space: local z = outward normal n, local y ~ upHint, then spin about n
export function orient(obj, n, upHint, spin = 0) {
  const z = n.clone().normalize(), y = upHint.clone().addScaledVector(z, -upHint.dot(z)).normalize(), x = new THREE.Vector3().crossVectors(y, z);
  obj.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z));
  obj.rotateZ(spin);
}
// computeVertexNormals leaves zero normals at degenerate pole/axis vertices -> NaN in lighting; point them outward
export function fixNormals(g) {
  g.computeBoundingBox(); const ctr = g.boundingBox.getCenter(new THREE.Vector3());
  const p = g.attributes.position, n = g.attributes.normal, v = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) if (Math.hypot(n.getX(i), n.getY(i), n.getZ(i)) < 1e-6) {
    v.set(p.getX(i), p.getY(i), p.getZ(i)).sub(ctr).normalize(); n.setXYZ(i, v.x, v.y, v.z);
  }
  return g;
}
// ellipsoid with the scale baked in (fur length stays in world units); optional deform; seam turned to the back
export function ellipsoid(rx, ry, rz, deform, ws = 72, hs = 48) {
  const g = new THREE.SphereGeometry(1, ws, hs);
  g.rotateY(-Math.PI / 2);
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    let x = p.getX(i) * rx, y = p.getY(i) * ry, z = p.getZ(i) * rz;
    if (deform) [x, y, z] = deform(x, y, z);
    p.setXYZ(i, x, y, z);
  }
  g.computeVertexNormals();
  return fixNormals(g);
}
// generic loft: rings of equal length around an axis -> closed tube (wrap-around indices, outward winding)
export function loftGeo(rings) {
  const N = rings[0].length, pos = [], idx = [];
  for (const r of rings) for (const p of r) pos.push(p.x, p.y, p.z);
  for (let j = 0; j < rings.length - 1; j++) for (let i = 0; i < N; i++) {
    const a = j * N + i, b = j * N + (i + 1) % N, c = a + N, d = b + N;
    idx.push(a, b, c, b, d, c);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx);
  g.computeVertexNormals();
  return fixNormals(g);
}
export const sexp = (c, p) => Math.sign(c) * Math.pow(Math.abs(c), 2 / p); // superellipse
export function catmull(rows, per) { // uniform Catmull-Rom through table rows (all columns)
  const out = [], n = rows.length;
  for (let i = 0; i < n - 1; i++) for (let k = 0; k < per; k++) {
    const t = k / per, P = (j) => rows[Math.min(n - 1, Math.max(0, j))];
    const p0 = P(i - 1), p1 = P(i), p2 = P(i + 1), p3 = P(i + 2);
    out.push(p1.map((_, c) => 0.5 * (2 * p1[c] + (-p0[c] + p2[c]) * t + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * t * t + (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * t * t * t)));
  }
  out.push(rows[n - 1]);
  return out;
}
