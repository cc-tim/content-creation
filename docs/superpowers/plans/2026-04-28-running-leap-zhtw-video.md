# 助跑起跳 — zh-TW Parenting Video Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce an 8–10 min all-image zh-TW parenting video from the TED talk "What kids know about motivation (and we don't)" using a hand-crafted 24-scene storyboard — no source clips, OpenAI image generation.

**Architecture:** Run pipeline phase 1 (acquire → analyze → direct) to create the project dir and knowledge graph; replace the LLM-generated storyboard with our canonical hand-crafted version; resume from TTS onward. All 24 scenes use `generated_image` visual type with `image_tier: premium` (OpenAI gpt-image-1).

**Tech Stack:** uv, edge-tts (zh-TW-YunJheNeural), OpenAI gpt-image-1 via gen-image.py, FFmpeg, Claude Haiku (proofread)

**Spec:** `docs/superpowers/specs/2026-04-28-running-leap-zhtw-parenting-design.md`

---

### Task 1: Run Phase 1 Pipeline (acquire → analyze → direct)

**Files:**
- Creates: `output/projects/<ID>/context.json`
- Creates: `output/projects/<ID>/knowledge.json`
- Creates: `output/projects/<ID>/storyboard.json` *(will be replaced in Task 2)*

- [ ] **Step 1: Run phase 1**

```bash
uv run pipeline produce \
  --url "https://www.youtube.com/watch?v=fdDJub69Hnk" \
  --locale zh-TW \
  --niche parenting
```

The pipeline will run acquire → analyze → direct, then **pause at the human review gate** and print something like:

```
--- HUMAN REVIEW GATE ---
  uv run pipeline produce --url ... --project-id 1234567890 --start-from tts
```

- [ ] **Step 2: Note the project ID from the printed resume command**

The pipeline prints the exact `--project-id <NUMBER>` in the resume command. Copy that number — it is your `<PROJECT_ID>` for all later tasks.

- [ ] **Step 3: Press Ctrl+C to stop the paused pipeline**

The human review gate blocks waiting for input. Ctrl+C here is safe — phase 1 is complete.

- [ ] **Step 4: Verify project structure**

```bash
ls output/projects/<PROJECT_ID>/
```

Expected output includes: `context.json  knowledge.json  storyboard.json  source/`

---

### Task 2: Replace Storyboard with Canonical 24-Scene Version

**Files:**
- Overwrite: `output/projects/<PROJECT_ID>/storyboard.json`

- [ ] **Step 1: Write the canonical storyboard.json**

Replace `<PROJECT_ID>` below and run (or write using the Write tool):

Save the following as `output/projects/<PROJECT_ID>/storyboard.json`:

```json
{
  "version": "2.0",
  "format": "storyboard",
  "target_duration_sec": 528,
  "aspect_ratio": "16:9",
  "title": "孩子不是在逃避，他正在準備起飛",
  "theme": {
    "background": "#faf5ef",
    "text_color": "#2d2b4e",
    "accent": "#6b62c5",
    "secondary_bg": "#f0e8d8",
    "font": "Noto Sans CJK TC",
    "image_style": "pencil sketch illustration, warm cream background, soft charcoal lines with gentle watercolor color washes, soft blue and coral and sage green accents, hand-drawn style, simple composition, no text in image"
  },
  "scenes": [
    {
      "id": "s1",
      "section": "hook",
      "narration": "台灣家庭的餐桌旁，孩子盯著課本，緩緩把它推到一旁。父母站在身後，忍不住開口：「快點，你還有好多題沒寫！」",
      "narration_est_sec": 15,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, Taiwanese child sitting at dining table staring at open textbook slowly pushing it aside, parent standing behind with worried expression, warm lamp light, cream background, soft charcoal lines with watercolor washes, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s2",
      "section": "hook",
      "narration": "你有沒有這樣的時刻？孩子明明有能力，就是不肯動手。你越催，他越不動。你開始懷疑：是懶？是逃避？還是根本不在乎？",
      "narration_est_sec": 16,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, Taiwanese parent sitting alone at kitchen table, hands folded, looking uncertain and reflective, soft warm lamp light, cream background, gentle charcoal lines with soft watercolor, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s3",
      "section": "hook",
      "narration": "但如果你的催促，正好打斷了他最重要的一步呢？",
      "narration_est_sec": 10,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, parent's hand reaching out mid-air toward a child visible in background, paused in hesitation, tension in the air, cream background, soft charcoal lines, minimal composition, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 1.0
    },
    {
      "id": "s4",
      "section": "concept",
      "narration": "想像你走在山路上，遇到一條小溪。要跨過去，你會怎麼做？",
      "narration_est_sec": 12,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, person standing at edge of a gentle narrow stream on a mountain trail, looking at it and considering how to jump across, simple nature scene, cream background, soft charcoal lines with sage green watercolor washes, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s5",
      "section": "concept",
      "narration": "溪流越寬，你退得越遠——不是因為你怕，是因為你需要足夠的助跑距離。孩子面對挑戰，也是一樣的道理。",
      "narration_est_sec": 16,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, figure taking a running leap across a wider stream, motion lines showing momentum, feet leaving ground mid-jump, simple outdoor scene, cream background, soft charcoal lines with soft blue watercolor sky, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s6",
      "section": "concept",
      "narration": "這個動作，叫做助跑起跳。是孩子天生內建的動力機制。每一次他們「退後」，都是在找到起跑點，準備飛越眼前的挑戰。",
      "narration_est_sec": 18,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, child with arms spread wide mid-leap over a small hurdle or stream, joyful focused expression, motion lines, cream background, soft charcoal lines with coral and blue watercolor accents, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s7",
      "section": "example_piano",
      "narration": "小欣坐在鋼琴旁的地板上，雙臂交叉，說什麼都不肯練習。",
      "narration_est_sec": 12,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, young girl sitting on floor next to upright piano, arms crossed stubbornly, looking away from piano, soft blue accent on clothing, cream background, soft charcoal lines with watercolor washes, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s8",
      "section": "example_piano",
      "narration": "媽媽在廚房裡深吸一口氣。補習費那麼貴，請了老師，買了琴——你就坐在那裡？",
      "narration_est_sec": 14,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, mother standing in kitchen doorway, eyes closed taking a deep breath, hands on counter, slight tension, piano barely visible in background room, cream background, soft charcoal lines with warm coral watercolor, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s9",
      "section": "example_piano",
      "narration": "但那天傍晚，媽媽路過客廳，聽到了琴聲。小欣一個人坐在琴椅上，輕輕地、一遍又一遍地練著那首曲子。",
      "narration_est_sec": 18,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, evening scene, young girl sitting alone at piano bench playing softly, gentle lamp light, peaceful expression, mother visible in doorway watching quietly with soft surprise, cream background, warm coral and blue watercolor accents, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s10",
      "section": "example_math",
      "narration": "另一個孩子，面對一張數學練習卷，突然睜大眼睛說：「我要爆炸了！爆炸了！砰！」",
      "narration_est_sec": 14,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, second-grade girl sitting at desk staring at math worksheet with wide panicked eyes and open mouth, pencil in hand, papers slightly scattered, playful energy, cream background, soft charcoal lines with coral watercolor accents, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s11",
      "section": "example_math",
      "narration": "然後她從椅子上跳下來，像一隻青蛙一樣，繞著桌子跳了一圈，又爬回椅子上。",
      "narration_est_sec": 14,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, girl mid-leap frog-jumping around a table, arms and legs spread wide, delighted chaotic energy, chair pushed aside behind her, cream background, soft charcoal lines with sage green and coral watercolor, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s12",
      "section": "example_math",
      "narration": "她不是在鬧，她在充電。一次青蛙跳，換回一道數學題。做完全部題目的時間？其實沒有比坐著硬撐更長。",
      "narration_est_sec": 18,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, same girl sitting calmly back at desk, pencil in hand, calm focused expression, completed math worksheet visible in front of her, small smile, cream background, soft charcoal lines with blue watercolor, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s13",
      "section": "example_classroom",
      "narration": "課堂上，老師問了一個問題。小明知道答案，但他縮進椅背，頭微微低下，沒有舉手。",
      "narration_est_sec": 16,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, classroom scene, boy sinking lower in his seat shrinking back, head slightly down, other students around him with raised hands, teacher at chalkboard in background, cream background, soft charcoal lines with watercolor washes, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s14",
      "section": "example_classroom",
      "narration": "那天晚上回到房間，他反覆練習那個答案，小聲地自己說了好幾遍。",
      "narration_est_sec": 13,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, boy sitting alone in bedroom at night, soft lamp light, lips moving as he practices speaking quietly to himself, books open around him, calm focused expression, cream background, soft charcoal lines with blue watercolor night tones, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s15",
      "section": "example_classroom",
      "narration": "隔天，老師又問了類似的問題。這一次，小明的手舉起來了。",
      "narration_est_sec": 12,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, classroom scene, same boy's hand raised confidently and high, slight proud smile, teacher looking at him with a welcoming expression, cream background, soft charcoal lines with warm coral and blue watercolor accents, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s16",
      "section": "science",
      "narration": "三個孩子，三種不同的方式，做的是同一件事——在挑戰面前先退一步，讓信心追上來，再起跳。信心，是助跑跑出來的。",
      "narration_est_sec": 20,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, three small vignette scenes arranged side by side: girl sitting by piano, girl frog-leaping around table, boy raising hand in class, all connected by a gentle flowing line, cream background, soft charcoal lines with blue coral and sage watercolor accents, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s17",
      "section": "actionable",
      "narration": "第一步：觀察。找找看，他有沒有偷瞄那個大滑梯？孩子在「逃避」的同時，往往還是在盯著目標看。",
      "narration_est_sec": 17,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, child playing on a small slide glancing sideways with curious eyes at a tall water slide in the distance, parent sitting on bench watching calmly, cream background, soft charcoal lines with sage green watercolor, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s18",
      "section": "actionable",
      "narration": "第二步：等待。你不需要成為他的動力，他的動力已經在了。你的工作，是不要擋在他的助跑路線上。",
      "narration_est_sec": 17,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, parent sitting on bench with hands relaxed in lap, calm trusting expression, child playing independently in background, parent deliberately not intervening, open space between them, cream background, soft charcoal lines with warm watercolor, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s19",
      "section": "actionable",
      "narration": "第三步：說出來。當他完成的時候，告訴他你看見了什麼——「你知道自己需要什麼，你找到方法了。」",
      "narration_est_sec": 18,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, parent kneeling to child's eye level, gentle hand on child's shoulder, speaking softly, child looking up attentively, warm connection, cream background, soft charcoal lines with sage green and coral watercolor accents, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s20",
      "section": "payoff",
      "narration": "這句話的力量，不是讚美，是鏡子——讓孩子看見自己的能力是真實的，不是靠外力給的。說完那句話，你會看見他的臉，從一點點不確定，變成一點點相信自己。",
      "narration_est_sec": 24,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, close-up of child's face, expression shifting from slight uncertainty to a quiet proud small smile, parent's gentle hand barely visible at edge of frame, warm soft light on face, cream background, soft charcoal lines with warm coral watercolor, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s21",
      "section": "risk",
      "narration": "如果在他還沒準備好時強迫起跳——最好的結果是勉強服從，最壞的是讓他開始覺得自己很爛。信心越低，下次需要的助跑距離就越長。我們以為在推他，其實是在讓那條溪流，變得更寬。",
      "narration_est_sec": 26,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, parent behind child urging them toward edge of a wide stream the child is not ready to jump, child's body language tense and shrinking back, anxious expression, the stream looking wider and more daunting, cream background, soft charcoal lines, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s22",
      "section": "reframe",
      "narration": "孩子不是在逃避。他正在準備起飛。",
      "narration_est_sec": 9,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, child in triumphant mid-leap over a wide stream, arms spread wide, determined focused expression, motion lines showing speed, simple nature setting, cream background with soft blue and coral watercolor sky, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 1.5
    },
    {
      "id": "s23",
      "section": "close",
      "narration": "父母能給孩子最好的禮物，不是永遠在旁邊催促，而是讓他知道：就算他退後幾步，你還是在那裡，你相信他。",
      "narration_est_sec": 18,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, parent and child sitting together on floor, leaning against each other reading a book side by side, soft lamp light, peaceful unhurried intimate moment, no rush, cream background, warm coral and blue watercolor accents, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 0.5
    },
    {
      "id": "s24",
      "section": "close",
      "narration": "下次孩子退後，先停下來想一想——他是在逃避，還是在助跑？",
      "narration_est_sec": 14,
      "visual": {
        "type": "generated_image",
        "image_tier": "premium",
        "prompt": "pencil sketch, silhouette of child taking a joyful running leap upward, arms spread like wings, soaring forward, parent watching from behind with a soft proud smile, simple open landscape, cream background with soft blue sky and coral horizon watercolor, hand-drawn style, no text"
      },
      "overlay": null,
      "pause_after_sec": 2.0
    }
  ]
}
```

- [ ] **Step 2: Verify scene count**

```bash
python3 -c "
import json
d = json.load(open('output/projects/<PROJECT_ID>/storyboard.json'))
print('Scenes:', len(d['scenes']))
print('Title:', d['title'])
print('First scene:', d['scenes'][0]['id'], '—', d['scenes'][0]['narration'][:30])
print('Last scene:', d['scenes'][-1]['id'], '—', d['scenes'][-1]['narration'][:30])
"
```

Expected: `Scenes: 24`

- [ ] **Step 3: Resume the paused terminal (or close it — it's already done its job)**

If the pipeline terminal is still paused at the human review gate, press Ctrl+C to stop it. Phase 1 is complete.

---

### Task 3: Proofread the Storyboard

**Files:**
- Reads/modifies: `output/projects/<PROJECT_ID>/storyboard.json`

- [ ] **Step 1: Run proofreader**

```bash
uv run pipeline proofread run --project-id <PROJECT_ID>
```

Read the output. If issues are found:

- [ ] **Step 2: Apply fixes (if any issues found)**

```bash
uv run pipeline proofread run --project-id <PROJECT_ID> --apply
```

If no issues found, skip this step.

---

### Task 4: Run TTS

**Files:**
- Creates: `output/projects/<PROJECT_ID>/audio/s1.mp3` … `s24.mp3`

- [ ] **Step 1: Run TTS stage**

```bash
uv run pipeline produce \
  --url "https://www.youtube.com/watch?v=fdDJub69Hnk" \
  --project-id <PROJECT_ID> \
  --locale zh-TW \
  --niche parenting \
  --start-from tts \
  --skip-review
```

Expected: 24 audio files generated in `output/projects/<PROJECT_ID>/audio/`

- [ ] **Step 2: Verify audio files**

```bash
ls output/projects/<PROJECT_ID>/audio/ | wc -l
```

Expected: `24`

- [ ] **Step 3: Spot-check one audio file**

```bash
ffprobe -v quiet -show_entries format=duration output/projects/<PROJECT_ID>/audio/s1.mp3 2>&1 | grep duration
```

Expected: a duration in seconds (typically 10–26s matching narration length).

---

### Task 5: Run Compose

**Files:**
- Creates: `output/projects/<PROJECT_ID>/compose/scenes/s1_final.mp4` … `s24_final.mp4`
- Creates: `output/projects/<PROJECT_ID>/compose/final_zh-TW_subtitles_no_overlay.mp4`

**Note:** Image generation is the slow step — 24 scenes × OpenAI gpt-image-1 ≈ 24 API calls. Each call takes ~20–40s. Total: 8–16 min for image generation alone. This is expected.

- [ ] **Step 1: Run compose stage**

```bash
uv run pipeline produce \
  --url "https://www.youtube.com/watch?v=fdDJub69Hnk" \
  --project-id <PROJECT_ID> \
  --locale zh-TW \
  --niche parenting \
  --start-from compose \
  --skip-review
```

Monitor output for image generation progress (one log line per scene).

- [ ] **Step 2: If a specific scene's image fails, re-render just that scene**

If a scene fails image generation and falls back to a text card:

```bash
uv run pipeline compose rescene --project-id <PROJECT_ID> --scene <SCENE_ID>
```

Then re-burn:

```bash
uv run pipeline compose reburn --project-id <PROJECT_ID>
```

- [ ] **Step 3: Verify final video exists**

```bash
ls -lh output/projects/<PROJECT_ID>/compose/final_zh-TW_subtitles_no_overlay.mp4
```

Expected: file exists, size > 50MB typically for 8–10 min video.

---

### Task 6: Review and Lock Preferred Variant

**Files:**
- Reads: `output/projects/<PROJECT_ID>/compose/`

- [ ] **Step 1: Start dashboard to review video**

```bash
./scripts/start-dashboard.sh
```

Open the tunnel URL in a browser and navigate to the project. Watch the full video and check:
- All 24 scenes render as sketch illustrations (not text card fallbacks)
- Narration audio is clear and paced well
- Total duration is 8–10 min
- Emotional arc feels right: tension → concept → examples → action → reframe → close

- [ ] **Step 2: If any scene image is a text card fallback (solid color bg), re-render it**

Identify which scenes have fallback by watching, then:

```bash
uv run pipeline compose rescene --project-id <PROJECT_ID> --scene s<N>
uv run pipeline compose reburn --project-id <PROJECT_ID>
```

- [ ] **Step 3: Lock the preferred variant**

```bash
uv run pipeline compose set-variant --project-id <PROJECT_ID> --variant subtitles_no_overlay
```

- [ ] **Step 4: Commit project ID to a note**

```bash
echo "Running Leap project ID: <PROJECT_ID>" >> output/projects/README.md
```

---

### Task 7: Generate Metadata

**Files:**
- Creates: `output/projects/<PROJECT_ID>/metadata.json`

- [ ] **Step 1: Show current metadata**

```bash
uv run pipeline metadata show --work-dir output/projects/<PROJECT_ID>
```

If metadata.json exists and looks good, proceed. If not, regenerate:

- [ ] **Step 2: Regenerate metadata (if needed)**

```bash
uv run pipeline metadata regenerate --work-dir output/projects/<PROJECT_ID>
```

- [ ] **Step 3: Review and edit title/description**

The title should match or be close to: `孩子不是在逃避，他正在準備起飛`

```bash
uv run pipeline metadata set title="孩子不是在逃避，他正在準備起飛" \
  --work-dir output/projects/<PROJECT_ID>
```

---

### Notes

**OpenAI image cost estimate:** 24 scenes × $0.133/image = ~$3.19 for this video. Within budget.

**If an image looks off-style** (not sketch-like), edit the scene's `prompt` in storyboard.json and run:
```bash
uv run pipeline compose rescene --project-id <PROJECT_ID> --scene s<N>
uv run pipeline compose reburn --project-id <PROJECT_ID>
```

**Image cache:** Gen-image.py caches by prompt hash in `~/.claude/media-cache/`. If you re-render a scene with the same prompt, it hits cache — no API call.

**Revert OpenAI after this project:** No code was changed. `image_tier: premium` is set per-scene in storyboard.json, so no revert needed.
