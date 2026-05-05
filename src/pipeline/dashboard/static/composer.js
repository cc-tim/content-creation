// EditComposer: floating token chips, instruction textarea, confirm, and submit.
(function () {
  'use strict';

  var STYLE = ''
    + '#edit-mode-strip{position:fixed;bottom:0;left:0;right:0;z-index:900;padding:8px 14px;background:#111827;color:#bfdbfe;font-size:11px;border-top:1px solid #2563eb;display:none;font-family:system-ui,sans-serif;pointer-events:none}'
    + '.edit-mode-toggle{font-size:11px;padding:4px 10px;border-radius:4px;border:1px solid #2d3748;background:#1a1a2e;color:#94a3b8;cursor:pointer}.edit-mode-toggle.on{background:#1e3a5f;color:#bfdbfe;border-color:#3b82f6}'
    + 'body.edit-mode-on [data-edit-token]{cursor:crosshair;outline:1px dashed rgba(59,130,246,.35);outline-offset:2px}body.edit-mode-on [data-edit-token]:hover{outline-color:#60a5fa;background-color:rgba(59,130,246,.08)}'
    + '#edit-composer{position:fixed;right:14px;bottom:36px;z-index:950;width:min(440px,92vw);background:#0f172a;color:#e2e8f0;border:1px solid #3b82f6;border-radius:8px;padding:12px;box-shadow:0 4px 24px rgba(0,0,0,.4);font-family:system-ui,sans-serif;display:none}'
    + '#edit-composer.open{display:block}#edit-composer.collapsed{padding:8px 12px}#edit-composer .ec-collapsed-bar{display:none;align-items:center;gap:8px;cursor:pointer}#edit-composer.collapsed .ec-body{display:none}#edit-composer.collapsed .ec-collapsed-bar{display:flex}'
    + '#edit-composer .ec-chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;min-height:24px}#edit-composer .ec-chip{display:inline-flex;gap:6px;align-items:center;background:#1e293b;border:1px solid #2d3748;color:#93c5fd;padding:3px 8px;border-radius:12px;font-size:11px;font-family:monospace}#edit-composer .ec-chip-x{cursor:pointer;opacity:.65}#edit-composer .ec-chip-x:hover{opacity:1;color:#f87171}'
    + '#edit-composer textarea{width:100%;height:60px;resize:vertical;background:#0f172a;color:#e2e8f0;border:1px solid #2d3748;border-radius:4px;padding:6px 8px;font-size:12px;font-family:inherit;margin-bottom:8px}#edit-composer .ec-summary{font-size:11px;color:#94a3b8;margin-bottom:8px;min-height:14px}#edit-composer .ec-actions{display:flex;gap:6px;justify-content:flex-end}#edit-composer .ec-actions button,.ec-confirm-modal button{font-size:11px;padding:5px 12px;border-radius:4px;border:1px solid #2d3748;background:#1e293b;color:#e2e8f0;cursor:pointer}#edit-composer .ec-actions button.primary,.ec-confirm-modal button.primary{background:#1e3a5f;border-color:#3b82f6}#edit-composer .ec-actions button:disabled{opacity:.4;cursor:not-allowed}'
    + '.ec-cross-flash{outline:2px solid #3b82f6!important;outline-offset:2px!important}.ec-confirm-overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);display:flex;align-items:center;justify-content:center;z-index:1100}.ec-confirm-modal{background:#111827;border:1px solid #2d3748;border-radius:6px;padding:18px;width:min(520px,92vw);font-family:system-ui,sans-serif;color:#e2e8f0}.ec-confirm-modal h3{font-size:14px;margin:0 0 10px}.ec-confirm-list{font-size:12px;color:#cbd5e1;background:#0f172a;border:1px solid #1e293b;border-radius:4px;padding:8px 10px;margin-bottom:10px;max-height:160px;overflow:auto}.ec-confirm-cost{font-size:12px;color:#facc15;margin-bottom:10px}'
    + '@media (max-width:600px){#edit-composer{right:8px;left:8px;width:auto;bottom:30px}}';

  var state = { projectId: null, tokens: [], instruction: '', totalScenes: 0, store: null };

  function ensureStyle() {
    if (document.getElementById('ec-style')) return;
    var s = document.createElement('style');
    s.id = 'ec-style';
    s.textContent = STYLE;
    document.head.appendChild(s);
  }

  function ensureHostNode() {
    var host = document.getElementById('edit-composer');
    if (host) return host;
    host = document.createElement('div');
    host.id = 'edit-composer';
    host.innerHTML = '<div class="ec-collapsed-bar"><span class="ec-collapsed-count">(0)</span><span style="color:#94a3b8;font-size:11px">Edit composer ▲</span></div>'
      + '<div class="ec-body"><div class="ec-chips"></div><textarea class="ec-instruction" placeholder="Describe the edit"></textarea><div class="ec-summary"></div><div class="ec-actions"><button type="button" class="ec-collapse">Collapse</button><button type="button" class="ec-cancel">Cancel</button><button type="button" class="ec-submit primary">Submit</button></div></div>';
    document.body.appendChild(host);
    return host;
  }

  function ecQS(sel) {
    var host = document.getElementById('edit-composer');
    return host ? host.querySelector(sel) : null;
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  function renderChips() {
    var chipsEl = ecQS('.ec-chips');
    if (!chipsEl) return;
    chipsEl.innerHTML = '';
    if (!state.tokens.length) {
      chipsEl.innerHTML = '<span style="color:#64748b;font-size:11px">No tokens yet</span>';
      return;
    }
    state.tokens.forEach(function (raw) {
      var chip = document.createElement('span');
      chip.className = 'ec-chip';
      chip.setAttribute('data-token', raw);
      chip.innerHTML = '<span class="ec-chip-label">' + escapeHtml(raw) + '</span><span class="ec-chip-x" title="Remove">x</span>';
      chipsEl.appendChild(chip);
    });
  }

  function renderSummary() {
    var sumEl = ecQS('.ec-summary');
    if (sumEl && window.EditCostEstimate) {
      sumEl.textContent = window.EditCostEstimate.formatSummaryLine(state.tokens, state.totalScenes);
    }
    var collapsedCount = ecQS('.ec-collapsed-count');
    if (collapsedCount) collapsedCount.textContent = '(' + state.tokens.length + ')';
  }

  function persist() {
    if (!state.store) return;
    state.store.save({ tokens: state.tokens.slice(), instruction: state.instruction });
  }

  function addToken(raw) {
    if (!raw || state.tokens.indexOf(raw) >= 0) return;
    state.tokens.push(raw);
    renderChips();
    renderSummary();
    persist();
  }

  function removeToken(raw) {
    var i = state.tokens.indexOf(raw);
    if (i < 0) return;
    state.tokens.splice(i, 1);
    renderChips();
    renderSummary();
    persist();
  }

  function readTotalScenesFromDOM(projectId) {
    var strip = document.querySelector('tr[data-detail-for="' + projectId + '"] .scene-strip');
    if (!strip) return 1;
    var n = strip.querySelectorAll('.scene-chip').length;
    return n > 0 ? n : 1;
  }

  async function openForProject(projectId, totalScenes) {
    ensureStyle();
    var host = ensureHostNode();
    state.projectId = projectId;
    state.store = window.EditDraftStore.make(projectId);
    state.totalScenes = totalScenes || readTotalScenesFromDOM(projectId);
    var draft = await state.store.load();
    state.tokens = draft.tokens || [];
    state.instruction = draft.instruction || '';
    var instrEl = ecQS('.ec-instruction');
    if (instrEl) instrEl.value = state.instruction;
    renderChips();
    renderSummary();
    host.classList.add('open');
    host.classList.remove('collapsed');
  }

  function close() {
    var host = document.getElementById('edit-composer');
    if (host) host.classList.remove('open');
    if (state.store) state.store.flush();
    state.projectId = null;
    state.store = null;
    state.tokens = [];
    state.instruction = '';
  }

  function findAnnotatedElement(token) {
    var all = document.querySelectorAll('[data-edit-token]');
    for (var i = 0; i < all.length; i++) {
      if (all[i].getAttribute('data-edit-token') === token) return all[i];
    }
    return null;
  }

  function showConfirm(callback) {
    var est = window.EditCostEstimate.estimateJobCost(state.tokens, state.totalScenes);
    var rows = state.tokens.map(function (t) {
      return '<div>- ' + escapeHtml(window.EditTokens.tokenLabel(t)) + ' <span style="color:#64748b;font-family:monospace">' + escapeHtml(t) + '</span></div>';
    }).join('');
    var overlay = document.createElement('div');
    overlay.className = 'ec-confirm-overlay';
    overlay.innerHTML = '<div class="ec-confirm-modal"><h3>Confirm edit job</h3><div class="ec-confirm-list">' + rows + '</div><div style="font-size:11px;color:#94a3b8;margin-bottom:8px">Instruction</div><div class="ec-confirm-list" style="white-space:pre-wrap">' + escapeHtml(state.instruction || '(none)') + '</div><div class="ec-confirm-cost">' + (est.usd > 0 ? 'Estimated cost: $' + est.usd.toFixed(3) + '. ' : '') + (est.wideRebuild ? 'Touches more than 50% of scenes.' : '') + '</div><div class="ec-actions"><button type="button" class="ec-confirm-cancel">Cancel</button><button type="button" class="ec-confirm-ok primary">Confirm and submit</button></div></div>';
    document.body.appendChild(overlay);
    overlay.querySelector('.ec-confirm-cancel').addEventListener('click', function () {
      overlay.remove();
      callback(false);
    });
    overlay.querySelector('.ec-confirm-ok').addEventListener('click', function () {
      overlay.remove();
      callback(true);
    });
  }

  async function submit() {
    if (!state.projectId) return;
    if (!state.tokens.length) {
      alert('No tokens. Tap a scene element to add one before submitting.');
      return;
    }
    var est = window.EditCostEstimate.estimateJobCost(state.tokens, state.totalScenes);
    function doPost() {
      var btn = ecQS('.ec-submit');
      if (btn) btn.disabled = true;
      fetch('/api/jobs/' + encodeURIComponent(state.projectId) + '/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tokens: state.tokens, instruction: state.instruction }),
      }).then(function (resp) {
        if (!resp.ok) return resp.text().then(function (t) { throw new Error('submit failed: ' + resp.status + ' ' + t); });
        return resp.json();
      }).then(function (body) {
        if (state.store) state.store.clear();
        var pid = state.projectId;
        if (window.EditMode && pid) window.EditMode.setEnabled(pid, false);
        var sumEl = ecQS('.ec-summary');
        if (sumEl) sumEl.textContent = body && body.job_id ? 'Job ' + body.job_id + ' queued.' : 'Job queued.';
      }).catch(function (err) {
        if (btn) btn.disabled = false;
        alert(err.message || String(err));
      });
    }
    if (est.needsConfirm) showConfirm(function (ok) { if (ok) doPost(); });
    else doPost();
  }

  function wireHostInteractions() {
    var host = ensureHostNode();
    host.addEventListener('click', function (ev) {
      var x = ev.target.closest && ev.target.closest('.ec-chip-x');
      if (x) {
        var chip = x.closest('.ec-chip');
        if (chip) removeToken(chip.getAttribute('data-token'));
        return;
      }
      if (ev.target.closest('.ec-collapse')) {
        host.classList.toggle('collapsed');
        return;
      }
      if (ev.target.closest('.ec-collapsed-bar')) {
        host.classList.remove('collapsed');
        return;
      }
      if (ev.target.closest('.ec-cancel')) {
        if (window.EditMode && state.projectId) window.EditMode.setEnabled(state.projectId, false);
        return;
      }
      if (ev.target.closest('.ec-submit')) submit();
    });
    host.addEventListener('input', function (ev) {
      if (ev.target.classList && ev.target.classList.contains('ec-instruction')) {
        state.instruction = ev.target.value;
        persist();
      }
    });
    host.addEventListener('mouseover', function (ev) {
      var chip = ev.target.closest && ev.target.closest('.ec-chip');
      if (!chip) return;
      var match = findAnnotatedElement(chip.getAttribute('data-token'));
      if (match) match.classList.add('ec-cross-flash');
    });
    host.addEventListener('mouseout', function (ev) {
      if (!(ev.target.closest && ev.target.closest('.ec-chip'))) return;
      document.querySelectorAll('.ec-cross-flash').forEach(function (el) {
        el.classList.remove('ec-cross-flash');
      });
    });
  }

  function init() {
    ensureStyle();
    ensureHostNode();
    wireHostInteractions();
  }

  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);

  window.EditComposer = {
    openForProject: openForProject,
    close: close,
    addToken: addToken,
    removeToken: removeToken,
  };
})();
