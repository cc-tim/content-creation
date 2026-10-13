// The toy3d page API (E11): init(bank, {width, height, mode}) builds the world from the bank once;
// applyState(spec) poses it (and returns its named nodes, Layer B); renderState(spec) poses and
// renders it to a PNG data URL; info() names the WebGL renderer. Python (toy3d.runtime) drives it.
import { buildWorld } from './world.js';

let world = null;
window.toy3d = {
  init(bank, opts) {
    if (world) throw new Error('toy3d: init once per page');
    world = buildWorld(bank, opts);
    return true;
  },
  applyState(spec) { return need().applyState(spec); },
  renderState(spec) { return need().renderState(spec); },
  info() { return need().info(); },
};
function need() {
  if (!world) throw new Error('toy3d: call init(bank, {width, height, mode}) first');
  return world;
}
window.ready = true;
