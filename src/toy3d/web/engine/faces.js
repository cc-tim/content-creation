// toy3d face decals (E11): Animal Crossing-style faces drawn on canvases and swapped per expression,
// ported verbatim from the frozen snapshot (scene.js faces, look A). Colours from each character's
// bank palette; the shapes are the drawing.
import { THREE, canvasTex, mk, rgba } from './core.js';

export function faceCanvas(extent, draw) {
  return canvasTex(1024, 1024, (g) => {
    const k = 1024 / (2 * extent);
    g.setTransform(k, 0, 0, -k, 512, 512); // head units, y up, front view
    g.lineCap = 'round'; g.lineJoin = 'round';
    draw(g);
  }, { repeat: [1, 1] });
}
export function faceShell(radius, extent, tex, parent, roughness) {
  const g = new THREE.SphereGeometry(radius, 72, 54, Math.PI / 2 - 1.25, 2.5, Math.PI / 2 - 1.15, 2.3);
  const p = g.attributes.position, uv = g.attributes.uv;
  for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i) / (2 * extent) + 0.5, p.getY(i) / (2 * extent) + 0.5);
  const m = mk(g, new THREE.MeshStandardMaterial({ map: tex, transparent: true, depthWrite: false, roughness,
    polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 }), parent, null, { cast: false, recv: true });
  m.userData.noAO = true;
  return m;
}
export const ell = (g, x, y, rx, ry, fill) => { g.beginPath(); g.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2); g.fillStyle = fill; g.fill(); };
export const line = (g, pts, w, col) => { g.beginPath(); g.moveTo(...pts[0]); for (const p of pts.slice(1)) g.lineTo(...p); g.lineWidth = w; g.strokeStyle = col; g.stroke(); };
const blush = (g, x, y, hex, a) => {
  const gr = g.createRadialGradient(x, y, 0, x, y, 0.06);
  gr.addColorStop(0, rgba(hex, a)); gr.addColorStop(1, rgba(hex, 0));
  g.save(); g.translate(x, y); g.scale(1, 0.62); g.translate(-x, -y); g.fillStyle = gr; g.fillRect(x - 0.07, y - 0.07, 0.14, 0.14); g.restore();
};

const EYE_X = 0.135, EYE_Y = -0.02; // Tim's eye centres (glasses rings share them)
export const TIM_EYE = { x: EYE_X, y: EYE_Y };

// Tim: neutral, blink, shock (decals tim_neutral, tim_blink, tim_shock)
export function timFaces(pal, prm) {
  const INK = pal.ink, BROW = pal.brow, MOUTH = pal.mouth, BLUSH = prm.blush;
  const smile = (g) => {
    g.beginPath(); g.moveTo(-0.036, -0.142); g.quadraticCurveTo(0, -0.185, 0.036, -0.142);
    g.lineWidth = 0.014; g.strokeStyle = MOUTH; g.stroke();
  };
  return {
    tim_neutral: faceCanvas(0.42, (g) => {
      for (const s of [-1, 1]) {
        ell(g, s * EYE_X, EYE_Y, 0.029, 0.043, INK);
        ell(g, s * EYE_X + 0.009, EYE_Y + 0.017, 0.0085, 0.0085, pal.glint);
        line(g, [[s * 0.108, 0.118], [s * 0.168, 0.116]], 0.019, BROW);
        blush(g, s * 0.215, -0.115, pal.blush, BLUSH);
      }
      smile(g);
    }),
    tim_blink: faceCanvas(0.42, (g) => {
      for (const s of [-1, 1]) {
        g.beginPath(); g.moveTo(s * EYE_X - 0.03, EYE_Y + 0.004); g.quadraticCurveTo(s * EYE_X, EYE_Y - 0.022, s * EYE_X + 0.03, EYE_Y + 0.004);
        g.lineWidth = 0.013; g.strokeStyle = INK; g.stroke();
        line(g, [[s * 0.108, 0.118], [s * 0.168, 0.116]], 0.019, BROW);
        blush(g, s * 0.215, -0.115, pal.blush, BLUSH);
      }
      smile(g);
    }),
    tim_shock: faceCanvas(0.42, (g) => {
      // gloom lines on the (high) forehead
      g.save(); g.translate(0, 0.215); g.scale(1, 0.5);
      const gr = g.createRadialGradient(0, 0, 0, 0, 0, 0.2);
      gr.addColorStop(0, rgba(pal.gloom, prm.gloom)); gr.addColorStop(1, rgba(pal.gloom, 0));
      g.fillStyle = gr; g.fillRect(-0.2, -0.2, 0.4, 0.4); g.restore();
      for (const x of [-0.09, -0.045, 0, 0.045, 0.09]) line(g, [[x, 0.232], [x, 0.188 + Math.abs(x) * 0.22]], 0.011, pal.gloom_lines);
      for (const s of [-1, 1]) {
        ell(g, s * EYE_X, EYE_Y, 0.052, 0.056, pal.shock_eye);
        g.beginPath(); g.ellipse(s * EYE_X, EYE_Y, 0.052, 0.056, 0, 0, Math.PI * 2); g.lineWidth = 0.009; g.strokeStyle = INK; g.stroke();
        ell(g, s * EYE_X, EYE_Y - 0.004, 0.014, 0.016, INK);
        line(g, [[s * 0.1, 0.162], [s * 0.172, 0.146]], 0.019, BROW);
      }
      ell(g, 0, -0.165, 0.04, 0.052, pal.shock_mouth);
      g.save(); g.beginPath(); g.ellipse(0, -0.165, 0.04, 0.052, 0, 0, Math.PI * 2); g.clip();
      ell(g, 0, -0.205, 0.032, 0.026, pal.shock_tongue); g.restore();
    }),
  };
}

// The lioness: stern, blink (decals lion_stern, lion_blink), and her mouth on the muzzle
export function lionFaces(pal) {
  const eyes = (blinking) => faceCanvas(0.36, (g) => {
    for (const s of [-1, 1]) {
      const cx = s * 0.13, cy = 0.04;
      g.save(); g.translate(cx, cy - 0.035); g.scale(1, 0.55); ell(g, 0, 0, 0.055, 0.055, pal.eye_white); g.restore();
      line(g, [[s * 0.162, cy - 0.012], [s * 0.198, cy - 0.03]], 0.011, pal.ink);
      if (blinking) line(g, [[cx - 0.035, cy + 0.003], [cx + 0.035, cy - 0.003 * s]], 0.014, pal.ink);
      else {
        g.save(); g.beginPath(); // stern: flat lid, inner corner lower
        g.moveTo(s * 0.08, cy + 0.006); g.lineTo(s * 0.185, cy + 0.03); g.lineTo(s * 0.185, cy - 0.1); g.lineTo(s * 0.08, cy - 0.1); g.closePath(); g.clip();
        ell(g, cx, cy - 0.004, 0.032, 0.038, pal.ink);
        g.restore();
        ell(g, cx - 0.009, cy - 0.012, 0.0075, 0.0075, pal.glint);
      }
      line(g, [[s * 0.205, 0.128], [s * 0.078, 0.082]], 0.026, pal.brow);
    }
  });
  return { lion_stern: eyes(false), lion_blink: eyes(true) };
}
export function lionMouth(pal) {
  return faceCanvas(1.0, (g) => { // drawn in the muzzle's unit-sphere space
    line(g, [[0, 0.3], [0, -0.1]], 0.07, pal.mouth);
    g.beginPath(); g.moveTo(-0.5, -0.52); g.quadraticCurveTo(-0.22, -0.06, 0, -0.12); g.quadraticCurveTo(0.22, -0.06, 0.5, -0.52);
    g.lineWidth = 0.07; g.strokeStyle = pal.mouth; g.stroke();
    for (const s of [-1, 1]) for (const [x, y] of [[0.32, 0.12], [0.5, 0.18], [0.42, -0.02], [0.6, 0.04], [0.55, -0.16]]) ell(g, s * x, y, 0.035, 0.035, pal.whisker_dots);
  });
}
