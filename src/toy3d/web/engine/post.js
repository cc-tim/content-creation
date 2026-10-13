// toy3d renderer and post (E11): the locked look A, ported verbatim from the frozen snapshot
// (scene.js renderer + post): MSAA half-float target, GTAO with Poisson denoise (fur shells, face
// decals, puffs and sprites excluded), a NaN guard, mild bloom, the output transform, then the
// vignette grade. Every value comes from the bank style (style.yaml).
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { mulberry32 } from './core.js';

const TONE = { neutral: THREE.NeutralToneMapping };
const SHADOWS = { pcf: THREE.PCFShadowMap };

export function makeRenderer(style, W, H) {
  const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1);
  renderer.setSize(W, H);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = SHADOWS[style.shadows.type];
  renderer.toneMapping = TONE[style.tone.mapping];
  renderer.toneMappingExposure = style.tone.exposure;
  document.body.appendChild(renderer.domElement);
  // A shader that fails to compile or link fails the frame: three would log it and draw on without it.
  renderer.debug.onShaderError = (gl, program, vs, fs) => {
    const log = [gl.getProgramInfoLog(program), gl.getShaderInfoLog(vs), gl.getShaderInfoLog(fs)].filter(Boolean).join(' | ');
    throw new Error(`toy3d: a shader failed to compile or link: ${log.trim().slice(0, 400)}`);
  };
  return renderer;
}

export function environment(scene, renderer, style) {
  const E = style.environment;
  if (!E.room) return;
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), E.sigma).texture;
  scene.environmentIntensity = E.intensity;
}

export function makeComposer(renderer, scene, camera, style, W, H) {
  const Po = style.post;
  const rt = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: Po.samples });
  const composer = new EffectComposer(renderer, rt);
  composer.setPixelRatio(1); composer.setSize(W, H);
  composer.addPass(new RenderPass(scene, camera));
  // The Poisson denoise's noise texture draws from Math.random when the pass is built: draw it from
  // the snapshot's own stream position, so the AO grain is the snapshot's whatever was built first.
  const N = Po.denoise.noise, saved = Math.random, r = mulberry32(N.seed);
  for (let i = 0; i < N.skip; i++) r();
  Math.random = r;
  let gtao;
  try { gtao = new GTAOPass(scene, camera, W, H); } finally { Math.random = saved; }
  const G = Po.gtao, D = Po.denoise;
  gtao.updateGtaoMaterial({ radius: G.radius, distanceExponent: G.distance_exponent, thickness: G.thickness, scale: G.scale, samples: G.samples });
  gtao.updatePdMaterial({ lumaPhi: D.luma_phi, depthPhi: D.depth_phi, normalPhi: D.normal_phi, radius: D.radius, rings: D.rings, samples: D.samples });
  gtao.blendIntensity = G.blend;
  const baseOverride = gtao.overrideVisibility.bind(gtao);
  gtao.overrideVisibility = function () {
    baseOverride();
    scene.traverse((o) => { if (o.userData.noAO || o.isSprite) o.visible = false; });
  };
  composer.addPass(gtao);
  composer.addPass(new ShaderPass({
    uniforms: { tDiffuse: { value: null } },
    vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
    fragmentShader: 'uniform sampler2D tDiffuse; varying vec2 vUv; void main(){ vec4 c = texture2D(tDiffuse, vUv); if (any(isnan(c)) || any(isinf(c))) c = vec4(0.0, 0.0, 0.0, 1.0); gl_FragColor = c; }',
  }));
  const B = Po.bloom;
  composer.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), B.strength, B.radius, B.threshold));
  composer.addPass(new OutputPass());
  const Gr = Po.grade;
  const grade = new ShaderPass({
    uniforms: { tDiffuse: { value: null }, vig: { value: Gr.vignette }, grain: { value: Gr.grain }, warm: { value: Gr.warm }, frame: { value: 0 }, res: { value: new THREE.Vector2(W, H) } },
    vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
    fragmentShader: `
      uniform sampler2D tDiffuse; uniform float vig, grain, warm, frame; uniform vec2 res; varying vec2 vUv;
      float hash(vec2 p){ p = fract(p * vec2(443.897, 441.423)); p += dot(p, p.yx + 19.19); return fract((p.x + p.y) * p.x); }
      void main(){
        vec3 c = texture2D(tDiffuse, vUv).rgb;
        c = mix(c, c * vec3(1.035, 1.0, 0.93) + vec3(0.012, 0.008, 0.0), warm);
        vec2 d = vUv - 0.5; d.x *= 1.7778;
        c *= 1.0 - vig * smoothstep(0.35, 1.05, length(d));
        c += (hash(floor(vUv * res) + frame * 17.31) - 0.5) * grain;
        gl_FragColor = vec4(c, 1.0);
      }`,
  });
  composer.addPass(grade);
  return { composer, grade, gtao };
}
