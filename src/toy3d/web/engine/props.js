// toy3d props and graphics (E11): the speech bubble (dirty-plates pictogram + "!", billboarded) and
// the idea bulb with its glow, rays, light and smoke, ported verbatim from the frozen snapshot
// (scene.js bubble, bulb, puffs). Colours and look values from the bank (graphics/bubble.yaml,
// props/idea_bulb.yaml).
import { THREE, UNTINTED, canvasTex, mk, sph, lathe, mulberry32 } from './core.js';
import { ell } from './faces.js';

export function buildBubble(scene, def, M) {
  const P = def.palette, Q = def.params;
  const { soft, prop } = M;
  const bubble = new THREE.Group(); scene.add(bubble);
  const bubPop = new THREE.Group(); bubble.add(bubPop);
  const mBub = soft(P.bubble, { clearcoat: Q.bubble.clearcoat });
  sph(1, mBub, bubPop, [0, 0, 0], [0.36, 0.27, 0.075]);
  const tail = mk(new THREE.ConeGeometry(0.07, 0.2, 24), mBub, bubPop, [-0.2, -0.27, 0]); tail.rotation.z = 2.55; tail.scale.z = 0.5;
  const smudge = canvasTex(256, 256, (g) => {
    const r = mulberry32(61);
    ell(g, 128, 128, 120, 120, P.plate);
    for (let i = 0; i < 9; i++) ell(g, 70 + r() * 110, 70 + r() * 110, 12 + r() * 26, 8 + r() * 18, r() < 0.6 ? P.smudge[0] : P.smudge[1]);
  }, { repeat: [1, 1] });
  const plates = new THREE.Group(); plates.position.set(-0.09, -0.1, 0.06); plates.rotation.x = 0.6; plates.scale.setScalar(1.3); bubPop.add(plates);
  const mPlate = prop(P.plate, { roughness: Q.plate.roughness });
  for (let i = 0; i < 5; i++) {
    const pl = lathe([[0, 0], [0.085, 0], [0.115, 0.016], [0.122, 0.026], [0.114, 0.028], [0.084, 0.009], [0, 0.009]], mPlate, plates, [(i % 2 ? 0.012 : -0.01), i * 0.03, 0], 40);
    pl.rotation.z = (i % 2 ? 0.06 : -0.05);
  }
  const dirt = mk(new THREE.CircleGeometry(0.085, 32), prop(UNTINTED, { map: smudge, transparent: true }), plates, [-0.005, 4 * 0.03 + 0.0105, 0], { cast: false });
  dirt.rotation.x = -Math.PI / 2;
  for (const [x, z] of [[0.03, 0.02], [-0.04, -0.01], [0.0, -0.04]]) sph(0.011, prop(P.crumb), plates, [x, 0.133, z]);
  const mBang = soft(P.bang);
  const bang = new THREE.Group(); bang.position.set(0.19, 0.0, 0.06); bubPop.add(bang);
  lathe([[0, -0.03], [0.012, -0.028], [0.03, 0.07], [0.028, 0.095], [0, 0.1]], mBang, bang, [0, 0.0, 0], 24);
  sph(0.026, mBang, bang, [0, -0.07, 0]);
  bubble.visible = false;
  return { bubble, bubPop, bang, icons: { dishes: plates, bang } };
}

export function buildBulb(scene, def, M) {
  const P = def.palette, Q = def.params;
  const lightPer = Q.light.per_level, emissivePer = Q.glass.emissive_per_level, glowPer = Q.glow.opacity_per_level;
  const opacityLit = Q.glass.opacity_lit, opacityOff = Q.glass.opacity_off;
  const bulb = new THREE.Group(); scene.add(bulb);
  const mGlass = new THREE.MeshStandardMaterial({ color: P.glass, emissive: P.emissive, emissiveIntensity: emissivePer, roughness: Q.glass.roughness, transparent: true, opacity: opacityLit });
  lathe([[0, -0.13], [0.035, -0.13], [0.04, -0.1], [0.07, -0.06], [0.09, 0.0], [0.085, 0.04], [0.05, 0.095], [0, 0.11]], mGlass, bulb, null, 40);
  const mScrew = new THREE.MeshStandardMaterial({ color: P.screw, metalness: Q.screw.metalness, roughness: Q.screw.roughness });
  mk(new THREE.CylinderGeometry(0.036, 0.03, 0.06, 20), mScrew, bulb, [0, -0.15, 0]);
  for (const y of [-0.13, -0.15, -0.17]) { const tr = mk(new THREE.TorusGeometry(0.035, 0.006, 6, 20), mScrew, bulb, [0, y, 0]); tr.rotation.x = Math.PI / 2; }
  sph(0.014, M.prop(P.tip), bulb, [0, -0.185, 0]);
  const glowTex = canvasTex(128, 128, (g) => {
    const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    gr.addColorStop(0, P.glow[0]); gr.addColorStop(0.35, P.glow[1]); gr.addColorStop(1, P.glow[2]);
    g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
  });
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  glow.userData.noAO = true; bulb.add(glow);
  const rays = new THREE.Group(); bulb.add(rays);
  const mRay = new THREE.MeshStandardMaterial({ color: P.ray, emissive: P.ray, emissiveIntensity: Q.ray.emissive, roughness: Q.ray.roughness });
  for (let k = 0; k < 7; k++) {
    const a = -Math.PI / 2 + (k - 3) * 0.42;
    const ray = mk(new THREE.CapsuleGeometry(0.011, 0.06, 4, 8), mRay, rays, [Math.cos(a) * 0.19, -Math.sin(a) * 0.19 - 0.01, 0], { cast: false });
    ray.rotation.z = -a - Math.PI / 2 + Math.PI;
  }
  const light = new THREE.PointLight(P.light, lightPer, 0, 2);
  scene.add(light);
  const lit = new THREE.Color(P.glass), off = new THREE.Color(P.glass_off);
  // the bulb at its spec level (scene.js poseBulb, with the level from the timeline)
  function show(s, headWorld) {
    bulb.visible = true;
    bulb.position.set(headWorld.x + s.anchor[0], headWorld.y + s.anchor[1] + s.bob, headWorld.z + s.anchor[2]);
    bulb.rotation.set(0, 0, s.tilt);
    mGlass.emissiveIntensity = emissivePer * s.level;
    mGlass.color.copy(s.lit ? lit : off);
    mGlass.opacity = s.lit ? opacityLit : opacityOff;
    glow.material.opacity = glowPer * s.level;
    glow.scale.setScalar(s.glow);
    rays.visible = s.rays > 0;
    if (s.rays > 0) rays.scale.setScalar(s.rays);
    light.visible = true;
    light.position.copy(bulb.position);
    light.intensity = lightPer * s.level;
  }
  function hide() { bulb.visible = false; light.visible = false; }
  return { bulb, glow, rays, light, mGlass, show, hide };
}

// the bulb's smoke when it goes out (seeded sizes; the spec drives each puff's k)
export function buildSmoke(scene, def, n) {
  const P = def.palette, Q = def.params;
  const puffs = [];
  for (let i = 0; i < n; i++) {
    const m = new THREE.Mesh(new THREE.SphereGeometry(1, 20, 14), new THREE.MeshStandardMaterial({ color: P.smoke, transparent: true, roughness: Q.smoke.roughness, depthWrite: false }));
    m.userData = { noAO: true, kind: 'smoke', i, s: 0.03 + i * 0.008 };
    scene.add(m); puffs.push(m);
  }
  return puffs;
}
