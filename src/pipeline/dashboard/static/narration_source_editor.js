// NarrationSourceEditor — direct-action modal for per-scene narration.
//
// Flow:
//   1. Open modal for a given (project_id, scene). Modal shows current scene
//      narration text (read-only) and a source dropdown.
//   2. User picks edge | fish_audio | prerecorded.
//   3. For TTS engines: user types a voice_id; clicks Apply → POST set-source.
//   4. For prerecorded:
//        a. User taps REC, records via MediaRecorder, taps STOP.
//        b. User taps Apply.
//        c. Multipart-upload the blob → /api/narration/<id>/upload — server
//           normalizes to WAV and saves to narration_overrides/<scene>.wav.
//        d. If auto-transcribe is on: call /api/narration/<id>/transcribe;
//           show a side-by-side diff vs the storyboard's existing narration.
//           User accepts (will then POST set-source) or rejects.
//        e. Final POST: /api/narration/<id>/set-source with engine=prerecorded
//           and file=narration_overrides/<scene>.wav.
//   5. Close modal. (SSE-driven dashboard refresh lands in Plan 5; for now
//      the user re-opens the project detail row to see the change.)

(function () {
  'use strict';

  const STYLE = `
    .nse-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.7); display: flex;
      align-items: center; justify-content: center; z-index: 1000; }
    .nse-modal { background: #1a1a2e; color: #e2e8f0; border: 1px solid #2d3748;
      border-radius: 6px; padding: 18px; width: min(560px, 92vw); }
    .nse-h { font-size: 14px; font-weight: 600; margin-bottom: 10px; }
    .nse-narration { background: #0f172a; border: 1px solid #1e293b; border-radius: 4px;
      padding: 10px; font-size: 12px; color: #cbd5e1; max-height: 120px; overflow: auto;
      margin-bottom: 12px; }
    .nse-row { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
    .nse-row label { font-size: 11px; color: #94a3b8; min-width: 70px; }
    .nse-row select, .nse-row input[type="text"] {
      flex: 1; background: #0f172a; color: #e2e8f0; border: 1px solid #2d3748;
      border-radius: 4px; padding: 5px 8px; font-size: 12px; }
    .nse-rec-section { background: #0f172a; border: 1px solid #1e293b; border-radius: 4px;
      padding: 12px; margin-bottom: 10px; }
    .nse-rec-btns { display: flex; gap: 8px; align-items: center; }
    .nse-rec-btns button { font-size: 11px; padding: 5px 12px; border-radius: 4px;
      border: 1px solid #2d3748; background: #1e293b; color: #e2e8f0; cursor: pointer; }
    .nse-rec-btns button:disabled { opacity: .4; cursor: not-allowed; }
    .nse-rec-btns button.recording { background: #7f1d1d; border-color: #b91c1c; }
    .nse-timer { font-family: monospace; font-size: 12px; color: #94a3b8; }
    .nse-diff { display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
      background: #0f172a; border: 1px solid #1e293b; border-radius: 4px;
      padding: 10px; margin-bottom: 10px; font-size: 11px; }
    .nse-diff h4 { font-size: 10px; color: #64748b; margin-bottom: 4px; text-transform: uppercase; }
    .nse-diff pre { white-space: pre-wrap; color: #cbd5e1; font-family: inherit; }
    .nse-actions { display: flex; gap: 8px; justify-content: flex-end; }
    .nse-actions button { font-size: 11px; padding: 6px 14px; border-radius: 4px;
      border: 1px solid #2d3748; background: #1e293b; color: #e2e8f0; cursor: pointer; }
    .nse-actions button.primary { background: #1e3a5f; border-color: #3b82f6; }
    .nse-status { font-size: 11px; color: #94a3b8; margin-bottom: 8px; min-height: 14px; }
    .nse-status.error { color: #ef4444; }
  `;

  function ensureStyleInjected() {
    if (document.getElementById('nse-style')) return;
    const s = document.createElement('style');
    s.id = 'nse-style';
    s.textContent = STYLE;
    document.head.appendChild(s);
  }

  async function uploadRecording(projectId, scene, blob) {
    const fd = new FormData();
    fd.append('file', blob, `${scene}.webm`);
    const resp = await fetch(`/api/narration/${projectId}/upload?scene=${encodeURIComponent(scene)}`, {
      method: 'POST', body: fd,
    });
    if (!resp.ok) throw new Error(`upload failed: ${resp.status} ${await resp.text()}`);
    return await resp.json();  // { ok, path }
  }

  async function transcribeFile(projectId, scene, file, language) {
    const resp = await fetch(`/api/narration/${projectId}/transcribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene, file, language }),
    });
    if (!resp.ok) throw new Error(`transcribe failed: ${resp.status} ${await resp.text()}`);
    return (await resp.json()).transcript;
  }

  async function setSource(projectId, scene, engine, voice, file) {
    const resp = await fetch(`/api/narration/${projectId}/set-source`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene, engine, voice, file }),
    });
    if (!resp.ok) throw new Error(`set-source failed: ${resp.status} ${await resp.text()}`);
    return await resp.json();
  }

  function openEditor({ projectId, scene, narrationText, locale }) {
    ensureStyleInjected();

    const overlay = document.createElement('div');
    overlay.className = 'nse-overlay';
    overlay.innerHTML = `
      <div class="nse-modal" role="dialog" aria-modal="true">
        <div class="nse-h">Narration source · ${scene}</div>
        <div class="nse-narration">${escapeHtml(narrationText)}</div>
        <div class="nse-row">
          <label>Source</label>
          <select class="nse-engine">
            <option value="edge">Edge-TTS</option>
            <option value="fish_audio">Fish Audio</option>
            <option value="prerecorded">🎙 Prerecorded</option>
          </select>
        </div>
        <div class="nse-row nse-voice-row">
          <label>Voice ID</label>
          <input type="text" class="nse-voice" placeholder="e.g. zh-tw-default-f">
        </div>
        <div class="nse-rec-section" hidden>
          <div class="nse-rec-btns">
            <button class="nse-rec">REC</button>
            <button class="nse-stop" disabled>STOP</button>
            <button class="nse-play" disabled>Play</button>
            <span class="nse-timer">0:00</span>
          </div>
          <label style="display:block;margin-top:10px;font-size:11px;color:#94a3b8">
            <input type="checkbox" class="nse-auto-transcribe" checked>
            Auto-transcribe and show diff before applying
          </label>
        </div>
        <div class="nse-diff" hidden>
          <div><h4>Storyboard narration</h4><pre class="nse-diff-orig"></pre></div>
          <div><h4>Whisper transcript</h4><pre class="nse-diff-new"></pre></div>
        </div>
        <div class="nse-status"></div>
        <div class="nse-actions">
          <button class="nse-cancel">Cancel</button>
          <button class="nse-apply primary">Apply</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const $ = (sel) => overlay.querySelector(sel);
    const engineSel = $('.nse-engine');
    const voiceRow = $('.nse-voice-row');
    const voiceInput = $('.nse-voice');
    const recSection = $('.nse-rec-section');
    const recBtn = $('.nse-rec');
    const stopBtn = $('.nse-stop');
    const playBtn = $('.nse-play');
    const timerEl = $('.nse-timer');
    const autoTransCb = $('.nse-auto-transcribe');
    const diffSection = $('.nse-diff');
    const diffOrig = $('.nse-diff-orig');
    const diffNew = $('.nse-diff-new');
    const statusEl = $('.nse-status');
    const applyBtn = $('.nse-apply');
    const cancelBtn = $('.nse-cancel');

    let recorder = null;
    let recordedBlob = null;
    let recordedUrl = null;
    let timerHandle = null;
    let recordStart = 0;

    function setStatus(msg, isError) {
      statusEl.textContent = msg;
      statusEl.classList.toggle('error', !!isError);
    }

    function applyEngineVisibility() {
      const e = engineSel.value;
      voiceRow.hidden = (e === 'prerecorded');
      recSection.hidden = (e !== 'prerecorded');
    }
    engineSel.addEventListener('change', applyEngineVisibility);
    applyEngineVisibility();

    recBtn.addEventListener('click', async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recorder = new MediaRecorder(stream);
        const chunks = [];
        recorder.ondataavailable = (e) => chunks.push(e.data);
        recorder.onstop = () => {
          recordedBlob = new Blob(chunks, { type: 'audio/webm' });
          if (recordedUrl) URL.revokeObjectURL(recordedUrl);
          recordedUrl = URL.createObjectURL(recordedBlob);
          stream.getTracks().forEach((t) => t.stop());
          playBtn.disabled = false;
          stopBtn.disabled = true;
          recBtn.disabled = false;
          recBtn.classList.remove('recording');
        };
        recorder.start();
        recordStart = Date.now();
        timerHandle = setInterval(() => {
          const t = Math.floor((Date.now() - recordStart) / 1000);
          timerEl.textContent = `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
        }, 200);
        recBtn.disabled = true;
        recBtn.classList.add('recording');
        stopBtn.disabled = false;
        setStatus('Recording…');
      } catch (err) {
        setStatus(`Microphone access failed: ${err.message}`, true);
      }
    });

    stopBtn.addEventListener('click', () => {
      if (recorder && recorder.state !== 'inactive') recorder.stop();
      if (timerHandle) clearInterval(timerHandle);
      setStatus('Recording stopped. Press Apply to upload.');
    });

    playBtn.addEventListener('click', () => {
      if (!recordedUrl) return;
      const a = new Audio(recordedUrl);
      a.play().catch((e) => setStatus(`Playback failed: ${e.message}`, true));
    });

    cancelBtn.addEventListener('click', () => {
      if (recordedUrl) URL.revokeObjectURL(recordedUrl);
      overlay.remove();
    });

    applyBtn.addEventListener('click', async () => {
      const engine = engineSel.value;
      try {
        applyBtn.disabled = true;
        if (engine === 'prerecorded') {
          if (!recordedBlob) {
            setStatus('Record audio first.', true);
            applyBtn.disabled = false;
            return;
          }
          setStatus('Uploading & normalizing…');
          const upload = await uploadRecording(projectId, scene, recordedBlob);
          if (autoTransCb.checked) {
            setStatus('Transcribing…');
            const language = (locale || 'zh').split('-')[0];
            const transcript = await transcribeFile(projectId, scene, upload.path, language);
            diffOrig.textContent = narrationText;
            diffNew.textContent = transcript;
            diffSection.hidden = false;
            const accept = window.confirm(
              `Whisper transcript:\n\n${transcript}\n\nApply this recording? ` +
              `(The storyboard narration will be left unchanged; only narration_source is set.)`
            );
            if (!accept) {
              setStatus('Cancelled by user.');
              applyBtn.disabled = false;
              return;
            }
          }
          setStatus('Saving narration_source…');
          await setSource(projectId, scene, 'prerecorded', null, upload.path);
        } else {
          // edge / fish_audio
          const voice = voiceInput.value.trim();
          if (!voice) {
            setStatus('Voice ID is required for TTS engines.', true);
            applyBtn.disabled = false;
            return;
          }
          setStatus('Saving narration_source…');
          await setSource(projectId, scene, engine, voice, null);
        }
        setStatus('Saved. Run `pipeline compose rescene --scene ' + scene + '` to re-render.');
        setTimeout(() => overlay.remove(), 1500);
      } catch (err) {
        setStatus(err.message, true);
        applyBtn.disabled = false;
      }
    });
  }

  function escapeHtml(str) {
    return String(str || '').replace(/[&<>"]/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  // Public entry point
  window.NarrationSourceEditor = { open: openEditor };
})();
