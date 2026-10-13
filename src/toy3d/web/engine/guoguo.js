// toy3d GuoGuo (E11): Tim's king-penguin hand-puppet plush, frozen at v7 (Tim approved, 2026-10-13),
// ported verbatim from the snapshot (scene.js shell fur, makeGuo). The long-pile shell fur is
// deterministic (a per-strand hash of the rest position). Two builds: seated (rooms) and standing
// (design views). Colours, the photo traces and the design-pick tables come from the bank
// (characters/guoguo.yaml, guo_trace.json). Rig nodes: root, body, head, flippers, eyes.
import {
  THREE, V3, D2R, lerp, sstep, mk, sph, orient, ellipsoid, fixNormals, loftGeo, sexp, catmull,
} from './core.js';

// ---- shell fur (deterministic): offset shells; a per-strand hash of the rest position decides strand height ----
const FUR_HOOK = function (sh) {
  const u = this.userData;
  Object.assign(sh.uniforms, { uShell: { value: u.k }, uFurLen: u.len, uFurPush: u.push, uDensity: { value: u.density }, uTwist: u.twist, uTwistY: u.twistY });
  sh.vertexShader = 'attribute float furScale; uniform float uShell; uniform float uFurLen; uniform vec3 uFurPush; uniform float uTwist; uniform vec2 uTwistY; varying vec3 vFurPos;\n' + sh.vertexShader
    .replace('#include <beginnormal_vertex>', '#include <beginnormal_vertex>\n  float twA = uTwist * smoothstep(uTwistY.x, uTwistY.y, position.y), twC = cos(twA), twS = sin(twA);\n' +
      '  objectNormal = vec3(twC * objectNormal.x + twS * objectNormal.z, objectNormal.y, -twS * objectNormal.x + twC * objectNormal.z);')
    .replace('#include <begin_vertex>', '#include <begin_vertex>\n  vFurPos = position;\n' +
      '  transformed = vec3(twC * position.x + twS * position.z, position.y, -twS * position.x + twC * position.z); // head turn (same as rotation.y)\n' +
      '  transformed += (objectNormal * uFurLen * uShell + uFurPush * uFurLen * uShell * uShell) * furScale;');
  sh.fragmentShader = 'uniform float uShell; uniform float uDensity; varying vec3 vFurPos;\n' +
    'float furHash(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }\n' +
    sh.fragmentShader.replace('#include <clipping_planes_fragment>', `#include <clipping_planes_fragment>
  if (uShell > 0.0) {
    vec3 c = vFurPos * uDensity; vec3 f = fract(c) - 0.5;
    float h = 0.25 + 0.75 * furHash(floor(c));               // strand height
    if (h < uShell || length(f) > 0.8 * (1.0 - 0.75 * uShell)) discard;   // strands taper to the tip
  }`).replace('#include <color_fragment>', '#include <color_fragment>\n  diffuseColor.rgb *= mix(0.8, 1.04, uShell);');
};

function inPoly(u, v, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [ui, vi] = poly[i], [uj, vj] = poly[j];
    if ((vi > v) !== (vj > v) && u < ((uj - ui) * (v - vi)) / (vj - vi) + ui) inside = !inside;
  }
  return inside;
}

export function buildGuoGuo(ch, trace, seated) {
  const Pal = ch.palette, Q = ch.params;
  const GG = { white: new THREE.Color(Pal.white), grey: new THREE.Color(Pal.grey), black: new THREE.Color(Pal.black),
    yellow: new THREE.Color(Pal.yellow), orange: new THREE.Color(Pal.orange) };
  const F = Q.fur;
  const parts = [];
  const NO_TWIST = { value: 0 }, NO_TWIST_Y = { value: new THREE.Vector2(10, 11) };
  function furPart(geo, colorFn, { len = F.len, shells = F.shells, density = F.density, twist = NO_TWIST, twistY = NO_TWIST_Y } = {}) {
    const p = geo.attributes.position, n = geo.attributes.normal, col = new Float32Array(p.count * 3), fs = new Float32Array(p.count), c = new THREE.Color();
    for (let i = 0; i < p.count; i++) {
      const k = colorFn(c, p.getX(i), p.getY(i), p.getZ(i), n.getX(i), n.getY(i), n.getZ(i)); // optional return: fur length scale
      col.set([c.r, c.g, c.b], i * 3); fs[i] = typeof k === 'number' ? k : 1; // arrow colorFns that return the Color mean 'no scale'
    }
    geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    geo.setAttribute('furScale', new THREE.BufferAttribute(fs, 1));
    const g = new THREE.Group();
    g.userData.len = { value: len }; g.userData.push = { value: new THREE.Vector3() };
    for (let i = 0; i <= shells; i++) {
      const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: F.roughness, metalness: F.metalness });
      Object.assign(mat.userData, { k: i / shells, len: g.userData.len, push: g.userData.push, density, twist, twistY });
      mat.onBeforeCompile = FUR_HOOK;
      const m = new THREE.Mesh(geo, mat);
      m.castShadow = i === 0; m.receiveShadow = true;
      if (i) m.userData.noAO = true;
      g.add(m);
    }
    parts.push(g);
    return g;
  }

  // photo -> model mapping for the reference traces (guo_trace.json): model u (m, image-right) / v (m, up from the feet)
  const GUO_MAP = Q.trace_map;
  const tracePolys = (view, key) => trace[view][key].map((poly) => poly.map(([x, y]) => {
    const m = GUO_MAP[view]; return [(x - m.x0) * m.s, (m.y0 - y) * m.s];
  }));
  // project a model point (mirrored onto the photographed side) into a view's image plane; null if facing away
  function projView(view, x, y, z, nx, nz) {
    const yw = D2R(GUO_MAP[view].yaw), sx = view === 'side' ? 1 : 1, X = view === 'side' ? Math.abs(x) : x;
    const facing = (view === 'side' ? Math.abs(nx) * (Math.sign(nx) === Math.sign(x || 1) ? 1 : -1) : nx) * Math.sin(yw) + nz * Math.cos(yw);
    return facing > 0.12 ? [sx * (X * Math.cos(yw) - z * Math.sin(yw)), y] : null;
  }
  const FLIPPER_TOP = Q.flipper_top; // the top edge of the flippers where they attach (v7: the head's black ends here)
  const BIB_LIFT = FLIPPER_TOP - Q.bib_top; // v7: the traced V-bib starts at the flipper-top line
  const [EAR_SIDE] = tracePolys('side', 'orange'), YELLOW_FRONT = tracePolys('front', 'yellow').map((poly) => poly.map(([u, v]) => [u, v + BIB_LIFT]));
  const EAR = Q.ear; // round-oval patch low on the head side, reaching forward enough to read from the front
  const paintTraced = (c, x, y, z, nx, nz) => {
    const ps = projView('side', x, y, z, nx, nz), pf = projView('front', x, y, z, nx, nz);
    if (ps && inPoly(ps[0], ps[1], EAR_SIDE)) c.copy(GG.orange);
    const th = Math.abs(Math.atan2(x, z)) / D2R(1), de = ((th - EAR.th) / EAR.dth) ** 2 + ((y - EAR.y + 0.0009 * (th - EAR.th)) / EAR.dy) ** 2;
    c.lerp(GG.orange, 1 - sstep(0.85, 1.0, de));
    if (pf && YELLOW_FRONT.some((poly) => inPoly(pf[0], pf[1], poly))) c.copy(GG.yellow);
  };
  const GUO_PROF = Q.profile, GUO_LEG = Q.leg, GUO_EYE = Q.eye;
  function guoSurf(th, y, prof) { // point on the body loft at angle th (deg, 0 = front, +x side positive) and height y
    let r = prof[0];
    for (let i = 1; i < prof.length; i++) if (prof[i][0] >= y) { const q = prof[i - 1], w = (y - q[0]) / (prof[i][0] - q[0]); r = q.map((v, c) => v + (prof[i][c] - v) * w); break; }
    const [, a, f, b] = r, c = Math.cos(D2R(th)), sn = Math.sin(D2R(th)), p = lerp(2.5, 2.15, sstep(0.44, 0.52, y));
    const zc = (f + b) / 2 * sstep(0.64, 0.664, y);
    return V3(a * sexp(sn, p), y, zc + (c >= 0 ? f - zc : zc - b) * sexp(c, p));
  }
  // seated (v7, room frames): a plush settled on a shelf -> wide slumped base, legs forward along the surface, tapering to the head
  const SIT_DROP = Q.sit_drop;
  function sitBody(x, y, z) { // standing body-loft point -> seated: lower body spreads + settles, flat base; head/chest just drop
    const k = sstep(0.46, 0.14, y), k2 = k * k;
    return [x * (1 + 0.1 * k + 0.2 * k2), Math.max(0.012, y - SIT_DROP - 0.05 * k), z > 0 ? z * (1 + 0.14 * k) : z * (1 + 0.38 * k)];
  }
  function sitLeg(s) { // standing leg/foot point -> seated: swing forward ~80 deg about the hip, splay out a little, drop
    const py = 0.17, pz = 0.02, px = s * 0.106, a = D2R(-80), ca = Math.cos(a), sa = Math.sin(a), sp = s * 0.18, cs = Math.cos(sp), ss = Math.sin(sp);
    return (x, y, z) => {
      const dy = y - py, dz = z - pz, y1 = py + dy * ca - dz * sa, z1 = pz + dy * sa + dz * ca, dx = x - px, dz1 = z1 - pz;
      return [px + dx * cs + dz1 * ss, y1 - SIT_DROP, pz - dx * ss + dz1 * cs];
    };
  }
  function bake(geo, fn) { // remap positions in place (after the colours were painted on the standing shape), refresh normals
    const p = geo.attributes.position;
    for (let i = 0; i < p.count; i++) p.setXYZ(i, ...fn(p.getX(i), p.getY(i), p.getZ(i)));
    geo.computeVertexNormals(); fixNormals(geo); geo.computeBoundingBox(); geo.computeBoundingSphere();
    return geo;
  }

  const D = seated ? SIT_DROP : 0;
  const root = new THREE.Group(), body = new THREE.Group();
  root.add(body);
  const head = new THREE.Group(); body.add(head); // rigid head parts (beak, eyes); the head fur twists with it in the shader
  const twist = { value: 0 }, twistY = { value: new THREE.Vector2(0.46 - D, 0.53 - D) };
  const prof = catmull(GUO_PROF, 6), NR = 144;
  const rings = prof.map(([y]) => Array.from({ length: NR }, (_, i) => guoSurf((i / NR) * 360 - 180, y, prof)));
  const bg = loftGeo(rings);
  const eyeP = [-1, 1].map((s) => guoSurf(s * GUO_EYE.th, GUO_EYE.y, prof));
  const blackLine = () => FLIPPER_TOP + 0.003; // v7: black all round, lowest point level with the flipper tops (front, side, back)
  body.add(furPart(bg, (c, x, y, z, nx, ny, nz) => {
    const th = Math.atan2(x, z) / D2R(1);
    c.copy(GG.grey).lerp(GG.white, 1 - sstep(80, 92, Math.abs(th)));          // white front, neutral grey sides/back
    c.lerp(GG.black, sstep(blackLine(th) - 0.006, blackLine(th) + 0.006, y));  // black head (grey rises up the back of the head)
    paintTraced(c, x, y, z, nx, nz);                                           // orange ear patches + beak-base stripe, yellow V bib
    let k = lerp(1, 0.85, sstep(0.44, 0.5, y));
    for (const e of eyeP) k = Math.min(k, lerp(0.12, 1, sstep(0.016, 0.03, e.distanceTo(V3(x, y, z)))));
    return k;
  }, { twist, twistY }));
  if (seated) bake(bg, sitBody);
  // LONG black wedge beak, forward and slightly down; orange stripe along the lower mandible (projected from the side trace)
  const BK = Q.beak;
  const bkRings = [];
  for (let j = 0; j <= 40; j++) {
    const t = j / 40, cap = t < 0.9 ? 1 : Math.sqrt(Math.max(0, 1 - ((t - 0.9) / 0.1) ** 2));
    const z = lerp(BK.z0, BK.z1, t), yc = lerp(BK.y0, BK.y1, t), h = BK.h0 * (1 - 0.8 * t) * cap, w = BK.w0 * (1 - 0.76 * t) * cap;
    bkRings.push(Array.from({ length: 40 }, (_, i) => { const ph = (i / 40) * Math.PI * 2; return V3(w * sexp(Math.cos(ph), 2.3), yc + h * sexp(Math.sin(ph), 2.3), z); }));
  }
  const bkGeo = loftGeo(bkRings), bkT = new Float32Array(bkGeo.attributes.position.count);
  for (let j = 0, k = 0; j < bkRings.length; j++) for (let i = 0; i < 40; i++) bkT[k++] = j / 40; // ring param t per vertex
  let bkI = 0;
  head.add(furPart(bkGeo, (c, x, y, z, nx) => { // bright orange stripe along the lower mandible, both sides, most of the length
    const t = bkT[bkI++], yc = lerp(BK.y0, BK.y1, t), h = Math.max(1e-4, BK.h0 * (1 - 0.8 * t)), sv = (y - yc) / h;
    const lo = lerp(-0.95, -0.8, t), hi = lerp(-0.12, -0.5, t);
    c.copy(GG.black).lerp(GG.orange, sstep(lo - 0.05, lo + 0.05, sv) * (1 - sstep(hi - 0.06, hi + 0.06, sv)) * (1 - sstep(0.82, 0.9, t)) * sstep(0.2, 0.45, Math.abs(nx)));
  }, { len: F.beak_len, shells: F.beak_shells }));
  if (seated) bake(bkGeo, (x, y, z) => [x, y - D, z]);
  // blue glass-bead eyes, half-sunk in short-pile sockets on the sides of the head
  const mIris = new THREE.MeshPhysicalMaterial({ color: Pal.iris, roughness: Q.iris.roughness, clearcoat: Q.iris.clearcoat });
  const mPupil = new THREE.MeshPhysicalMaterial({ color: Pal.pupil, roughness: Q.pupil.roughness, clearcoat: Q.pupil.clearcoat });
  const mGlint = new THREE.MeshBasicMaterial({ color: Pal.glint });
  const eyes = eyeP.map((at, i) => {
    const s = i ? 1 : -1, n = guoSurf(s * (GUO_EYE.th + 2), GUO_EYE.y, prof).sub(guoSurf(s * (GUO_EYE.th - 2), GUO_EYE.y, prof))
      .cross(guoSurf(s * GUO_EYE.th, GUO_EYE.y + 0.004, prof).sub(guoSurf(s * GUO_EYE.th, GUO_EYE.y - 0.004, prof))).normalize().multiplyScalar(s);
    const eye = new THREE.Group(); eye.position.copy(at).addScaledVector(n, -0.0025); eye.position.y -= D; head.add(eye); // v7: sunk flush into the pile
    orient(eye, n, V3(0, 1, 0));
    const bead = new THREE.Group(); bead.scale.set(1, 1, 0.3); eye.add(bead);        // v7: flat glass disc, no visible depth
    sph(0.016, mIris, bead);                                     // glass eye: thin blue ring around a big dark pupil
    const pupil = sph(0.0132, mPupil, bead, [0, 0, 0.0052]);
    sph(0.0028, mGlint, bead, [0.0045, 0.0055, 0.0172]).castShadow = false;
    return { eye, pupil };
  });
  // flippers: flat, wide puppet arms tapering to a blunt rounded end, out sideways, angled slightly down; white front, grey back
  const FL = Q.flippers;
  const flippers = [-1, 1].map((s) => {
    const pivot = new THREE.Group(); pivot.position.set(s * 0.13, 0.43 - D, 0.005); body.add(pivot);
    const rs = [], L = FL.xt - FL.xr, sc = 1 - FL.ht / L;
    for (let j = 0; j <= 36; j++) {
      const t = j / 36, cap = t < sc ? 1 : Math.sqrt(Math.max(0, 1 - ((t - sc) / (1 - sc)) ** 2));
      const x = s * (FL.xr + t * L) - s * 0.13, yc = lerp(FL.yr, FL.yt, t) - 0.43, h = lerp(FL.hr, FL.ht, Math.pow(Math.min(1, t / sc), 0.7)) * cap, th = lerp(FL.tr, FL.tt, t) * cap;
      rs.push(Array.from({ length: 36 }, (_, i) => { const ph = (i / 36) * Math.PI * 2; return V3(x, yc + h * sexp(Math.cos(ph), 2.6), s * th * sexp(Math.sin(ph), 2.2)); }));
    }
    pivot.add(furPart(loftGeo(rs), (c, x, y, z, nx, ny, nz) => c.copy(GG.grey).lerp(GG.white, sstep(-0.25, 0.15, nz)), { len: F.flipper_len }));
    return pivot;
  });
  // legs (white front, grey back, black fluffy bottoms) + stubby black feet at the bottom front
  const legProf = catmull(GUO_LEG, 6);
  for (const s of [-1, 1]) {
    const lr = legProf.map(([y]) => Array.from({ length: 72 }, (_, i) => guoSurf((i / 72) * 360 - 180, y, legProf).add(V3(s * 0.106, 0, 0))));
    const legGeo = loftGeo(lr), footGeo = ellipsoid(0.07, 0.04, 0.074);
    footGeo.translate(s * 0.106, 0.042, 0.05);
    body.add(furPart(legGeo, (c, x, y, z, nx, ny, nz) => {
      c.copy(GG.grey).lerp(GG.white, 1 - sstep(80, 95, Math.abs(Math.atan2(nx, nz)) / D2R(1)));
      c.lerp(GG.black, 1 - sstep(0.082, 0.1, y));
    }));
    body.add(furPart(footGeo, (c) => c.copy(GG.black), { len: F.foot_len }));
    if (seated) { // legs + feet stick forward along the shelf surface, resting on it
      bake(legGeo, sitLeg(s)); bake(footGeo, sitLeg(s));
      const lift = 0.006 - Math.min(legGeo.boundingBox.min.y, footGeo.boundingBox.min.y);
      bake(legGeo, (x, y, z) => [x, y + lift, z]); bake(footGeo, (x, y, z) => [x, y + lift, z]);
    }
  }
  return { root, body, head, eyes, flippers, twist, seated, parts };
}

// Fur secondary motion: gravity droop + lag against the body's vertical speed + flap whip, each
// part's push in its own local frame (scene.js poseGuo, after the rig is posed).
const _q = new THREE.Quaternion(), _w = new THREE.Vector3();
export function pushFur(guo, push, flipperPush) {
  guo.root.updateMatrixWorld(true);
  for (const g of guo.parts) {
    _w.set(0, guo.flippers.includes(g.parent) ? flipperPush : push, 0);
    g.getWorldQuaternion(_q);
    g.userData.push.value.copy(_w.applyQuaternion(_q.invert()));
  }
}
