# Future Tasks

Improvements and features to revisit after the v2 compose engine is stable.

## Visual & Rendering

- [ ] **Center-screen animated subtitles for Shorts** — Word-by-word highlight, CapCut style. Significantly improves Shorts engagement. Requires custom subtitle renderer instead of FFmpeg burn-in.
- [ ] **Ken Burns effect for still images** — Slow pan/zoom on generated images and still frames to add motion. FFmpeg zoompan filter.
- [ ] **Transition effects between scenes** — Crossfade, fade-to-black, swipe. Currently hard cuts only.
- [ ] **B-roll stock footage integration** — Pull from Pexels/Pixabay API when source clips are insufficient. Free, no attribution required.
- [ ] **Video templates per channel brand** — Intro animation, outro card, consistent color palette, watermark.

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

## Agent Skills

- [ ] **Interactive storyboard editor** — Rich TUI or browser-based storyboard viewer/editor.
- [ ] **Voice preview** — Generate TTS for a single scene to preview before full render.
- [ ] **Batch produce** — Process multiple URLs from a candidate list in sequence.
