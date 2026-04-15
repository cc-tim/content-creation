# Recording your own voice per scene

This project supports a hybrid narration workflow: generate a draft with
Edge-TTS, then iteratively replace individual scenes with your own
recordings. You can re-run `produce` at any time; scenes with recordings
use your voice, the rest use Edge.

## One-time setup

1. Create a recording directory under `voices/prerecorded/`:
   ```bash
   mkdir -p voices/prerecorded/tim-zhtw
   ```

2. Register a `prerecorded` voice profile:
   ```bash
   uv run pipeline voice add \
     --id tim-zhtw \
     --engine prerecorded \
     --locale zh-TW \
     --recording-dir voices/prerecorded/tim-zhtw \
     --fallback-voice zh-TW-default-f \
     --display-name "Tim (zh-TW, pre-recorded)"
   ```

3. Verify:
   ```bash
   uv run pipeline voice list
   ```

## Recording loop

1. Produce a draft (Edge fills every scene):
   ```bash
   uv run pipeline produce --url <video-url> --locale zh-TW \
     --voice tim-zhtw --no-subtitles
   ```

2. See what still needs recording:
   ```bash
   uv run pipeline storyboard recordings --voice tim-zhtw \
     --work-dir output/projects/<project_id>
   ```

3. For each scene you want to re-record, read the exact text:
   ```bash
   uv run pipeline storyboard show --scene hook_1 \
     --work-dir output/projects/<project_id>
   ```

4. Record that scene. Recommended settings: 16 kHz mono WAV.
   Save as `voices/prerecorded/tim-zhtw/hook_1.wav`.

5. Re-run `produce` with the same `--project-id` and `--start-from tts`:
   ```bash
   uv run pipeline produce --url <video-url> --locale zh-TW \
     --voice tim-zhtw --no-subtitles \
     --project-id <project_id> --start-from tts
   ```

6. Iterate scene by scene. `storyboard recordings` shows progress.

## When text drifts

If you hand-edit `storyboard.json` (or re-run `direct`), a scene's
narration may change after you already recorded it. The engine compares
the live narration to the snapshot `<scene_id>.txt` saved at record time:

- If they match → recording is used silently.
- If they differ → a `prerecorded.stale_recording` warning prints and the
  recording is used anyway. `storyboard recordings` shows `status: stale`.

To refresh, re-record the scene. The snapshot is rewritten on next run.

## Orphans

A file in the recording directory that has no matching scene id in the
storyboard is an orphan. `storyboard recordings` lists orphans separately.
Delete them when you're confident they're no longer needed.

## Equipment

Any decent USB mic or headset works. Record in a quiet room. The pipeline
transcodes WAV/MP3/M4A input to MP3 automatically.
