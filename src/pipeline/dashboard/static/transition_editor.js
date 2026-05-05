// TransitionEditor - direct-action modal for setting/clearing per-seam transitions.

(function () {
  'use strict';

  var STYLE = ''
    + '.te-overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);'
    + 'display:flex;align-items:center;justify-content:center;z-index:1000;'
    + 'font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}'
    + '.te-modal{background:#1a1a2e;color:#e2e8f0;border:1px solid #2d3748;'
    + 'border-radius:6px;padding:18px;width:min(520px,92vw);box-sizing:border-box;'
    + 'box-shadow:0 20px 60px rgba(0,0,0,.45)}'
    + '.te-h{font-size:14px;font-weight:600;margin:0 0 10px}'
    + '.te-row{display:flex;gap:8px;align-items:center;margin-bottom:10px}'
    + '.te-row label{font-size:11px;color:#94a3b8;min-width:94px}'
    + '.te-row select,.te-row input[type="number"],.te-row input[type="file"]{'
    + 'flex:1;min-width:0;background:#0f172a;color:#e2e8f0;border:1px solid #2d3748;'
    + 'border-radius:4px;padding:5px 8px;font-size:12px;box-sizing:border-box}'
    + '.te-row input[type="file"]{padding:4px 8px}'
    + '.te-note{font-size:11px;color:#64748b;margin:-2px 0 10px 102px;line-height:1.35}'
    + '.te-status{font-size:11px;color:#94a3b8;margin-bottom:8px;min-height:14px;line-height:1.35}'
    + '.te-status.error{color:#ef4444}'
    + '.te-actions{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}'
    + '.te-actions button{font-size:11px;padding:6px 14px;border-radius:4px;'
    + 'border:1px solid #2d3748;background:#1e293b;color:#e2e8f0;cursor:pointer}'
    + '.te-actions button.primary{background:#1e3a5f;border-color:#3b82f6}'
    + '.te-actions button.danger{background:#7f1d1d;border-color:#b91c1c}'
    + '.te-actions button:disabled{opacity:.45;cursor:not-allowed}'
    + '@media (max-width:520px){.te-row{display:block}.te-row label{display:block;margin-bottom:4px}'
    + '.te-note{margin-left:0}.te-actions{justify-content:stretch}.te-actions button{flex:1}}';

  var TRANSITION_STYLES = ['none', 'fade', 'page-turn', 'slide', 'wipe'];

  function ensureStyle() {
    if (document.getElementById('te-style')) return;
    var el = document.createElement('style');
    el.id = 'te-style';
    el.textContent = STYLE;
    document.head.appendChild(el);
  }

  function requestJson(url, options) {
    return fetch(url, options).then(function (resp) {
      return resp.text().then(function (text) {
        var payload = null;
        if (text) {
          try {
            payload = JSON.parse(text);
          } catch (err) {
            payload = text;
          }
        }
        if (!resp.ok) {
          throw new Error(formatError(resp.status, payload));
        }
        return payload;
      });
    });
  }

  function formatError(status, payload) {
    var detail = '';
    if (payload && typeof payload === 'object' && payload.detail) {
      detail = payload.detail;
    } else if (typeof payload === 'string') {
      detail = payload;
    }
    return 'Request failed: ' + status + (detail ? ' ' + detail : '');
  }

  function listSfx() {
    return requestJson('/api/sfx/list').then(function (items) {
      return Array.isArray(items) ? items : [];
    }).catch(function () {
      return [];
    });
  }

  function uploadSfx(file) {
    var fd = new FormData();
    fd.append('file', file, file.name);
    return requestJson('/api/sfx/upload', {
      method: 'POST',
      body: fd,
    }).then(function (payload) {
      if (!payload || !payload.path) {
        throw new Error('Upload succeeded without a returned path.');
      }
      return payload.path;
    });
  }

  function setTransition(projectId, body) {
    return requestJson('/api/transition/' + encodeURIComponent(projectId) + '/set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  function clearTransition(projectId, body) {
    return requestJson('/api/transition/' + encodeURIComponent(projectId) + '/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  function optionHtml(value, label) {
    return '<option value="' + escapeAttr(value) + '">' + escapeHtml(label) + '</option>';
  }

  function renderSfxOptions(items, selected) {
    var html = optionHtml('', 'silent');
    items.forEach(function (item) {
      var path = item && item.path ? item.path : String(item || '');
      var name = item && item.name ? item.name : path;
      if (!path) return;
      html += optionHtml(path, name);
    });
    return html.replace(
      'value="' + escapeAttr(selected || '') + '"',
      'value="' + escapeAttr(selected || '') + '" selected'
    );
  }

  function setBusy(buttons, busy) {
    buttons.forEach(function (button) {
      button.disabled = !!busy;
    });
  }

  function updateLocalTransitionChips(fromScene, toScene, summary, cleared) {
    var root = document;
    var selectors = [
      '[data-transition-from="' + cssEscape(fromScene) + '"][data-transition-to="' + cssEscape(toScene) + '"]',
      '[data-from-scene="' + cssEscape(fromScene) + '"][data-to-scene="' + cssEscape(toScene) + '"]',
      '[data-scene="' + cssEscape(fromScene) + '"][data-edit-token="@' + cssEscape(fromScene) + '/transition"]',
    ];
    selectors.forEach(function (selector) {
      var nodes;
      try {
        nodes = root.querySelectorAll(selector);
      } catch (err) {
        nodes = [];
      }
      Array.prototype.forEach.call(nodes, function (node) {
        node.dataset.transitionState = cleared ? 'clear' : 'set';
        node.title = summary || (cleared ? 'Transition cleared' : 'Transition set');
      });
    });
  }

  function openEditor(projectId, fromScene, toScene) {
    if (projectId && typeof projectId === 'object') {
      fromScene = projectId.fromScene;
      toScene = projectId.toScene;
      projectId = projectId.projectId;
    }
    projectId = String(projectId || '');
    fromScene = String(fromScene || '');
    toScene = String(toScene || '');
    if (!projectId || !fromScene || !toScene) {
      throw new Error('TransitionEditor.open requires projectId, fromScene, and toScene.');
    }

    ensureStyle();

    var overlay = document.createElement('div');
    overlay.className = 'te-overlay';
    overlay.innerHTML = ''
      + '<div class="te-modal" role="dialog" aria-modal="true" aria-labelledby="te-title">'
      + '<div class="te-h" id="te-title">Transition ' + escapeHtml(fromScene) + ' to ' + escapeHtml(toScene) + '</div>'
      + '<div class="te-row"><label for="te-style-select">Style</label>'
      + '<select id="te-style-select" class="te-style"></select></div>'
      + '<div class="te-row"><label for="te-duration-input">Duration (sec)</label>'
      + '<input id="te-duration-input" class="te-duration" type="number" min="0" max="3" step="0.05" value="0.5"></div>'
      + '<div class="te-row"><label for="te-sfx-select">SFX</label>'
      + '<select id="te-sfx-select" class="te-sfx">' + optionHtml('', 'silent') + '</select></div>'
      + '<div class="te-row"><label for="te-sfx-upload">Upload custom</label>'
      + '<input id="te-sfx-upload" class="te-sfx-upload" type="file" accept="audio/*"></div>'
      + '<div class="te-note">Apply writes storyboard.json. Clear removes this transition and leaves a hard cut.</div>'
      + '<div class="te-status" role="status" aria-live="polite"></div>'
      + '<div class="te-actions">'
      + '<button type="button" class="te-cancel">Cancel</button>'
      + '<button type="button" class="te-clear danger">Clear</button>'
      + '<button type="button" class="te-apply primary">Apply</button>'
      + '</div></div>';

    document.body.appendChild(overlay);

    var modal = overlay.querySelector('.te-modal');
    var styleSelect = overlay.querySelector('.te-style');
    var durationInput = overlay.querySelector('.te-duration');
    var sfxSelect = overlay.querySelector('.te-sfx');
    var uploadInput = overlay.querySelector('.te-sfx-upload');
    var statusEl = overlay.querySelector('.te-status');
    var cancelBtn = overlay.querySelector('.te-cancel');
    var clearBtn = overlay.querySelector('.te-clear');
    var applyBtn = overlay.querySelector('.te-apply');
    var actionButtons = [cancelBtn, clearBtn, applyBtn];

    styleSelect.innerHTML = TRANSITION_STYLES.map(function (style) {
      return optionHtml(style, style);
    }).join('');
    styleSelect.value = 'page-turn';

    function setStatus(message, isError) {
      statusEl.textContent = message || '';
      statusEl.classList.toggle('error', !!isError);
    }

    function close() {
      document.removeEventListener('keydown', onKeydown);
      overlay.remove();
    }

    function onKeydown(event) {
      if (event.key === 'Escape') close();
    }

    function refreshSfx(selected) {
      return listSfx().then(function (items) {
        sfxSelect.innerHTML = renderSfxOptions(items, selected);
        sfxSelect.value = selected || '';
      });
    }

    styleSelect.addEventListener('change', function () {
      if (styleSelect.value === 'none') {
        durationInput.value = '0';
        sfxSelect.value = '';
      } else if ((parseFloat(durationInput.value) || 0) <= 0) {
        durationInput.value = '0.5';
      }
    });

    uploadInput.addEventListener('change', function () {
      var file = uploadInput.files && uploadInput.files[0];
      if (!file) return;
      setBusy(actionButtons, true);
      setStatus('Uploading ' + file.name + '...');
      uploadSfx(file).then(function (path) {
        return refreshSfx(path).then(function () {
          setStatus('Uploaded ' + file.name + '.');
        });
      }).catch(function (err) {
        setStatus(err.message, true);
      }).then(function () {
        setBusy(actionButtons, false);
        uploadInput.value = '';
      });
    });

    cancelBtn.addEventListener('click', close);
    overlay.addEventListener('click', function (event) {
      if (event.target === overlay) close();
    });
    modal.addEventListener('click', function (event) {
      event.stopPropagation();
    });

    applyBtn.addEventListener('click', function () {
      var style = styleSelect.value;
      var duration = parseFloat(durationInput.value);
      if (!isFinite(duration) || duration < 0) {
        setStatus('Duration must be zero or greater.', true);
        return;
      }
      setBusy(actionButtons, true);
      setStatus('Applying transition...');
      setTransition(projectId, {
        from_scene: fromScene,
        to_scene: toScene,
        style: style,
        duration_sec: duration,
        sfx: sfxSelect.value || null,
      }).then(function (payload) {
        var summary = payload && payload.summary ? payload.summary : 'Transition applied.';
        setStatus(summary);
        updateLocalTransitionChips(fromScene, toScene, summary, false);
        setTimeout(close, 900);
      }).catch(function (err) {
        setStatus(err.message, true);
        setBusy(actionButtons, false);
      });
    });

    clearBtn.addEventListener('click', function () {
      setBusy(actionButtons, true);
      setStatus('Clearing transition...');
      clearTransition(projectId, {
        from_scene: fromScene,
        to_scene: toScene,
      }).then(function (payload) {
        var summary = payload && payload.summary ? payload.summary : 'Transition cleared.';
        setStatus(summary);
        updateLocalTransitionChips(fromScene, toScene, summary, true);
        setTimeout(close, 900);
      }).catch(function (err) {
        setStatus(err.message, true);
        setBusy(actionButtons, false);
      });
    });

    document.addEventListener('keydown', onKeydown);
    refreshSfx('').then(function () {
      setStatus('');
    });
    styleSelect.focus();
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === 'function') {
      return window.CSS.escape(String(value));
    }
    return String(value).replace(/["\\]/g, '\\$&');
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      }[ch];
    });
  }

  function escapeAttr(value) {
    return escapeHtml(value);
  }

  window.TransitionEditor = {
    open: openEditor,
  };
}());
