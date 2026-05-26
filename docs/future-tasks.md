# Future Tasks

Improvements and features to revisit after the v2 compose engine is stable.

## Visual & Rendering

> **Rendering capabilities are now tracked in `docs/ROADMAP.md`** (the arsenal backlog,
> owned by the `engineering-manager` subagent). The three items below are absorbed into
> roadmap epics — kept here only as cross-references. Add new rendering-capability ideas to
> the roadmap, not here. Material-acquisition and channel-brand items remain below.

- [→ ROADMAP E3] **Center-screen animated subtitles for Shorts** — Word-by-word highlight, CapCut style. → animated overlays epic.
- [→ ROADMAP E2] **Ken Burns effect for still images** — Slow pan/zoom to add motion. → programmatic animation epic.
- [→ ROADMAP E2/E6] **Transition effects between scenes** — Crossfade, fade, swipe. Partly shipped (`book-page-turn-v2`); rest → animation / dashboard-transition epics.
- [ ] **B-roll stock footage integration** — Pull from Pexels/Pixabay API when source clips are insufficient. Free, no attribution required. *(material acquisition — stays here)* — **partly shipped:** `src/pipeline/utils/gallery.py` already does tiered B-roll search (local → Pexels → Pixabay → generate); remaining work is wiring it into the compose loop as a fallback for thin source clips.
- [ ] **Social-media B-roll / footage grabber** — Pull short clips from YouTube / TikTok / Instagram Reels for use as source B-roll or reference footage. *(material acquisition — stays here, NOT the rendering ROADMAP. Sibling to the Pexels/Pixabay B-roll line above.)* **Distinct from the existing YouTube *porting* acquire stage** (`src/pipeline/stages/acquire.py:download_video`, which yt-dlp-downloads the ONE source video being ported); this is multi-source raw-clip grabbing for B-roll, but reuses the same yt-dlp dependency. Cross-links: `acquire.py:download_video` (yt-dlp pattern to copy), `utils/gallery.py` (the tiered B-roll search + `clips/` cache to extend with a social tier). Open concerns: per-platform extractor reliability (yt-dlp handles all three), licensing/source-tracking for non-stock clips, the 5–15s "used sparingly" YouTube-policy constraint. *(Idea D, INTAKE 2026-05-26.)*
- [ ] **Video templates per channel brand** — Intro animation, outro card, consistent color palette, watermark. *(channel branding — stays here)*

## Content & Knowledge

- [ ] **Knowledge enrichment pipeline** — Auto-crawl Wikipedia, news articles for Layer 1 keywords. Add facts with `source: "enrichment"`.
- [ ] **Multi-source knowledge merge** — Combine facts from multiple YouTube videos + articles into one knowledge.json for a comprehensive deep-dive video.
- [ ] **Fact verification via web search** — Auto-check facts against search results, flag contradictions.
- [ ] **Terminology glossary per series** — Consistent translation of recurring terms across videos.

## Shorts & Distribution

- [ ] **Auto-generate thumbnails** — DALL-E or extracted key frame with text overlay.
- [ ] **Shorts batch pipeline** — One command: "give me 5 Shorts from this source" → renders all.
- [ ] **Shorts A/B hook testing** — Generate 2-3 different hooks for the same Short, publish and compare CTR.
- [ ] **Cross-platform formatting** — Same Short exported for YouTube Shorts (9:16), Instagram Reels, TikTok (with watermark adjustments).

## Pipeline & Infrastructure

- [ ] **SQLite database** — Replace file-based project tracking. Enable queries across projects (which facts perform best, etc.).
- [ ] **Discovery Engine** — Automated trend monitoring + gap analysis (designed in original spec, not yet built).
- [ ] **Observability** — YouTube Analytics polling, tag × metrics correlation (designed in original spec, not yet built).
- [ ] **Publish stage** — YouTube upload with optimized metadata, synthetic content disclosure.
- [ ] **Google Cloud TTS Neural2** — Premium voice option for higher quality narration.
- [ ] **OpenAI TTS** — Highest naturalness option for special narration needs.
- [ ] **Whisper fallback** — For videos without subtitles, use OpenAI Whisper API for transcription.
- [x] **SFX asset registry / config legibility + cross-project reuse** → **migrated to `docs/ROADMAP.md` E7** (Audio arsenal & SFX legibility, 2026-05-26). Tim approved a formal audio epic, so this audio-arsenal item moved out of the idea bin into E7 (item 1) alongside the paired dashboard layer-visibility half; the EM mandate now formally covers the audio axis. *Tracked in ROADMAP E7 — do not re-add here.*

## Agent Skills

- [ ] **Interactive storyboard editor** — Rich TUI or browser-based storyboard viewer/editor.
- [ ] **Voice preview** — Generate TTS for a single scene to preview before full render.
- [ ] **Batch produce** — Process multiple URLs from a candidate list in sequence.

## Skill Management (skill-repo)

- [ ] **Project-skill migration** — Migrate `content-creation/skills/` (15 skills) into `~/skill-repo` using `skill-sync push` + `skill-sync install --scope project`. Per-skill human decision: repo-managed vs project-private. Generates `.skills.toml`. Plans A–E complete; this is the last unblocked follow-up.
- [ ] **knowledge.py `<main>` selection** (Plan A #6, low priority) — Apply `<main>` CSS selector before markdownify on `developers.openai.com`; strip `\[​\]\(#[^)]+\)` anchors on `claude.com`. Reduces noise in KNOWLEDGE/ docs.
- [ ] **Split `fetch_one` into fetch-and-hash vs write** (Plan A #7, low priority) — Eliminate mtime churn on unchanged KNOWLEDGE/ content by only writing when sha changes.
