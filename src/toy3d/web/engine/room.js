// toy3d set "office" (E11): a Sylvanian-style dollhouse cutaway (open front and right) with the hall
// behind its door, ported verbatim from the frozen snapshot (scene.js room … chair, lights). The
// set's colours and look values are its bank palette / params; geometry stays here.
import {
  THREE, UNTINTED, BLACK, V3, canvasTex, mk, rbox, sph, lathe, worldBox, mulberry32, rgba,
} from './core.js';
import { ell, line } from './faces.js';

const RX0 = -2.6, RX1 = 2.4, RZ0 = -1.9, RZ1 = 1.25, WH = 2.3, WT = 0.1;
const DOOR = { z0: -1.125, z1: -0.275, h: 1.75 };
const WIN = { x0: 1.45, x1: 2.15, y0: 0.95, y1: 1.75 };
const HX0 = -4.3, HZ0 = -1.75, HZ1 = 0.35;
export const ROOM = { RX0, DOOR };

export function buildOffice(scene, set, M) {
  const P = set.palette, Q = set.params;
  const { soft, prop, wood } = M;
  const [seatX, , seatZ] = set.spots.desk_seat.pos;

  const wallpaper = canvasTex(256, 256, (g, w, h) => {
    const r = mulberry32(41);
    g.fillStyle = P.wall; g.fillRect(0, 0, w, h);
    const flower = (x, y, col) => {
      for (let k = 0; k < 5; k++) { const a = (k / 5) * Math.PI * 2; g.beginPath(); g.arc(x + Math.cos(a) * 5, y + Math.sin(a) * 5, 3.6, 0, Math.PI * 2); g.fillStyle = col; g.fill(); }
      g.beginPath(); g.arc(x, y, 2.6, 0, Math.PI * 2); g.fillStyle = P.wallpaper_centre; g.fill();
    };
    const [pink, sage] = P.wallpaper_flowers;
    for (const [x, y, c] of [[40, 50, pink], [168, 30, sage], [110, 140, pink], [220, 170, sage], [30, 210, sage], [150, 230, pink]]) {
      for (const [ox, oy] of [[0, 0], [256, 0], [-256, 0], [0, 256], [0, -256]]) flower(x + ox + (r() - 0.5) * 6, y + oy + (r() - 0.5) * 6, c);
    }
    for (let i = 0; i < 40; i++) { g.beginPath(); g.arc(r() * w, r() * h, 1.2, 0, Math.PI * 2); g.fillStyle = P.wallpaper_dot; g.fill(); }
  });
  const floorTex = canvasTex(1024, 1024, (g, w, h) => {
    const r = mulberry32(57), rows = 6, rh = h / rows;
    for (let j = 0; j < rows; j++) {
      let x = -r() * 300;
      while (x < w) {
        const len = 260 + r() * 340, v = 0.93 + r() * 0.12, c = new THREE.Color(P.floor).multiplyScalar(v);
        g.fillStyle = `#${c.getHexString()}`; g.fillRect(x, j * rh, len, rh);
        for (let k = 0; k < 6; k++) {
          g.strokeStyle = rgba(P.floor_grain, 0.05 + r() * 0.06); g.lineWidth = 1 + r() * 2;
          const yy = j * rh + 10 + r() * (rh - 20); g.beginPath(); g.moveTo(x, yy); g.bezierCurveTo(x + len * 0.3, yy + 5, x + len * 0.6, yy - 5, x + len, yy + 2); g.stroke();
        }
        g.fillStyle = rgba(P.floor_seam, 0.45); g.fillRect(x, j * rh, 3, rh);
        x += len;
      }
      g.fillStyle = rgba(P.floor_seam, 0.5); g.fillRect(0, j * rh, w, 3);
    }
  }, { repeat: [1, 1] });
  const hallTile = canvasTex(256, 256, (g, w, h) => {
    g.fillStyle = P.hall_wall; g.fillRect(0, 0, w, h);
    for (let y = 0; y < 4; y++) for (let x = 0; x < 4; x++) if ((x + y) % 2) { g.fillStyle = P.hall_check; g.fillRect(x * 64, y * 64, 64, 64); }
    g.strokeStyle = P.hall_grid; g.lineWidth = 3;
    for (let i = 0; i <= 4; i++) { g.beginPath(); g.moveTo(i * 64, 0); g.lineTo(i * 64, h); g.stroke(); g.beginPath(); g.moveTo(0, i * 64); g.lineTo(w, i * 64); g.stroke(); }
  });

  const mWall = prop(UNTINTED, { map: wallpaper });
  const mExt = prop(P.exterior), mBeam = wood(P.beam), mTrim = prop(P.trim), mWains = prop(P.wainscot);
  const mHall = prop(UNTINTED, { map: hallTile });
  // box face order: +x, -x, +y, -y, +z, -z
  const backMats = [mExt, mExt, mBeam, mExt, mWall, mExt];
  const leftMats = [mWall, mExt, mBeam, mExt, mExt, mExt];
  const box = (x0, x1, y0, y1, z0, z1, mats, tile = 0.45) => worldBox(x0, x1, y0, y1, z0, z1, mats, tile, scene);
  // back wall with window hole
  box(RX0 - WT, WIN.x0, 0, WH, RZ0 - WT, RZ0, backMats);
  box(WIN.x1, RX1, 0, WH, RZ0 - WT, RZ0, backMats);
  box(WIN.x0, WIN.x1, 0, WIN.y0, RZ0 - WT, RZ0, backMats);
  box(WIN.x0, WIN.x1, WIN.y1, WH, RZ0 - WT, RZ0, backMats);
  // left wall with door hole
  box(RX0 - WT, RX0, 0, WH, RZ0 - WT, DOOR.z0, leftMats);
  box(RX0 - WT, RX0, 0, WH, DOOR.z1, RZ1, leftMats);
  box(RX0 - WT, RX0, DOOR.h, WH, DOOR.z0, DOOR.z1, leftMats);
  // wainscot, baseboard, rail
  box(RX0, RX1, 0, 0.72, RZ0, RZ0 + 0.02, mWains);
  box(RX0, RX0 + 0.02, 0, 0.72, RZ0, DOOR.z0 - 0.06, mWains);
  box(RX0, RX0 + 0.02, 0, 0.72, DOOR.z1 + 0.06, RZ1, mWains);
  rbox(RX1 - RX0, 0.04, 0.045, 0.012, mTrim, scene, [(RX0 + RX1) / 2, 0.74, RZ0 + 0.03]);
  rbox(0.045, 0.04, DOOR.z0 - 0.06 - RZ0, 0.012, mTrim, scene, [RX0 + 0.03, 0.74, (RZ0 + DOOR.z0 - 0.06) / 2]);
  rbox(0.045, 0.04, RZ1 - DOOR.z1 - 0.06, 0.012, mTrim, scene, [RX0 + 0.03, 0.74, (RZ1 + DOOR.z1 + 0.06) / 2]);
  rbox(RX1 - RX0, 0.09, 0.035, 0.01, mTrim, scene, [(RX0 + RX1) / 2, 0.045, RZ0 + 0.035]);
  // timber beams + posts
  rbox(RX1 - RX0 + 0.22, 0.1, 0.16, 0.02, mBeam, scene, [(RX0 + RX1) / 2, WH + 0.05, RZ0 - WT / 2]);
  rbox(0.16, 0.1, RZ1 - RZ0 + 0.22, 0.02, mBeam, scene, [RX0 - WT / 2, WH + 0.05, (RZ0 + RZ1) / 2]);
  rbox(0.14, WH, 0.14, 0.02, mBeam, scene, [RX1 + 0.03, WH / 2, RZ0 - WT / 2]);
  rbox(0.14, WH, 0.14, 0.02, mBeam, scene, [RX0 - WT / 2, WH / 2, RZ1 + 0.03]);
  // floor + base slab + tabletop
  const floor = mk(new THREE.PlaneGeometry(RX1 - RX0, RZ1 - RZ0), prop(UNTINTED, { map: floorTex }), scene, [(RX0 + RX1) / 2, 0.001, (RZ0 + RZ1) / 2], { cast: false });
  floor.rotation.x = -Math.PI / 2;
  floorTex.repeat.set((RX1 - RX0) / 1.7, (RZ1 - RZ0) / 1.7);
  rbox(RX1 - HX0 + 0.3, 0.16, RZ1 - RZ0 + 0.3, 0.04, mBeam, scene, [(HX0 + RX1) / 2, -0.08, (RZ0 + RZ1) / 2]);
  const table = mk(new THREE.CircleGeometry(30, 64), prop(P.table), scene, [0, -0.16, 0], { cast: false });
  table.rotation.x = -Math.PI / 2;

  // door: hinge on the back edge, swings into the room
  const doorHinge = new THREE.Group();
  doorHinge.position.set(RX0 - WT / 2, 0, DOOR.z0);
  scene.add(doorHinge);
  const mDoor = prop(P.door);
  rbox(0.055, DOOR.h - 0.02, DOOR.z1 - DOOR.z0 - 0.02, 0.012, mDoor, doorHinge, [0, DOOR.h / 2, (DOOR.z1 - DOOR.z0) / 2]);
  for (const sx of [-1, 1]) for (const [py, ph] of [[0.48, 0.62], [1.24, 0.66]]) rbox(0.02, ph, 0.58, 0.01, mDoor, doorHinge, [sx * 0.032, py, 0.425]);
  const mBrass = new THREE.MeshStandardMaterial({ color: P.brass, metalness: Q.brass.metalness, roughness: Q.brass.roughness });
  for (const sx of [-1, 1]) sph(0.034, mBrass, doorHinge, [sx * 0.062, 0.9, 0.73]);
  // door frame trim (room side)
  rbox(0.04, DOOR.h + 0.06, 0.06, 0.012, mTrim, scene, [RX0 + 0.015, (DOOR.h + 0.06) / 2, DOOR.z0 - 0.03]);
  rbox(0.04, DOOR.h + 0.06, 0.06, 0.012, mTrim, scene, [RX0 + 0.015, (DOOR.h + 0.06) / 2, DOOR.z1 + 0.03]);
  rbox(0.04, 0.06, DOOR.z1 - DOOR.z0 + 0.12, 0.012, mTrim, scene, [RX0 + 0.015, DOOR.h + 0.03, (DOOR.z0 + DOOR.z1) / 2]);

  // hallway (kitchen side) behind the door
  const hallMats = [mHall, mExt, mBeam, mExt, mHall, mHall];
  box(HX0 - WT, HX0, 0, WH, HZ0 - WT, HZ1 + WT, hallMats, 0.5);
  box(HX0, RX0 - WT, 0, WH, HZ0 - WT, HZ0, hallMats, 0.5);
  box(HX0, RX0 - WT, 0, WH, HZ1, HZ1 + WT, [mHall, mHall, mBeam, mExt, mExt, mHall], 0.5);
  const hallFloor = mk(new THREE.PlaneGeometry(RX0 - WT - HX0, HZ1 - HZ0), prop(P.hall_floor), scene, [(HX0 + RX0 - WT) / 2, 0.001, (HZ0 + HZ1) / 2], { cast: false });
  hallFloor.rotation.x = -Math.PI / 2;
  rbox(0.22, 0.04, 0.9, 0.01, wood(P.desk), scene, [HX0 + 0.11, 1.35, -0.7]);
  [[-1.0, 0.2], [-0.78, 0.26], [-0.55, 0.18], [-0.36, 0.22]].forEach(([z, h], i) => {
    lathe([[0, 0], [0.06, 0], [0.065, h * 0.8], [0.05, h], [0, h]], prop(P.hall_vases[i]), scene, [HX0 + 0.12, 1.37, z], 24);
  });
  const hallLight = new THREE.PointLight(P.hall_light, Q.hall_light.intensity, 0, 2);
  hallLight.position.set(...Q.hall_light.pos);
  scene.add(hallLight);

  // window + outside backdrop + curtains
  const skyTex = canvasTex(512, 512, (g, w, h) => {
    const gr = g.createLinearGradient(0, 0, 0, h);
    gr.addColorStop(0, P.sky[0]); gr.addColorStop(0.65, P.sky[1]); gr.addColorStop(1, P.sky[2]);
    g.fillStyle = gr; g.fillRect(0, 0, w, h);
    const r = mulberry32(73);
    for (let i = 0; i < 5; i++) { const x = r() * w, y = 60 + r() * 160; for (let k = 0; k < 4; k++) ell(g, x + k * 26, y + Math.sin(k) * 6, 34, 18, P.cloud); }
    g.fillStyle = P.hills[0]; g.beginPath(); g.moveTo(0, 380); g.bezierCurveTo(140, 320, 260, 400, 512, 340); g.lineTo(512, 512); g.lineTo(0, 512); g.fill();
    g.fillStyle = P.hills[1]; g.beginPath(); g.moveTo(0, 430); g.bezierCurveTo(200, 390, 330, 450, 512, 410); g.lineTo(512, 512); g.lineTo(0, 512); g.fill();
  });
  mk(new THREE.PlaneGeometry(1.1, 1.1), new THREE.MeshBasicMaterial({ map: skyTex }), scene, [(WIN.x0 + WIN.x1) / 2, 1.35, RZ0 - WT - 0.12], { cast: false, recv: false });
  const mWinFrame = prop(P.trim);
  rbox(WIN.x1 - WIN.x0 + 0.12, 0.06, 0.08, 0.015, mWinFrame, scene, [(WIN.x0 + WIN.x1) / 2, WIN.y1 + 0.03, RZ0 - 0.03]);
  rbox(WIN.x1 - WIN.x0 + 0.22, 0.05, 0.16, 0.015, mWinFrame, scene, [(WIN.x0 + WIN.x1) / 2, WIN.y0 - 0.02, RZ0 + 0.03]);
  for (const x of [WIN.x0, WIN.x1]) rbox(0.06, WIN.y1 - WIN.y0, 0.08, 0.015, mWinFrame, scene, [x, (WIN.y0 + WIN.y1) / 2, RZ0 - 0.03]);
  rbox(0.025, WIN.y1 - WIN.y0, 0.03, 0.008, mWinFrame, scene, [(WIN.x0 + WIN.x1) / 2, (WIN.y0 + WIN.y1) / 2, RZ0 - 0.05]);
  rbox(WIN.x1 - WIN.x0, 0.025, 0.03, 0.008, mWinFrame, scene, [(WIN.x0 + WIN.x1) / 2, (WIN.y0 + WIN.y1) / 2, RZ0 - 0.05]);
  const gingham = canvasTex(128, 128, (g, w, h) => {
    g.fillStyle = P.gingham; g.fillRect(0, 0, w, h);
    g.fillStyle = P.gingham_check;
    for (let i = 0; i < 4; i++) { g.fillRect(i * 32, 0, 16, h); g.fillRect(0, i * 32, w, 16); }
  }, { repeat: [3, 8] });
  for (const [x, sgn] of [[WIN.x0 - 0.1, -1], [WIN.x1 + 0.1, 1]]) {
    const g = new THREE.PlaneGeometry(0.3, 1.0, 30, 1);
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) p.setZ(i, 0.022 * Math.sin(p.getX(i) * 52 + sgn));
    g.computeVertexNormals();
    const c = mk(g, soft(UNTINTED, { map: gingham, side: THREE.DoubleSide, normalMap: null, sheen: Q.curtain.sheen }), scene, [x, 1.36, RZ0 + 0.07]);
    c.rotation.y = 0;
  }
  const rod = mk(new THREE.CylinderGeometry(0.014, 0.014, WIN.x1 - WIN.x0 + 0.7, 12), wood(P.beam), scene, [(WIN.x0 + WIN.x1) / 2, 1.88, RZ0 + 0.07]);
  rod.rotation.z = Math.PI / 2;
  for (const x of [WIN.x0 - 0.35, WIN.x1 + 0.35]) sph(0.03, wood(P.beam), scene, [x, 1.88, RZ0 + 0.07]);

  // framed painting (wordless landscape)
  const paintTex = canvasTex(512, 384, (g, w, h) => {
    const gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, P.painting_sky[0]); gr.addColorStop(1, P.painting_sky[1]);
    g.fillStyle = gr; g.fillRect(0, 0, w, h);
    ell(g, 360, 120, 46, 46, P.painting_sun);
    g.fillStyle = P.painting_hills[0]; g.beginPath(); g.moveTo(0, 250); g.bezierCurveTo(150, 170, 300, 270, 512, 210); g.lineTo(512, 384); g.lineTo(0, 384); g.fill();
    g.fillStyle = P.painting_hills[1]; g.beginPath(); g.moveTo(0, 310); g.bezierCurveTo(180, 250, 320, 330, 512, 290); g.lineTo(512, 384); g.lineTo(0, 384); g.fill();
    for (const [x, y] of [[90, 235], [120, 245], [420, 262]]) { ell(g, x, y, 18, 24, P.painting_tree); g.fillStyle = P.painting_trunk; g.fillRect(x - 3, y + 18, 6, 18); }
  });
  rbox(0.62, 0.48, 0.04, 0.015, wood(P.beam), scene, [-1.6, 1.48, RZ0 + 0.02]);
  mk(new THREE.PlaneGeometry(0.52, 0.38), prop(UNTINTED, { map: paintTex, roughness: Q.painting.roughness }), scene, [-1.6, 1.48, RZ0 + 0.042], { cast: false });

  // wall clock above the door: ticks only, no numerals
  const clockTex = canvasTex(256, 256, (g) => {
    ell(g, 128, 128, 120, 120, P.clock_face);
    for (let i = 0; i < 12; i++) { const a = (i / 12) * Math.PI * 2; ell(g, 128 + Math.sin(a) * 96, 128 - Math.cos(a) * 96, i % 3 ? 5 : 8, i % 3 ? 5 : 8, P.clock_ticks); }
    line(g, [[128, 128], [128 + 50, 128 - 30]], 10, P.clock_hands); line(g, [[128, 128], [128 - 20, 128 - 78]], 7, P.clock_hands); ell(g, 128, 128, 10, 10, P.clock_hands);
  });
  const clockRim = mk(new THREE.CylinderGeometry(0.19, 0.19, 0.05, 40), wood(P.beam), scene, [RX0 + 0.03, 2.02, -0.7]);
  clockRim.rotation.z = Math.PI / 2;
  const clockFace = mk(new THREE.CircleGeometry(0.165, 40), prop(UNTINTED, { map: clockTex }), scene, [RX0 + 0.058, 2.02, -0.7], { cast: false });
  clockFace.rotation.y = Math.PI / 2;

  // bookshelf (plain spines)
  const shelf = new THREE.Group(); shelf.position.set(-0.45, 0, RZ0 + 0.215); scene.add(shelf);
  const mShelf = wood(P.shelf);
  for (const sx of [-1, 1]) rbox(0.045, 1.02, 0.4, 0.01, mShelf, shelf, [sx * 0.42, 0.51, 0]);
  for (const y of [0.04, 0.37, 0.7, 1.02]) rbox(0.88, 0.04, 0.41, 0.01, mShelf, shelf, [0, y, 0]);
  {
    const r = mulberry32(91), cols = P.books;
    for (const y of [0.06, 0.39, 0.72]) {
      let x = -0.39;
      const stop = 0.39 - (y > 0.5 ? 0.25 : 0.06);
      while (x < stop) {
        const w = 0.035 + r() * 0.035, h = 0.18 + r() * 0.09;
        const b = rbox(w, h, 0.2, 0.008, prop(cols[Math.floor(r() * cols.length)]), shelf, [x + w / 2, y + h / 2, 0.02]);
        if (r() < 0.15) b.rotation.z = 0.08;
        x += w + 0.004;
      }
    }
    lathe([[0, 0], [0.07, 0], [0.08, 0.12], [0, 0.12]], prop(P.pot), shelf, [0.25, 0.74, 0], 24);
    for (const [dx, dy, rr] of [[0, 0.17, 0.08], [-0.05, 0.15, 0.06], [0.05, 0.16, 0.06]]) sph(rr, soft(P.green), shelf, [0.25 + dx, 0.74 + dy, 0]);
    lathe([[0, 0], [0.05, 0], [0.06, 0.08], [0.03, 0.16], [0.035, 0.2], [0, 0.2]], prop(P.shelf_vase, { roughness: Q.vase.roughness }), shelf, [-0.32, 1.04, 0.02], 24);
  }
  // floor plant
  lathe([[0, 0], [0.14, 0], [0.17, 0.3], [0.18, 0.32], [0, 0.32]], prop(P.pot), scene, [0.4, 0, RZ0 + 0.32], 32);
  for (const [dx, dy, dz, rr] of [[0, 0.55, 0, 0.2], [-0.13, 0.45, 0.05, 0.15], [0.14, 0.48, -0.02, 0.16], [0.03, 0.72, 0.02, 0.14], [0.06, 0.42, 0.13, 0.12]]) {
    sph(rr, soft(rr > 0.15 ? P.green : P.green_dark), scene, [0.4 + dx, dy, RZ0 + 0.32 + dz]);
  }
  // braided rug
  const rugTex = canvasTex(512, 512, (g) => {
    const cols = P.rug;
    for (let i = 15; i >= 0; i--) { ell(g, 256, 256, (i + 1) * 16, (i + 1) * 16, cols[i % 4]); }
    g.strokeStyle = P.rug_braid; g.lineWidth = 2;
    for (let i = 1; i <= 16; i++) for (let k = 0; k < i * 7; k++) {
      const a = (k / (i * 7)) * Math.PI * 2, rr = i * 16 - 8;
      g.beginPath(); g.moveTo(256 + Math.cos(a) * (rr - 5), 256 + Math.sin(a) * (rr - 5)); g.lineTo(256 + Math.cos(a + 0.05) * (rr + 5), 256 + Math.sin(a + 0.05) * (rr + 5)); g.stroke();
    }
  });
  const rug = mk(new THREE.CircleGeometry(0.85, 64), soft(UNTINTED, { map: rugTex, normalMap: null }), scene, [seatX, 0.006, seatZ + 0.05], { cast: false });
  rug.rotation.x = -Math.PI / 2;

  // desk + laptop + clutter
  const mDesk = wood(P.desk), mDeskDk = wood(P.desk_dark);
  const DESK = { x: seatX, z: 0.025, w: 1.15, d: 0.55, h: 0.55 };
  rbox(DESK.w, 0.055, DESK.d, 0.02, mDesk, scene, [DESK.x, DESK.h - 0.0275, DESK.z]);
  for (const [dx, dz] of [[-1, -1], [-1, 1], [1, -1], [1, 1]]) rbox(0.06, DESK.h - 0.05, 0.06, 0.02, mDeskDk, scene, [DESK.x + dx * (DESK.w / 2 - 0.06), (DESK.h - 0.05) / 2, DESK.z + dz * (DESK.d / 2 - 0.06)]);
  rbox(0.3, 0.17, DESK.d - 0.08, 0.02, mDesk, scene, [DESK.x + 0.36, DESK.h - 0.14, DESK.z]);
  sph(0.022, mBrass, scene, [DESK.x + 0.36, DESK.h - 0.14, DESK.z - DESK.d / 2 + 0.03]);
  const mLap = prop(P.laptop, { roughness: Q.laptop.roughness, metalness: Q.laptop.metalness });
  rbox(0.38, 0.022, 0.26, 0.008, mLap, scene, [DESK.x, DESK.h + 0.011, -0.06]);
  rbox(0.33, 0.004, 0.12, 0.002, prop(P.laptop_dark), scene, [DESK.x, DESK.h + 0.023, -0.03]);
  const lid = new THREE.Group(); lid.position.set(DESK.x, DESK.h + 0.02, 0.07); lid.rotation.x = 0.26; scene.add(lid);
  rbox(0.38, 0.25, 0.014, 0.008, mLap, lid, [0, 0.125, 0]);
  const scrCanvas = document.createElement('canvas'); scrCanvas.width = 512; scrCanvas.height = 320;
  const scrTex = new THREE.CanvasTexture(scrCanvas); scrTex.colorSpace = THREE.SRGBColorSpace;
  const screen = mk(new THREE.PlaneGeometry(0.35, 0.22), new THREE.MeshStandardMaterial({ color: BLACK, emissive: UNTINTED, emissiveMap: scrTex, emissiveIntensity: Q.screen.emissive, roughness: Q.screen.roughness }),
    lid, [0, 0.128, -0.0075], { cast: false });
  screen.rotation.y = Math.PI;
  const scr = { bg: P.screen_bg, bar: P.screen_bar, dots: P.screen_dots, cols: P.screen_code, cursor: P.screen_cursor };
  function drawScreen(lines, cursor) { // wordless: pastel code bars "typing" in
    const g = scrCanvas.getContext('2d');
    g.fillStyle = scr.bg; g.fillRect(0, 0, 512, 320);
    g.fillStyle = scr.bar; g.fillRect(0, 0, 512, 34);
    scr.dots.forEach((c, i) => ell(g, 22 + i * 22, 17, 6, 6, c));
    const cols = scr.cols;
    const r = mulberry32(5);
    let y = 54;
    for (let i = 0; i < lines; i++) {
      const indent = [0, 1, 1, 2, 2, 1, 0, 1, 2, 1, 0][i] * 26;
      let x = 22 + indent;
      const nb = 1 + Math.floor(r() * 3);
      for (let b = 0; b < nb; b++) {
        const w = 30 + r() * 90;
        g.fillStyle = cols[Math.floor(r() * cols.length)];
        g.beginPath(); g.roundRect(x, y, w, 12, 6); g.fill();
        x += w + 12;
      }
      y += 23;
    }
    if (cursor) { g.fillStyle = scr.cursor; g.fillRect(22, y, 8, 14); }
    scrTex.needsUpdate = true;
  }
  const screenLight = new THREE.PointLight(P.screen_light, Q.screen_light.intensity, 0, 2);
  screenLight.position.set(DESK.x, DESK.h + 0.17, 0.02);
  scene.add(screenLight);
  // mug, plant, notebook
  lathe([[0, 0], [0.05, 0], [0.052, 0.1], [0.046, 0.1], [0.044, 0.01], [0, 0.01]], prop(P.mug, { roughness: Q.mug.roughness }), scene, [DESK.x - 0.43, DESK.h, -0.05], 32);
  const handle = mk(new THREE.TorusGeometry(0.028, 0.008, 8, 20), prop(P.mug, { roughness: Q.mug.roughness }), scene, [DESK.x - 0.48, DESK.h + 0.05, -0.05]);
  handle.rotation.y = Math.PI / 2;
  lathe([[0, 0], [0.045, 0], [0.055, 0.07], [0, 0.07]], prop(P.pot), scene, [DESK.x + 0.45, DESK.h, 0.15], 24);
  for (const [dx, dz, a] of [[0, 0, 0], [0.025, 0.01, 0.6], [-0.025, 0.01, -0.6], [0.01, -0.025, 0.3], [-0.01, 0.025, -0.3]]) {
    const l = sph(0.03, soft(P.green), scene, [DESK.x + 0.45 + dx, DESK.h + 0.1, 0.15 + dz], [0.7, 1.3, 0.7]);
    l.rotation.z = a;
  }
  rbox(0.2, 0.025, 0.26, 0.01, prop(P.notebook), scene, [DESK.x + 0.36, DESK.h + 0.0125, -0.1]).rotation.y = 0.12;
  rbox(0.19, 0.012, 0.25, 0.006, prop(P.notebook_paper), scene, [DESK.x + 0.36, DESK.h + 0.031, -0.1]).rotation.y = 0.08;

  // swivel chair at the desk seat (it turns and rolls with whoever sits in it)
  const chair = new THREE.Group(); chair.position.set(seatX, 0, seatZ); scene.add(chair);
  const mPad = soft(P.chair_pad), mFrame = prop(P.chair_frame, { roughness: Q.chair_frame.roughness });
  lathe([[0, 0], [0.2, 0], [0.235, 0.02], [0.24, 0.05], [0.225, 0.075], [0.18, 0.085], [0, 0.085]], mPad, chair, [0, 0.215, 0], 48);
  rbox(0.4, 0.34, 0.075, 0.035, mPad, chair, [0, 0.55, -0.24]).rotation.x = -0.08;
  rbox(0.05, 0.3, 0.03, 0.012, mFrame, chair, [0, 0.36, -0.22]);
  mk(new THREE.CylinderGeometry(0.022, 0.022, 0.16, 16), mFrame, chair, [0, 0.13, 0]);
  for (let k = 0; k < 5; k++) {
    const a = (k / 5) * Math.PI * 2 + 0.3;
    const sp = mk(new THREE.CapsuleGeometry(0.018, 0.2, 4, 10), mFrame, chair, [Math.sin(a) * 0.11, 0.055, Math.cos(a) * 0.11]);
    sp.rotation.order = 'YXZ'; sp.rotation.set(Math.PI / 2, a, 0);
    sph(0.03, mFrame, chair, [Math.sin(a) * 0.22, 0.03, Math.cos(a) * 0.22]);
  }
  // FNV-1a over the screen's pixels (Layer B: the drawn code bars, comparable to the snapshot's).
  // Read from a copy: reading the screen canvas itself would make Chrome stop accelerating it.
  function screenHash() {
    const copy = document.createElement('canvas'); copy.width = scrCanvas.width; copy.height = scrCanvas.height;
    const cg = copy.getContext('2d', { willReadFrequently: true }); cg.drawImage(scrCanvas, 0, 0);
    const d = cg.getImageData(0, 0, scrCanvas.width, scrCanvas.height).data;
    let h = 0x811c9dc5;
    for (let i = 0; i < d.length; i++) { h ^= d[i]; h = Math.imul(h, 0x01000193) >>> 0; }
    return h;
  }
  return { doorHinge, chair, drawScreen, screenHash };
}

// ---- dust puffs the door kicks up (seeded positions; the spec drives their k) ----
export function buildDust(scene, set) {
  const P = set.palette, Q = set.params;
  const puffs = [];
  const r = mulberry32(99);
  for (let i = 0; i < 9; i++) {
    const m = new THREE.Mesh(new THREE.SphereGeometry(1, 20, 14), new THREE.MeshStandardMaterial({ color: P.dust, transparent: true, roughness: Q.dust.roughness, depthWrite: false }));
    m.userData = { noAO: true, kind: 'door', p: V3(RX0 + 0.05 + r() * 0.15, 0.04 + r() * 0.9 * (i % 3 === 0 ? 1 : 0.15), DOOR.z1 - 0.05 - r() * 0.75), v: V3(0.25 + r() * 0.35, 0.05 + r() * 0.15, (r() - 0.5) * 0.3), s: 0.05 + r() * 0.06 };
    scene.add(m); puffs.push(m);
  }
  return puffs;
}

// ---- lights: a warm hemisphere, the key (soft PCF shadows), a cool rim ----
export function buildLights(scene, set) {
  const P = set.palette, Q = set.params;
  scene.add(new THREE.HemisphereLight(P.hemi_sky, P.hemi_ground, Q.hemi.intensity));
  const K = Q.key;
  const key = new THREE.DirectionalLight(P.key, K.intensity);
  key.position.set(...K.pos);
  key.target.position.set(...K.target);
  key.castShadow = true;
  key.shadow.mapSize.set(K.shadow.map, K.shadow.map);
  const e = K.shadow.extent;
  Object.assign(key.shadow.camera, { left: -e, right: e, top: e, bottom: -e, near: K.shadow.near, far: K.shadow.far });
  key.shadow.bias = K.shadow.bias; key.shadow.normalBias = K.shadow.normal_bias; key.shadow.radius = K.shadow.radius;
  scene.add(key, key.target);
  const rim = new THREE.DirectionalLight(P.rim, Q.rim.intensity);
  rim.position.set(...Q.rim.pos);
  scene.add(rim);
  return { key, rim };
}
