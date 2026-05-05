// SSE client for /api/sse/<project_id>.
(function (global) {
  'use strict';

  function noop() {}

  function subscribe(projectId, handlers) {
    handlers = handlers || {};
    var url = '/api/sse/' + encodeURIComponent(projectId);
    var es = null;
    var closed = false;
    var backoff = 1000;
    var maxBackoff = 30000;
    var reconnectTimer = null;

    function emitError(err) {
      (handlers.onError || noop)(err);
    }

    function scheduleReconnect() {
      if (closed) return;
      reconnectTimer = global.setTimeout(function () {
        reconnectTimer = null;
        backoff = Math.min(backoff * 2, maxBackoff);
        open();
      }, backoff);
    }

    function parseEvent(ev, callback) {
      try {
        callback(JSON.parse(ev.data || '{}'));
      } catch (err) {
        emitError(err);
      }
    }

    function open() {
      if (closed) return;
      es = new global.EventSource(url);
      es.addEventListener('files_changed', function (ev) {
        parseEvent(ev, function (data) {
          (handlers.onFilesChanged || noop)(data.paths || []);
        });
      });
      es.addEventListener('job_status', function (ev) {
        parseEvent(ev, function (data) {
          (handlers.onJobStatus || noop)(data);
        });
      });
      es.onopen = function () {
        backoff = 1000;
      };
      es.onerror = function (err) {
        emitError(err);
        if (es) es.close();
        scheduleReconnect();
      };
    }

    open();

    return {
      close: function () {
        closed = true;
        if (reconnectTimer) global.clearTimeout(reconnectTimer);
        if (es) es.close();
      },
    };
  }

  global.SSEClient = { subscribe: subscribe };
})(window);
