// EditComposer: wrapper chip workflow with edit popup.
(function () {
  'use strict';

  var STYLE = ''
    + '#edit-mode-strip{position:fixed;bottom:0;left:0;right:0;z-index:900;padding:8px 14px;background:#111827;color:#bfdbfe;font-size:11px;border-top:1px solid #2563eb;display:none;font-family:system-ui,sans-serif;pointer-events:none}'
    + '.edit-mode-toggle{font-size:11px;padding:4px 10px;border-radius:4px;border:1px solid #2d3748;background:#1a1a2e;color:#94a3b8;cursor:pointer}.edit-mode-toggle.on{background:#1e3a5f;color:#bfdbfe;border-color:#3b82f6}'
    + 'body.edit-mode-on [data-edit-token]{cursor:crosshair;outline:1px dashed rgba(59,130,246,.35);outline-offset:2px}body.edit-mode-on [data-edit-token]:hover{outline-color:#60a5fa;background-color:rgba(59,130,246,.08)}'
    + '#edit-composer{position:fixed;right:14px;bottom:36px;z-index:950;width:min(440px,92vw);background:#0f172a;color:#e2e8f0;border:1px solid #3b82f6;border-radius:8px;padding:12px;box-shadow:0 4px 24px rgba(0,0,0,.4);font-family:system-ui,sans-serif;display:none}'
    + '#edit-composer.open{display:block}#edit-composer.collapsed{padding:8px 12px}#edit-composer .ec-collapsed-bar{display:none;align-items:center;gap:8px;cursor:pointer}#edit-composer.collapsed .ec-body{display:none}#edit-composer.collapsed .ec-collapsed-bar{display:flex}'
    + '#edit-composer .ec-wrapper-chips{display:flex;flex-direction:column;gap:6px;margin-bottom:8px;min-height:24px}#edit-composer .ec-wrapper-chip{display:flex;align-items:center;gap:6px;background:#1e293b;border:1px solid #2d3748;color:#cbd5e1;padding:8px 12px;border-radius:6px;font-size:11px;font-family:monospace;cursor:pointer;transition:background .1s,border-color .1s}#edit-composer .ec-wrapper-chip:hover{background:#1e3a5f;border-color:#3b82f6}#edit-composer .ec-chip-token{color:#93c5fd;flex-shrink:0}#edit-composer .ec-chip-instruction{color:#cbd5e1;flex:1;overflow:hidden;text-overflow:ellipsis}#edit-composer .ec-actions{display:flex;gap:6px;justify-content:flex-end}#edit-composer .ec-actions button{font-size:11px;padding:5px 12px;border-radius:4px;border:1px solid #2d3748;background:#1e293b;color:#e2e8f0;cursor:pointer}#edit-composer .ec-actions button.primary{background:#1e3a5f;border-color:#3b82f6}#edit-composer .ec-actions button:disabled{opacity:.4;cursor:not-allowed}'
    + '.ec-edit-overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);display:flex;align-items:center;justify-content:center;z-index:1100}.ec-edit-modal{background:#111827;border:1px solid #2d3748;border-radius:6px;padding:18px;width:min(520px,92vw);font-family:system-ui,sans-serif;color:#e2e8f0}.ec-edit-modal h3{font-size:14px;margin:0 0 10px;color:#93c5fd;font-family:monospace}.ec-edit-modal .ec-instruction-field{width:100%;height:80px;resize:vertical;background:#0f172a;color:#e2e8f0;border:1px solid #2d3748;border-radius:4px;padding:8px;font-size:12px;font-family:inherit;margin-bottom:10px}.ec-edit-modal .ec-edit-actions{display:flex;gap:6px;justify-content:flex-end}.ec-edit-modal button{font-size:11px;padding:6px 12px;border-radius:4px;border:1px solid #2d3748;background:#1e293b;color:#e2e8f0;cursor:pointer}.ec-edit-modal button.primary{background:#1e3a5f;border-color:#3b82f6}.ec-edit-modal button.danger{color:#f87171}.ec-cross-flash{outline:2px solid #3b82f6!important;outline-offset:2px!important}'
    + '@media (max-width:600px){#edit-composer{right:8px;left:8px;width:auto;bottom:30px}}';

  var state = { projectId: null, wrapperChips: {}, store: null, editingToken: null };

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
      + '<div class="ec-body"><div class="ec-wrapper-chips"></div><div class="ec-actions"><button type="button" class="ec-collapse">Collapse</button><button type="button" class="ec-copy">Copy</button><button type="button" class="ec-cancel">Cancel</button><button type="button" class="ec-submit primary">Submit</button></div></div>';
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

  function renderWrapperChips() {
    var chipsEl = ecQS('.ec-wrapper-chips');
    if (!chipsEl) return;
    chipsEl.innerHTML = '';
    var tokens = Object.keys(state.wrapperChips);
    if (!tokens.length) {
      chipsEl.innerHTML = '<span style="color:#64748b;font-size:11px">No tokens yet. Tap an element in edit mode.</span>';
      return;
    }
    tokens.forEach(function (token) {
      var instruction = state.wrapperChips[token];
      var chip = document.createElement('div');
      chip.className = 'ec-wrapper-chip';
      chip.setAttribute('data-token', token);
      chip.innerHTML = '<span class="ec-chip-token">' + escapeHtml(token) + '</span><span class="ec-chip-instruction">' + escapeHtml(instruction) + '</span>';
      chipsEl.appendChild(chip);
    });
    var collapsedCount = ecQS('.ec-collapsed-count');
    if (collapsedCount) collapsedCount.textContent = '(' + tokens.length + ')';
  }

  function persist() {
    if (!state.store) return;
    state.store.save({ wrapperChips: state.wrapperChips });
  }

  async function openForProject(projectId) {
    ensureStyle();
    var host = ensureHostNode();
    state.projectId = projectId;
    state.store = window.EditDraftStore.make(projectId);
    var draft = await state.store.load();
    state.wrapperChips = draft.wrapperChips || {};
    renderWrapperChips();
    host.classList.add('open');
    host.classList.remove('collapsed');
  }

  function close() {
    var host = document.getElementById('edit-composer');
    if (host) host.classList.remove('open');
    if (state.store) state.store.flush();
    state.projectId = null;
    state.store = null;
    state.wrapperChips = {};
    state.editingToken = null;
  }

  function openEditPopup(token, isNew) {
    state.editingToken = token;
    var instruction = state.wrapperChips[token] || '';
    var overlay = document.createElement('div');
    overlay.className = 'ec-edit-overlay';
    overlay.innerHTML = '<div class="ec-edit-modal"><h3>' + escapeHtml(token) + '</h3>'
      + '<textarea class="ec-instruction-field" placeholder="Enter instruction (required)">' + escapeHtml(instruction) + '</textarea>'
      + '<div class="ec-edit-actions">'
      + '<button type="button" class="ec-edit-cancel">Cancel</button>'
      + (isNew ? '' : '<button type="button" class="ec-edit-remove danger">Remove</button>')
      + '<button type="button" class="ec-edit-ok primary">Ok</button>'
      + '</div></div>';
    document.body.appendChild(overlay);
    var instrField = overlay.querySelector('.ec-instruction-field');
    instrField.focus();
    instrField.select();
    overlay.querySelector('.ec-edit-cancel').addEventListener('click', function () {
      overlay.remove();
      state.editingToken = null;
    });
    if (!isNew) {
      overlay.querySelector('.ec-edit-remove').addEventListener('click', function () {
        delete state.wrapperChips[token];
        renderWrapperChips();
        persist();
        overlay.remove();
        state.editingToken = null;
      });
    }
    overlay.querySelector('.ec-edit-ok').addEventListener('click', function () {
      var text = instrField.value.trim();
      if (!text) {
        alert('Instruction cannot be empty');
        return;
      }
      state.wrapperChips[token] = text;
      renderWrapperChips();
      persist();
      overlay.remove();
      state.editingToken = null;
    });
    instrField.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        overlay.remove();
        state.editingToken = null;
      }
    });
  }

  function generatePrompt() {
    var tokens = Object.keys(state.wrapperChips);
    if (!tokens.length) {
      return '';
    }
    var lines = [
      'Project ID: ' + state.projectId,
      '',
      'Edit context:',
    ];
    tokens.forEach(function (token) {
      lines.push('- ' + token + ': ' + state.wrapperChips[token]);
    });
    return lines.join('\n');
  }

  function copyPrompt() {
    var tokens = Object.keys(state.wrapperChips);
    if (!tokens.length) {
      alert('No tokens to copy. Add at least one edit.');
      return;
    }
    var prompt = generatePrompt();
    navigator.clipboard.writeText(prompt).then(function () {
      var btn = ecQS('.ec-copy');
      if (btn) {
        var orig = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(function () { btn.textContent = orig; }, 2000);
      }
    }).catch(function (err) {
      alert('Copy failed: ' + (err.message || String(err)));
    });
  }

  async function submit() {
    if (!state.projectId) return;
    var tokens = Object.keys(state.wrapperChips);
    if (!tokens.length) {
      alert('No tokens. Tap a scene element to add one before submitting.');
      return;
    }
    var btn = ecQS('.ec-submit');
    if (btn) btn.disabled = true;
    var payload = {};
    tokens.forEach(function (token) {
      payload[token] = state.wrapperChips[token];
    });
    fetch('/api/jobs/' + encodeURIComponent(state.projectId) + '/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(function (resp) {
      if (!resp.ok) return resp.text().then(function (t) { throw new Error('submit failed: ' + resp.status + ' ' + t); });
      return resp.json();
    }).then(function (body) {
      if (state.store) state.store.clear();
      var pid = state.projectId;
      if (window.EditMode && pid) window.EditMode.setEnabled(pid, false);
    }).catch(function (err) {
      if (btn) btn.disabled = false;
      alert(err.message || String(err));
    });
  }

  function wireHostInteractions() {
    var host = ensureHostNode();
    host.addEventListener('click', function (ev) {
      var chip = ev.target.closest('.ec-wrapper-chip');
      if (chip) {
        var token = chip.getAttribute('data-token');
        openEditPopup(token, false);
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
      if (ev.target.closest('.ec-copy')) {
        copyPrompt();
        return;
      }
      if (ev.target.closest('.ec-cancel')) {
        if (window.EditMode && state.projectId) window.EditMode.setEnabled(state.projectId, false);
        return;
      }
      if (ev.target.closest('.ec-submit')) submit();
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
    openEditPopup: openEditPopup,
  };
})();
