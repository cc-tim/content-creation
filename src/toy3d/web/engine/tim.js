// toy3d Tim (E11): the Animal Crossing-style villager with hair H3 (Tim's pick, 2026-10-13), round
// wire glasses and the navy hoodie, ported verbatim from the frozen snapshot (scene.js makeTim,
// buildHair H3). Colours and material values from the bank (characters/tim.yaml); the hairline
// table too. Rig nodes: root, hips, torso, neck, head, arm_l/arm_r, leg_l/leg_r (j1, j2, e).
import {
  THREE, V3, D2R, lerp, clamp01, sstep, mk, rbox, sph, lathe, tube, limb, fixNormals,
} from './core.js';
import { faceShell, TIM_EYE } from './faces.js';

const HEAD_R = 0.42;
const dirYE = (yaw, e) => V3(Math.cos(D2R(e)) * Math.sin(D2R(yaw)), Math.sin(D2R(e)), Math.cos(D2R(e)) * Math.cos(D2R(yaw)));
const edgeThick = (yaw) => lerp(0.028, 0.008, sstep(30, 70, Math.abs(yaw)));   // defined fringe lip; short sides/nape taper thin
const edgeLip = (yaw) => lerp(6, 16, sstep(30, 80, Math.abs(yaw)));             // ramp width (deg): crisp at the fringe, tapered elsewhere

// one solid cap over the skull: thickness ramps up from the hairline with a rounded lip; grooves; edge function
function hairCapGeo({ top = 0.056, edgeT = edgeThick, lip = edgeLip, edge, groove = null, nu = 220, nv = 64 }) {
  const pos = [], idx = [];
  for (let iv = 0; iv <= nv; iv++) for (let iu = 0; iu <= nu; iu++) {
    const yaw = 180 + (iu / nu) * 360, yw = ((yaw + 180) % 360 + 360) % 360 - 180; // seam at the back
    const E = edge(yw), e = E + (89.9 - E) * Math.pow(iv / nv, 0.85);
    const lipK = 1 - Math.pow(1 - clamp01((e - E) / lip(yw)), 3);
    let t = lerp(edgeT(yw), top, sstep(E, 80, e)) * lipK;
    if (groove) t -= Math.min(groove(yw, e, E) * lipK, 0.35 * t); // grooves never cut through the thin taper
    const d = dirYE(yaw, e).multiplyScalar(HEAD_R - 0.004 + t);
    pos.push(d.x, d.y, d.z);
  }
  for (let iv = 0; iv < nv; iv++) for (let iu = 0; iu < nu; iu++) {
    const a = iv * (nu + 1) + iu, b = a + 1, c = a + nu + 1, d = c + 1;
    idx.push(a, b, c, b, d, c);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx);
  g.computeVertexNormals();
  return fixNormals(g);
}

// H3: a smooth mass, shallow sculpted grooves, a slightly tufted fringe edge
function buildHair(P, Q) {
  const H = Q.hair;
  const m = new THREE.MeshPhysicalMaterial({ color: P.hair, roughness: H.roughness, clearcoat: H.clearcoat, clearcoatRoughness: H.clearcoat_roughness,
    sheen: H.sheen, sheenRoughness: H.sheen_roughness, sheenColor: new THREE.Color(P.hair_sheen) }); // dark brown-black with a soft sheen
  // hairline: edge elevation in deg vs yaw (0 = front)
  const HAIRLINE = Q.hairline;
  function hairEdge(yaw) {
    const a = Math.min(180, Math.abs(yaw));
    for (let i = 1; i < HAIRLINE.length; i++) if (a <= HAIRLINE[i][0]) {
      const [y0, e0] = HAIRLINE[i - 1], [y1, e1] = HAIRLINE[i], k = (a - y0) / (y1 - y0);
      return e0 + (e1 - e0) * k * k * (3 - 2 * k);
    }
    return HAIRLINE[HAIRLINE.length - 1][1];
  }
  const g = new THREE.Group();
  const tri = (x) => 1 - Math.abs((((x % 2) + 2) % 2) - 1);
  const edge = (yaw) => hairEdge(yaw) - 3.2 * Math.pow(tri(yaw / 8.5), 1.6) * sstep(58, 30, Math.abs(yaw));
  const groove = (yaw, e, E) => 0.0065 * Math.pow(0.5 + 0.5 * Math.cos(D2R(yaw) * 34), 2.5) * sstep(82, 62, e) * sstep(E + 2, E + 9, e);
  mk(hairCapGeo({ edge, groove, nu: 340, nv: 72 }), m, g);
  return g;
}

export function buildTim(ch, M, faces) {
  const P = ch.palette, Q = ch.params;
  const { soft } = M;
  const { x: EYE_X, y: EYE_Y } = TIM_EYE;
  const root = new THREE.Group(), hips = new THREE.Group(), torso = new THREE.Group();
  root.add(hips); hips.add(torso);
  const mHood = soft(P.hoodie), mHoodDk = soft(P.hoodie_dark), mSkin = soft(P.skin), mPants = soft(P.pants);
  const mStr = soft(P.string), mShoe = soft(P.shoe), mSole = soft(P.sole);
  const body = lathe([[0, -0.02], [0.19, -0.02], [0.225, 0.02], [0.235, 0.1], [0.222, 0.22], [0.195, 0.31], [0.15, 0.375], [0.08, 0.41], [0, 0.42]], mHood, torso);
  body.scale.z = 0.84;
  const hem = mk(new THREE.TorusGeometry(0.206, 0.026, 12, 48), mHoodDk, torso, [0, 0.012, 0]); hem.rotation.x = Math.PI / 2; hem.scale.set(1, 0.84, 1);
  const hood = mk(new THREE.TorusGeometry(0.13, 0.05, 14, 40), mHood, torso, [0, 0.39, -0.03]); hood.rotation.x = Math.PI / 2 + 0.25;
  sph(0.14, mHood, torso, [0, 0.33, -0.15], [1.15, 0.8, 0.62]);
  rbox(0.22, 0.1, 0.03, 0.012, mHoodDk, torso, [0, 0.11, 0.19]).rotation.x = -0.06;
  for (const s of [-1, 1]) {
    mk(new THREE.CapsuleGeometry(0.008, 0.06, 4, 8), mStr, torso, [s * 0.042, 0.29, 0.168]).rotation.set(-0.25, 0, s * 0.35);
  }
  const neck = new THREE.Group(); neck.position.y = 0.4; torso.add(neck);
  const head = new THREE.Group(); head.position.y = 0.34; neck.add(head);
  sph(0.42, mSkin, head).geometry = new THREE.SphereGeometry(0.42, 72, 54);
  for (const s of [-1, 1]) sph(0.07, mSkin, head, [s * 0.41, -0.035, 0.02], [0.55, 1, 0.8]);
  const face = faceShell(0.4225, 0.42, faces.tim_neutral, head, M.faceRoughness);
  head.add(buildHair(P, Q));
  // thin round wire glasses
  const mWire = new THREE.MeshStandardMaterial({ color: P.wire, metalness: Q.wire.metalness, roughness: Q.wire.roughness });
  const mLens = new THREE.MeshPhysicalMaterial({ color: P.lens, transparent: true, opacity: Q.lens.opacity, roughness: Q.lens.roughness, clearcoat: Q.lens.clearcoat, depthWrite: false });
  for (const s of [-1, 1]) {
    const ring = mk(new THREE.TorusGeometry(0.092, 0.0085, 10, 56), mWire, head, [s * EYE_X, EYE_Y, 0.445]);
    ring.rotation.y = s * 0.22;
    const lens = mk(new THREE.CircleGeometry(0.09, 40), mLens, head, [s * EYE_X, EYE_Y, 0.444], { cast: false });
    lens.rotation.y = s * 0.22; lens.userData.noAO = true;
    const ox = s * (EYE_X + 0.092 * Math.cos(0.22)), oz = 0.445 - 0.092 * Math.sin(0.22);
    tube([[ox, EYE_Y + 0.005, oz], ...[38, 55, 72, 86].map((d) => [s * 0.452 * Math.sin(D2R(d)), EYE_Y + 0.01 + d * 0.0003, 0.452 * Math.cos(D2R(d))])], 0.007, mWire, head);
  }
  tube([[-EYE_X + 0.088, EYE_Y + 0.01, 0.452], [0, EYE_Y + 0.03, 0.466], [EYE_X - 0.088, EYE_Y + 0.01, 0.452]], 0.0075, mWire, head);
  // arms + legs
  const arms = [-1, 1].map((s) => {
    const L = limb(0.16, 0.15, 0.05, 0.047, mHood, mHood, sph(0.064, mSkin));
    L.j1.position.set(s * 0.205, 0.31, 0); torso.add(L.j1);
    const cuff = mk(new THREE.TorusGeometry(0.044, 0.014, 8, 24), mHoodDk, L.e, [0, 0.025, 0]); cuff.rotation.x = Math.PI / 2;
    return L;
  });
  const shoe = () => {
    const g = new THREE.Group();
    sph(1, mShoe, g, [0, -0.01, 0.035], [0.068, 0.05, 0.1]);
    sph(1, mSole, g, [0, -0.045, 0.035], [0.07, 0.016, 0.102]);
    return g;
  };
  const legs = [-1, 1].map((s) => {
    const L = limb(0.15, 0.13, 0.062, 0.056, mPants, mPants, shoe());
    L.j1.position.set(s * 0.1, 0.04, 0); hips.add(L.j1);
    return L;
  });
  // sweat drop (the shock expression's)
  const D = Q.drop;
  const drop = lathe([[0, -0.04], [0.025, -0.035], [0.038, -0.018], [0.04, 0], [0.034, 0.02], [0.022, 0.04], [0.01, 0.058], [0, 0.072]],
    new THREE.MeshPhysicalMaterial({ color: P.drop, roughness: D.roughness, clearcoat: D.clearcoat, transparent: true, opacity: D.opacity }), head, [0.355, 0.07, 0.24], 24);
  drop.rotation.z = -0.35;
  return { root, hips, torso, neck, head, face, arms, legs, drop };
}
