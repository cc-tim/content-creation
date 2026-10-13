// The toy3d page API (E11): init(bank, {width, height, mode}), applyState(spec), renderState(spec)
// → PNG data URL, info(). The engine modules are ported from the frozen r7-3d snapshot in Sprint 12
// task 6; until then every call says so.
const notBuilt = () => { throw new Error('toy3d engine: not built yet (E11 Sprint 12 task 6)'); };
window.toy3d = { init: notBuilt, applyState: notBuilt, renderState: notBuilt, info: notBuilt };
window.ready = true;
