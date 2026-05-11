// EditMode: global toggle, sticky strip, and click-to-mint registry.
(function () {
  'use strict';

  var STORAGE_PREFIX = 'edit-mode:';
  var activeProjectId = null;
  var enabled = false;

  function storageKey(projectId) { return STORAGE_PREFIX + projectId; }

  function isEnabledForProject(projectId) {
    try {
      return localStorage.getItem(storageKey(projectId)) === '1';
    } catch (e) {
      return false;
    }
  }

  function setEnabled(projectId, on) {
    activeProjectId = projectId;
    enabled = !!on;
    try {
      if (enabled) localStorage.setItem(storageKey(projectId), '1');
      else localStorage.removeItem(storageKey(projectId));
    } catch (e) {
      // Private browsing can reject localStorage.
    }
    document.body.classList.toggle('edit-mode-on', enabled);
    updateStickyStrip();
    if (window.EditComposer) {
      if (enabled) window.EditComposer.openForProject(projectId);
      else window.EditComposer.close();
    }
    updateToggleButtons();
  }

  function toggle(projectId) {
    setEnabled(projectId, !(enabled && activeProjectId === projectId));
  }

  function updateToggleButtons() {
    var btns = document.querySelectorAll('.edit-mode-toggle');
    btns.forEach(function (b) {
      var pid = b.getAttribute('data-project-id');
      var on = enabled && pid === activeProjectId;
      b.classList.toggle('on', on);
      b.textContent = on ? 'Edit mode: ON' : 'Edit mode';
    });
  }

  function ensureStickyStrip() {
    var strip = document.getElementById('edit-mode-strip');
    if (!strip) {
      strip = document.createElement('div');
      strip.id = 'edit-mode-strip';
      strip.textContent = 'Edit mode: tap any scene element to open edit popup. Esc exits.';
      document.body.appendChild(strip);
    }
    return strip;
  }

  function updateStickyStrip() {
    var strip = ensureStickyStrip();
    strip.style.display = enabled ? '' : 'none';
  }

  function onClickCapture(ev) {
    if (!enabled) return;
    if (!ev.target || !ev.target.closest) return;
    var match = ev.target.closest('[data-edit-token]');
    if (!match) return;
    if (ev.target.closest('.edit-mode-toggle')) return;
    if (ev.target.closest('#edit-composer')) return;
    var token = match.getAttribute('data-edit-token');
    if (!token) return;
    if (window.EditComposer && activeProjectId) {
      window.EditComposer.openEditPopup(token, true);
      ev.preventDefault();
      ev.stopPropagation();
    }
  }

  function onKeydown(ev) {
    if (enabled && ev.key === 'Escape' && activeProjectId) {
      setEnabled(activeProjectId, false);
    }
  }

  function attach(projectId) {
    if (isEnabledForProject(projectId)) setEnabled(projectId, true);
    else updateToggleButtons();
  }

  function init() {
    document.addEventListener('click', onClickCapture, true);
    document.addEventListener('keydown', onKeydown);
    ensureStickyStrip();
    updateStickyStrip();
    updateToggleButtons();
  }

  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);

  window.EditMode = {
    toggle: toggle,
    setEnabled: setEnabled,
    attach: attach,
    isEnabled: function () { return enabled; },
    activeProjectId: function () { return activeProjectId; },
  };
})();
