// Shared dashboard SSE wiring for index.html and verify.html.
(function (global) {
  'use strict';

  var subs = {};
  var latestStatus = {};

  function noop() {}

  function cssEscape(value) {
    if (global.CSS && typeof global.CSS.escape === 'function') {
      return global.CSS.escape(String(value));
    }
    return String(value).replace(/["\\]/g, '\\$&');
  }

  function badgeHostsFor(projectId) {
    return document.querySelectorAll(
      '[data-project-host][data-project-id="' + cssEscape(projectId) + '"]'
    );
  }

  function applyJobStatus(projectId, status) {
    latestStatus[projectId] = status || null;
    Array.prototype.forEach.call(badgeHostsFor(projectId), function (host) {
      var badge = global.InflightBadge.mount(host, projectId);
      if (status && (status.status === 'queued' || status.status === 'running')) {
        badge.setStatus(status);
      } else {
        badge.setStatus(null);
      }
    });
  }

  function sync(projectId) {
    applyJobStatus(projectId, latestStatus[projectId] || null);
  }

  function open(projectId, opts) {
    opts = opts || {};
    if (subs[projectId]) {
      sync(projectId);
      return subs[projectId];
    }
    subs[projectId] = global.SSEClient.subscribe(projectId, {
      onFilesChanged: opts.onFilesChanged || noop,
      onJobStatus: function (status) {
        applyJobStatus(projectId, status);
        if (opts.onJobStatus) opts.onJobStatus(status);
        if (status && status.status !== 'queued' && status.status !== 'running') {
          renderRecentMutations(projectId);
        }
      },
      onError: opts.onError || function (err) {
        console.warn('dashboard sse', projectId, err);
      },
    });
    sync(projectId);
    return subs[projectId];
  }

  function close(projectId) {
    if (!subs[projectId]) return;
    subs[projectId].close();
    delete subs[projectId];
    applyJobStatus(projectId, null);
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function renderEmpty(host, message) {
    host.innerHTML = '<h4>Recent mutations</h4><div class="recent-mut-empty">' +
      escapeHtml(message) + '</div>';
  }

  async function renderRecentMutations(projectId) {
    var host = document.querySelector(
      '.recent-mutations[data-project-id="' + cssEscape(projectId) + '"]'
    );
    if (!host) return;
    var resp;
    try {
      resp = await fetch('/api/projects/' + encodeURIComponent(projectId) + '/recent-mutations');
    } catch (err) {
      renderEmpty(host, 'recent mutations unavailable');
      return;
    }
    if (resp.status === 404) {
      renderEmpty(host, 'recent mutations unavailable');
      return;
    }
    if (!resp.ok) {
      renderEmpty(host, 'could not load recent mutations');
      return;
    }
    var rows = await resp.json().catch(function () { return []; });
    if (!Array.isArray(rows) || rows.length === 0) {
      renderEmpty(host, 'no mutations yet');
      return;
    }
    host.innerHTML = '<h4>Recent mutations</h4>' + rows.map(function (row) {
      return '<div class="recent-mut-row">' +
        '<span class="recent-mut-time">' + escapeHtml((row.timestamp || '').slice(11, 19)) + '</span>' +
        '<span class="recent-mut-cmd" title="' + escapeHtml(row.summary || row.command || '') + '">' +
          escapeHtml(row.summary || row.command || '') +
        '</span>' +
        '<button class="recent-mut-revert" type="button" data-mut-id="' +
          escapeHtml(row.mutation_id || '') + '">Revert</button>' +
      '</div>';
    }).join('');
    Array.prototype.forEach.call(host.querySelectorAll('.recent-mut-revert'), function (button) {
      button.addEventListener('click', function () {
        var mutationId = button.getAttribute('data-mut-id');
        if (!mutationId) return;
        fetch('/api/jobs/' + encodeURIComponent(projectId) + '/' +
          encodeURIComponent(mutationId) + '/revert', { method: 'POST' })
          .then(function () { renderRecentMutations(projectId); })
          .catch(function () {});
      });
    });
  }

  global.DashboardSSE = {
    open: open,
    close: close,
    sync: sync,
    renderRecentMutations: renderRecentMutations,
    _badgeHostsFor: badgeHostsFor,
  };
})(window);
