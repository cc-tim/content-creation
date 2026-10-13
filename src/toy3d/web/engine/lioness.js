// toy3d lioness (E11): a Sylvanian Families-style figure (no mane), lavender dress, gingham-hem apron,
// ported verbatim from the frozen snapshot (scene.js makeLion), with its known weak points (a
// primitive build). Colours and material values from the bank (characters/lioness.yaml). Rig
// nodes: root, hips, body, neck, head, arm_l/arm_r, leg_l/leg_r (j1, j2, e), ear_l/ear_r, tail.
import { THREE, UNTINTED, V3, canvasTex, mk, rbox, sph, lathe, tube, limb } from './core.js';
import { faceShell } from './faces.js';

export function buildLioness(ch, M, faces, mouth) {
  const P = ch.palette, Q = ch.params;
  const { soft } = M;
  const apronTex = canvasTex(256, 256, (g, w, h) => {
    g.fillStyle = P.apron; g.fillRect(0, 0, w, h);
    g.fillStyle = P.apron_check;
    for (let i = 0; i < 16; i++) { g.fillRect(i * 16, h - 44, 8, 44); }
    for (let j = 0; j < 4; j++) g.fillRect(0, h - 44 + j * 11, w, 5);
  }, { repeat: [3, 1] });
  const root = new THREE.Group(); root.scale.setScalar(ch.scale);
  const hips = new THREE.Group(); hips.position.y = 0.17; root.add(hips);
  const body = new THREE.Group(); hips.add(body);
  const mFur = soft(P.fur), mFurLt = soft(P.fur_light), mMuz = soft(P.muzzle), mDress = soft(P.dress), mInner = soft(P.inner_ear), mTuft = soft(P.tuft);
  const mApron = soft(UNTINTED, { map: apronTex, side: THREE.DoubleSide });
  const mNose = new THREE.MeshPhysicalMaterial({ color: P.nose, roughness: Q.nose.roughness, clearcoat: Q.nose.clearcoat });
  lathe([[0, 0], [0.2, 0], [0.255, 0.04], [0.278, 0.13], [0.265, 0.26], [0.22, 0.4], [0.16, 0.5], [0.09, 0.56], [0, 0.575]], mDress, body).scale.z = 0.9;
  lathe([[0.212, 0.012], [0.27, 0.05], [0.292, 0.13], [0.284, 0.24], [0.262, 0.32]], mApron, body, null, 40, -1.25, 2.5).scale.z = 0.9;
  const tie = mk(new THREE.TorusGeometry(0.25, 0.016, 10, 48), soft(P.apron), body, [0, 0.32, 0]); tie.rotation.x = Math.PI / 2; tie.scale.set(1, 0.9, 1);
  const bib = rbox(0.2, 0.16, 0.022, 0.01, soft(P.apron), body, [0, 0.415, 0.198]); bib.rotation.x = -0.41;
  rbox(0.11, 0.075, 0.018, 0.008, soft(P.apron), body, [0.075, 0.17, 0.262]).rotation.y = 0.27;
  for (const s of [-1, 1]) {
    tube([[s * 0.085, 0.48, 0.17], [s * 0.1, 0.56, 0.02], [s * 0.085, 0.5, -0.15], [s * 0.06, 0.34, -0.22]], 0.011, soft(P.apron), body);
    sph(0.05, soft(P.apron), body, [s * 0.055, 0.32, -0.235], [1, 0.65, 0.4]).rotation.z = s * 0.4;
  }
  const neck = new THREE.Group(); neck.position.y = 0.55; body.add(neck);
  const head = new THREE.Group(); head.position.y = 0.3; neck.add(head);
  const skull = sph(0.36, mFur, head, null, [1.1, 1, 1]);
  skull.geometry = new THREE.SphereGeometry(0.36, 72, 54);
  const face = faceShell(0.3625, 0.36, faces.lion_stern, skull, M.faceRoughness);
  const muz = sph(1, mMuz, head, [0, -0.105, 0.3], [0.165, 0.105, 0.1]);
  faceShell(1.012, 1.0, mouth, muz, M.faceRoughness);
  const nose = sph(1, mNose, head, [0, -0.05, 0.392], [0.05, 0.03, 0.03]); nose.rotation.x = -0.3;
  sph(1, mMuz, head, [0, -0.2, 0.27], [0.075, 0.05, 0.06]); // chin
  const mWhisk = soft(P.whisker);
  for (const s of [-1, 1]) for (const k of [-1, 0, 1]) {
    tube([[s * 0.12, -0.1 + k * 0.022, 0.36], [s * 0.2, -0.1 + k * 0.035, 0.36], [s * 0.29, -0.1 + k * 0.06, 0.33]], 0.0035, mWhisk, head).castShadow = false;
  }
  const mEarBack = soft(P.ear_back);
  const ears = [-1, 1].map((s) => {
    const n = V3(Math.sin(0.86) * Math.sin(s * 1.2) * 1.1, Math.cos(0.86), Math.sin(0.86) * Math.cos(s * 1.2)).normalize();
    const ear = new THREE.Group(); ear.position.copy(n.clone().multiplyScalar(0.355)); head.add(ear);
    ear.quaternion.setFromUnitVectors(V3(0, 0, 1), V3(s * 0.55, 0.1, 1).normalize());
    ear.rotateZ(-s * 0.35);
    sph(0.088, mFur, ear, null, [0.95, 1, 0.42]);
    sph(0.06, mInner, ear, [0, -0.01, 0.026], [1, 0.95, 0.3]);
    sph(0.085, mEarBack, ear, [0, 0.008, -0.012], [0.92, 0.95, 0.3]);
    return ear;
  });
  let finger = null;
  const paw = (pointer) => {
    const g = new THREE.Group();
    sph(0.056, mFurLt, g);
    if (pointer) finger = mk(new THREE.CapsuleGeometry(0.018, 0.05, 4, 10), mFurLt, g, [0, -0.06, 0]);
    return g;
  };
  const arms = [-1, 1].map((s, i) => {
    sph(0.085, mDress, body, [s * 0.205, 0.45, 0]);
    const L = limb(0.11, 0.1, 0.048, 0.045, mFur, mFur, paw(i === 1));
    L.j1.position.set(s * 0.215, 0.45, 0); body.add(L.j1);
    return L;
  });
  const legs = [-1, 1].map((s) => {
    const L = limb(0.07, 0.03, 0.06, 0.058, mFur, mFur, sph(1, mFur, null, [0, -0.03, 0.035], [0.068, 0.045, 0.105]));
    L.j1.position.set(s * 0.1, 0.02, 0); hips.add(L.j1);
    return L;
  });
  const tail = new THREE.Group(); tail.position.set(0, 0.08, -0.22); body.add(tail);
  tube([[0, 0, 0], [-0.04, -0.07, -0.12], [-0.17, -0.06, -0.2], [-0.29, 0.05, -0.16], [-0.33, 0.17, -0.1]], 0.026, mFur, tail);
  sph(1, mTuft, tail, [-0.335, 0.21, -0.09], [0.055, 0.08, 0.055]);
  return { root, hips, body, neck, head, face, arms, legs, ears, tail, finger };
}
