# Recording a voice sample for CosyVoice2

## Target

A single 30–60 second WAV clip that captures your natural narration voice.
This becomes the reference audio for zero-shot cloning.

## Equipment

- Any decent USB mic or headset (Blue Yeti, Shure MV7, AirPods Pro all work).
- A quiet room (no fan, no TV, no AC hum).
- `arecord` on Linux, QuickTime Player on macOS, or Audacity cross-platform.

## Procedure

1. Run `scripts/install_cosyvoice.sh` once per workstation.
2. Pick a unique voice id, e.g. `tim-zhtw`, and prepare an empty file:
   `voices/cloned/tim-zhtw.wav`.
3. Read the script below at your natural cadence. Do not rush.
4. Save the file as **16 kHz mono PCM WAV** (CosyVoice2 will resample internally
   but 16 kHz avoids quality surprises).
5. Register the voice:

   ```bash
   uv run pipeline voice add \
     --id tim-zhtw \
     --engine cosyvoice \
     --locale zh-TW \
     --reference voices/cloned/tim-zhtw.wav \
     --reference-text "大家好，歡迎來到今天的影片。..." \
     --display-name "Tim (zh-TW clone)"
   ```

6. Smoke test:

   ```bash
   uv run pipeline voice test tim-zhtw --text "測試一二三" --out /tmp/tim_test.wav
   ```

## Reference script (zh-TW, ~45 seconds)

> 大家好，歡迎來到今天的影片。今天我想跟各位分享一個非常有趣的研究。
> 在人工智慧快速發展的時代，我們常常聽到像是 GPT、Claude 這些名字。
> 但你知道嗎？讓 AI 真正能夠寫出完整應用程式的關鍵，其實不在於模型本身，
> 而在於整個系統的設計。從規劃、執行到評估，每一個環節都不能少。
> 那麼，接下來就讓我們一起來看看，研究員到底是怎麼做到的？

Use this exact text as `--reference-text` — CosyVoice2 matches the prosody of
the recording to the text, so the two must line up.
