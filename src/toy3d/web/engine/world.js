// toy3d world (E11): builds the scene graph from the bank once, in the snapshot's own order, and
// applies one frame spec (toy3d.acting) to it. The page never animates: every value that moves
// comes from the spec. applyState returns the named nodes' world matrices and render states, so
// the rig can be checked against the snapshot without pixels (Layer B).
import { THREE, materials, strict, checkPalette } from './core.js';
import { timFaces, lionFaces, lionMouth } from './faces.js';
import { buildOffice, buildDust, buildLights } from './room.js';
import { buildTim } from './tim.js';
import { buildLioness } from './lioness.js';
import { buildGuoGuo, pushFur } from './guoguo.js';
import { buildBubble, buildBulb, buildSmoke } from './props.js';
import { makeRenderer, environment, makeComposer } from './post.js';

// What only a render needs: a state-only world (no WebGL) leaves these bank values unread.
const RENDER_ONLY = ['style.yaml.tone', 'style.yaml.shadows', 'style.yaml.environment', 'style.yaml.post'];

const NODE_PROPS = { px: ['position', 'x'], py: ['position', 'y'], pz: ['position', 'z'],
  rx: ['rotation', 'x'], ry: ['rotation', 'y'], rz: ['rotation', 'z'] };

function rigNodes(kind, a) {
  const n = { hips: a.hips, neck: a.neck };
  if (kind === 'tim') n.torso = a.torso; else Object.assign(n, { body: a.body, tail: a.tail, ear_l: a.ears[0], ear_r: a.ears[1] });
  ['l', 'r'].forEach((s, i) => {
    for (const j of ['j1', 'j2']) { n[`arm_${s}.${j}`] = a.arms[i][j]; n[`leg_${s}.${j}`] = a.legs[i][j]; }
  });
  return n;
}

export function buildWorld(bank, { width, height, mode }) {
  if (mode !== 'render' && mode !== 'state') throw new Error(`toy3d: mode is render or state, not ${mode}`);
  const reads = new Set(), unread = [];
  const look = (obj, where) => {
    if (where.endsWith(' palette')) checkPalette(obj, where);
    const s = strict(obj, where, reads); unread.push(s.unread); return s.value;
  };
  const { picked: _picked, fps: _fps, size: _size, ...lookStyle } = bank.style;   // Python's: provenance, timing
  const style = look(lookStyle, 'style.yaml');
  const characters = Object.fromEntries(Object.entries(bank.characters).map(([name, ch]) => [name, {
    ...ch, palette: look(ch.palette, `characters/${name}.yaml palette`), params: look(ch.params, `characters/${name}.yaml params`) }]));
  const kindOf = (kind) => Object.entries(characters).find(([, c]) => c.rig.kind === kind);
  if (Object.keys(bank.sets).join() !== 'office') throw new Error(`toy3d v0 builds the office set only, not ${Object.keys(bank.sets)}`);
  const set = { ...bank.sets.office, palette: look(bank.sets.office.palette, 'sets/office.yaml palette'),
    params: look(bank.sets.office.params, 'sets/office.yaml params') };
  const bulbDef = bank.props.idea_bulb;
  const bulbLook = { palette: look(bulbDef.palette, 'props/idea_bulb.yaml palette'), params: look(bulbDef.params, 'props/idea_bulb.yaml params') };
  const bubbleLook = { palette: look(bank.bubble.palette, 'graphics/bubble.yaml palette'), params: look(bank.bubble.params, 'graphics/bubble.yaml params') };

  const renderer = mode === 'render' ? makeRenderer(style, width, height) : null;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(style.background);
  scene.fog = new THREE.Fog(style.fog.color, style.fog.near, style.fog.far);
  if (renderer) environment(scene, renderer, style);
  const camera = new THREE.PerspectiveCamera(30, width / height, style.camera.near, style.camera.far);

  const M = materials(style, set.palette);
  const [timName, timCh] = kindOf('tim'), [lionName, lionCh] = kindOf('lioness'), [guoName, guoCh] = kindOf('guoguo');
  const faces = { ...timFaces(timCh.palette, timCh.params.face), ...lionFaces(lionCh.palette) };
  const mouth = lionMouth(lionCh.palette);
  const room = buildOffice(scene, set, M);
  const actors = {};
  const tim = buildTim(timCh, M, faces);
  room.chair.add(tim.root);
  actors[timName] = { kind: 'tim', a: tim, nodes: rigNodes('tim', tim) };
  const lion = buildLioness(lionCh, M, faces, mouth);
  scene.add(lion.root);
  actors[lionName] = { kind: 'lioness', a: lion, nodes: rigNodes('lioness', lion) };
  const guoStand = buildGuoGuo(guoCh, bank.trace, false), guoSit = buildGuoGuo(guoCh, bank.trace, true);
  scene.add(guoStand.root, guoSit.root);
  actors[guoName] = { kind: 'guoguo', builds: { guoguo_standing: guoStand, guoguo_seated: guoSit } };
  const bub = buildBubble(scene, bubbleLook, M);
  const bulb = buildBulb(scene, bulbLook, M);
  const dust = buildDust(scene, set);
  const smoke = buildSmoke(scene, bulbLook, bulbDef.out.smoke);
  buildLights(scene, set);
  const post = renderer ? makeComposer(renderer, scene, camera, style, width, height) : null;

  const missed = unread.flatMap((f) => f()).filter((p) => renderer || !RENDER_ONLY.some((r) => p.startsWith(r)));
  if (missed.length) throw new Error(`toy3d bank: the engine never reads ${missed.join(', ')}`);

  const _v = new THREE.Vector3(), _right = new THREE.Vector3(), _up = new THREE.Vector3();
  // Rigs are per character (the bank's names); the spec's actors name their character.
  const headOf = (spec, actor) => {
    const s = spec.actors[actor];
    if (!s) throw new Error(`toy3d: ${actor} is not in this frame`);
    const A = actors[s.character];
    return (A.a ?? A.builds[s.build]).head;
  };

  function poseActor(name, s) {
    const A = actors[name];
    if (A.kind === 'guoguo') {
      for (const [build, g] of Object.entries(A.builds)) g.root.visible = s !== null && s.build === build;
      if (s === null) return;
      const g = A.builds[s.build], G = s.guo;
      g.root.position.set(...s.root.pos);
      g.root.rotation.y = s.root.yaw;
      g.head.rotation.y = g.twist.value = G.head_yaw;
      g.body.scale.set(...G.body_scale);
      g.body.position.y = G.body_py;
      g.body.rotation.z = G.body_rz;
      g.flippers.forEach((f, i) => { f.rotation.z = G.flippers[i]; });
      g.eyes.forEach((e) => { e.eye.scale.setScalar(G.eye); e.pupil.scale.setScalar(G.pupil); });
      pushFur(g, G.push, G.flipper_push);
      return;
    }
    const a = A.a;
    a.root.visible = s !== null;
    if (s === null) return;
    if (s.seat) {   // seated: the chair turns and rolls; the actor sits in it
      const c = room.chair;
      c.position.set(...s.seat.pos);
      c.rotation.y = s.seat.yaw;
      if (a.root.parent !== c) c.add(a.root);
      const dx = s.root.pos[0] - s.seat.pos[0], dz = s.root.pos[2] - s.seat.pos[2], cy = Math.cos(s.seat.yaw), sy = Math.sin(s.seat.yaw);
      a.root.position.set(cy * dx - sy * dz, s.root.pos[1] - s.seat.pos[1], sy * dx + cy * dz);
      a.root.rotation.y = s.root.yaw - s.seat.yaw;
    } else {
      if (a.root.parent !== scene) scene.add(a.root);
      a.root.position.set(...s.root.pos);
      a.root.rotation.y = s.root.yaw;
    }
    for (const [ch, v] of Object.entries(s.joints)) {
      const dot = ch.lastIndexOf('.'), node = A.nodes[ch.slice(0, dot)], p = NODE_PROPS[ch.slice(dot + 1)];
      if (!node || !p) throw new Error(`toy3d: ${name} has no rig channel ${ch}`);
      node[p[0]][p[1]] = v;
    }
    if (s.face !== null) {
      if (!faces[s.face]) throw new Error(`toy3d: no face decal ${s.face}`);
      a.face.material.map = faces[s.face];
    }
    if (a.finger) a.finger.visible = s.flags.includes('finger');
    if (a.drop) {
      a.drop.visible = s.sweat !== null;
      if (s.sweat) { a.drop.scale.setScalar(s.sweat.scale); a.drop.position.y = s.sweat.y; }
    }
  }

  function applyState(spec) {
    // poseAll: the door, the cast, then (with world matrices current) the bulb, puffs and screen
    room.doorHinge.rotation.y = spec.door.angle;
    const byCharacter = {};
    for (const [actor, s] of Object.entries(spec.actors)) {
      if (!actors[s.character]) throw new Error(`toy3d: no character ${s.character} (${actor}) in this world`);
      if (byCharacter[s.character]) throw new Error(`toy3d v0 draws each character once (${s.character})`);
      byCharacter[s.character] = s;
    }
    for (const name of Object.keys(actors)) poseActor(name, byCharacter[name] ?? null);
    scene.updateMatrixWorld(true);
    const props = Object.values(spec.props);
    if (props.length > 1) throw new Error('toy3d v0 draws one idea bulb');
    const p = props[0];
    if (p) {
      headOf(spec, p.on).getWorldPosition(_v);
      bulb.show(p, _v);
    } else bulb.hide();
    const D = spec.door.dust;
    for (const m of dust) {
      const u = m.userData, k = D ? D.k : 0;
      m.visible = k > 0 && k < 1;
      if (!D) continue;
      m.position.copy(u.p).addScaledVector(u.v, D.move);
      m.scale.setScalar(u.s * D.grow);
      m.material.opacity = D.alpha;
    }
    smoke.forEach((m, i) => {
      const s = p ? p.smoke[i] : null, k = s ? s.k : 0;
      m.visible = k > 0 && k < 1;
      if (!s) return;
      m.position.copy(bulb.bulb.position).add(new THREE.Vector3(s.dx, s.rise, 0));
      m.scale.setScalar(m.userData.s * s.grow);
      m.material.opacity = s.alpha;
    });
    room.drawScreen(spec.laptop.lines, spec.laptop.cursor);
    // the camera, then the billboard that faces it
    const C = spec.camera;
    camera.fov = C.fov;
    camera.up.set(...C.up);
    camera.position.set(...C.pos);
    camera.lookAt(...C.target);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld(true);
    if (spec.bubbles.length > 1) throw new Error('toy3d v0 draws one bubble at a time');
    const b = spec.bubbles[0];
    bub.bubble.visible = !!b;
    if (b) {
      headOf(spec, b.speaker).getWorldPosition(_v);
      _right.setFromMatrixColumn(camera.matrixWorld, 0);
      _up.setFromMatrixColumn(camera.matrixWorld, 1);
      bub.bubble.position.copy(_v).addScaledVector(_right, b.right).addScaledVector(_up, b.up).add(new THREE.Vector3(0, b.bob, 0));
      bub.bubble.quaternion.copy(camera.quaternion);
      bub.bubPop.scale.setScalar(b.pop);
      bub.bang.scale.setScalar(b.bang);
      for (const [icon, g] of Object.entries(bub.icons)) g.visible = b.icons.includes(icon);
    }
    scene.updateMatrixWorld(true);
    return snapshot();
  }

  // Layer B: named world matrices and render states, comparable to the snapshot's own
  function snapshot() {
    const out = {};
    const put = (name, o) => { if (o.visible) out[name] = Array.from(o.matrixWorld.elements); };
    for (const [name, A] of Object.entries(actors)) {
      if (A.kind === 'guoguo') {
        const g = Object.values(A.builds).find((x) => x.root.visible);
        if (!g) continue;
        put(`${name}.root`, g.root); put(`${name}.body`, g.body); put(`${name}.head`, g.head);
        g.flippers.forEach((f, i) => put(`${name}.flipper_${'lr'[i]}`, f));
        g.eyes.forEach((e, i) => { put(`${name}.eye_${'lr'[i]}`, e.eye); put(`${name}.pupil_${'lr'[i]}`, e.pupil); });
        out[`${name}.build`] = g.seated ? 'guoguo_seated' : 'guoguo_standing';
        out[`${name}.twist`] = g.twist.value;
        g.parts.forEach((part, i) => { out[`${name}.push.${i}`] = part.userData.push.value.toArray(); });
        continue;
      }
      const a = A.a;
      if (!a.root.visible) continue;
      put(`${name}.root`, a.root); put(`${name}.head`, a.head);
      for (const [n, o] of Object.entries(A.nodes)) put(`${name}.${n}`, o);
      out[`${name}.face`] = Object.entries(faces).find(([, t]) => t === a.face.material.map)?.[0] ?? null;
      if (a.finger) out[`${name}.finger`] = a.finger.visible;
      if (a.drop && a.drop.visible) put(`${name}.drop`, a.drop);
    }
    put('chair', room.chair); put('door', room.doorHinge); put('camera', camera);
    out['camera.fov'] = camera.fov;
    if (bulb.bulb.visible) {
      put('bulb', bulb.bulb);
      Object.assign(out, { 'bulb.emissive': bulb.mGlass.emissiveIntensity, 'bulb.opacity': bulb.mGlass.opacity,
        'bulb.color': bulb.mGlass.color.getHexString(), 'glow.opacity': bulb.glow.material.opacity,
        'glow.scale': bulb.glow.scale.x, 'rays.visible': bulb.rays.visible, 'light.intensity': bulb.light.intensity });
      if (bulb.rays.visible) out['rays.scale'] = bulb.rays.scale.x;
    }
    if (bub.bubble.visible) { put('bubble', bub.bubble); put('bubble.pop', bub.bubPop); put('bubble.bang', bub.bang); }
    dust.forEach((m, i) => { if (m.visible) { put(`dust.${i}`, m); out[`dust.${i}.opacity`] = m.material.opacity; } });
    smoke.forEach((m, i) => { if (m.visible) { put(`smoke.${i}`, m); out[`smoke.${i}.opacity`] = m.material.opacity; } });
    return out;
  }

  function renderState(spec) {
    if (!post) throw new Error('toy3d: this page was built in state mode (no WebGL); init it with mode render');
    applyState(spec);
    post.grade.uniforms.frame.value = spec.frame;
    post.composer.render();
    return renderer.domElement.toDataURL('image/png');
  }

  function info() {
    if (!renderer) return { renderer: null, mode };
    const gl = renderer.getContext(), ext = gl.getExtension('WEBGL_debug_renderer_info');
    return { renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER), mode };
  }

  return { scene, camera, applyState, renderState, info };
}
