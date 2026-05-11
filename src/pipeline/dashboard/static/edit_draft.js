// EditDraftStore: debounced persistence for per-project edit_draft.json.
(function () {
  'use strict';

  var DEBOUNCE_MS = 400;

  function makeStore(projectId) {
    var saveTimer = null;
    var pendingPayload = null;

    async function load() {
      var resp = await fetch('/api/jobs/' + encodeURIComponent(projectId) + '/draft');
      if (!resp.ok) return { tokens: [], instruction: '' };
      var data = await resp.json();
      if (data.wrapperChips && typeof data.wrapperChips === 'object' && !Array.isArray(data.wrapperChips)) {
        return { wrapperChips: Object.assign({}, data.wrapperChips) };
      }
      return {
        tokens: Array.isArray(data.tokens) ? data.tokens.slice() : [],
        instruction: typeof data.instruction === 'string' ? data.instruction : '',
        wrapperChips: {},
      };
    }

    function save(payload) {
      pendingPayload = payload;
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(flush, DEBOUNCE_MS);
    }

    async function flush() {
      saveTimer = null;
      if (!pendingPayload) return;
      var payload = pendingPayload;
      pendingPayload = null;
      try {
        await fetch('/api/jobs/' + encodeURIComponent(projectId) + '/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      } catch (err) {
        console.warn('draft save failed', err);
      }
    }

    async function clear() {
      if (saveTimer) {
        clearTimeout(saveTimer);
        saveTimer = null;
      }
      pendingPayload = null;
      try {
        await fetch('/api/jobs/' + encodeURIComponent(projectId) + '/draft', { method: 'DELETE' });
      } catch (err) {
        console.warn('draft clear failed', err);
      }
    }

    return { load: load, save: save, flush: flush, clear: clear };
  }

  window.EditDraftStore = { make: makeStore };
})();
