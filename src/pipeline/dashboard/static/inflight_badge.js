// In-flight job badge driven by dashboard job_status SSE events.
(function (global) {
  'use strict';

  function escapeAttr(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function badgeHtml(state) {
    if (!state || !state.job_id) return '';
    if (state.status !== 'queued' && state.status !== 'running') return '';
    var status = state.status === 'queued' ? 'queued' : 'running';
    var label = state.status === 'queued' ? 'Queued' : 'Editing';
    var jobId = String(state.job_id);
    return (
      '<span class="inflight-badge ' + status + '">' +
        '<span class="inflight-dot"></span>' +
        '<span>' + label + '</span>' +
        '<span class="inflight-jid">' + escapeAttr(jobId.slice(0, 6)) + '</span>' +
        '<button class="inflight-cancel" type="button" title="Cancel this job" ' +
          'data-job-id="' + escapeAttr(jobId) + '">x</button>' +
      '</span>'
    );
  }

  function mountInflightBadge(host, projectId) {
    if (!host) return { setStatus: function () {} };
    host.classList.add('inflight-host');

    function setStatus(state) {
      host.innerHTML = badgeHtml(state);
      var cancel = host.querySelector('.inflight-cancel');
      if (!cancel) return;
      cancel.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var jobId = cancel.getAttribute('data-job-id');
        if (!jobId) return;
        fetch('/api/jobs/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(jobId) + '/cancel', {
          method: 'POST',
        }).catch(function () {});
      });
    }

    return { setStatus: setStatus };
  }

  global.InflightBadge = {
    mount: mountInflightBadge,
    _badgeHtml: badgeHtml,
  };
})(window);
