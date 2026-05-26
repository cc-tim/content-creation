# Storyboard Critic Reviews — 20260504-115232-baby-walker-story

## Loop 1 — 2026-05-26 — REWORK (applied, not looped per user instruction)

**Arc read:** Strong open with three real archival images and Ken Burns motion through the history block; injury-stats act properly charted; mechanism act has three hazard stills and the danger clip. Then sags: four verbatim punchlines buried as bare text cards despite explicit brief instructions, and the closing 15-scene product section collapses to 9 slides/text_cards with two real product photos sitting unused.

**Verdict:** First two-thirds is a real film. Closing third is a slideshow. Four verbatim quotes — every one in verbatim_lines — rendered as bare text_cards, two of them (s6, s25) in direct defiance of per-beat brief instructions naming the image and overlay treatment. Fixed with 7 demands auto-applied; text-heavy rate dropped 46% → 30%.

**Dimensions:**
- Messaging: Four verbatim punchlines buried as text_cards. s25 (Shin quote) and s6 (Sloan quote) had explicit per-beat brief specs naming image + overlay — both ignored by the generator.
- Structure: s45/s46 were a stranded repeated beat (same rule stated twice). Merged to one scene.
- Pacing: s40-s47 had a 6-scene slideshow run (slide/text_card with no real visuals). Breaking it required promoting s44 to a comparison chart and anchoring s45 on the push-toy image.
- Visual coverage: The two product photos (Baby_by_Vignesh.jpg, Baby_Walker.jpg) were underused in the closing section; now anchor s29/s35 (Vignesh) and s45 (Baby_Walker).

**Demands applied (7 auto):**
- [s6] (rewrite) → article_image Learning_to_walk.png + namecard overlay (Sloan verbatim) — binding video_brief spec; verbatim quotes need overlay-on-image
- [s25] (rewrite) → article_image north_america_blank_map.png + namecard overlay (Shin verbatim) — binding video_brief spec, explicitly forbade bare text_card
- [s29] (rewrite) → article_image Baby_by_Vignesh.jpg + namecard overlay (AAP verbatim) — standing standard: verbatim gets overlay-on-image
- [s35] (rewrite) → article_image Baby_by_Vignesh.jpg + text_emphasis overlay ("Still legal. Still sold. 2024") — image available, text_card wastes the punch
- [s37] (rewrite) → comparison chart (sit-in vs push-toy mechanical inverse) — A-vs-B narration deserves A-vs-B visual
- [s44] (rewrite) → comparison chart (3-product safety summary) — prime comparison slot; slide flattened it
- [s45+s46] (merge) → s45 article_image Baby_Walker.jpg + namecard ("Wheels + suspended seat" verbatim); s46 removed — repeated beat eliminated, verbatim lifted off bare card

**Technical note — quote_bottom unsupported:** Critic specified `quote_bottom` overlay type which does not exist in the renderer. All verbatim-quote overlays applied as `namecard` (name=quote, role=attribution) instead — renders at 65-79% height, safe from subtitle collision. Standards file updated.

**Greenpass terms:** n/a — loop stopped per user instruction after loop 1; loop 2 not dispatched.

**Post-loop 1 distribution:** article_image 18 (39%), chart 11 (23%), slide 7 (15%), text_card 7 (15%), clip 2 (4%), generated_image 1 (2%). Text-heavy: 30% (down from 46%).

## Loop 2 — 2026-05-27 — REWORK (3 demands, all applied; no blocking/acquire)

**Arc read:** Strong, coherent film start-to-finish. 1440 manuscript hook → four centuries of unchanging design → plastic 1960s-70s boom → clinical injury turn with animated charts and three hazard stills → undercount → decline-curve → Canada-vs-US ban politics → BMJ delay study → calm three-product close → one rule. Builds and earns its turns; only friction was three discrete repair points.

**Verdict:** All 7 loop-1 demands verified CLOSED on the scene side (4 verbatim punchlines now namecards on images; s37/s44 comparison charts; s45+s46 merged). Slideshow failure is dead — longest text-heavy run 3 (s41-43 activity-center close, accepted per greenlight term 3), longest chart run 2. REWORK rested on three discrete defects, now all fixed.

**Dimensions:**
- Messaging: Strong. Lone redundancy was s26 recycling s35's "Still legal/sold 2024" punchline — fixed.
- Structure: One carryover defect — the loop-1 s46 merge updated the scene list but NOT the `transitions` array, leaving dangling s45→s46 / s46→s47 referencing a deleted scene. Render-blocking. Fixed.
- Pacing: Resolved. Promoting s13 to a stat chart switches subtype (bar→stat→stat), not a same-type cluster.
- Visual coverage: Excellent. Every required_image appears; lone gap was s26 (no real visual) — fixed by the map.

**Demands applied (3, all auto/rewrite — no acquire, so no pause):**
- [s13] (rewrite) text_card "38% skull fractures" (English) → stat_big_number chart (value 38%, unit 顱骨骨折), schema mirrored from s11/s14/s18/s30. `reveal_duration_sec` set to 4.5 to match the four sibling stat charts (critic proposed 3.5). Brief forbade flattening the injury-stats block (230,676/74%/91%/38%) into number-cards.
- [s26] (rewrite) text_card recycling s35's punchline → article_image north_america_blank_map.png + text_emphasis overlay. **Adapted:** critic's overlay had a two-line `\n` text; the `_render_text_emphasis` ffmpeg drawtext renderer (src/pipeline/composer/overlay.py:185) is single-line and no existing scene uses `\n`. Reformatted to single line "美國選擇設計標準，而非禁令" (lobbying outcome; not redundant with s24 contrast or s35 punchline).
- [s45] (rewrite, scene-patch is a no-op) → the real payload was a **manual `transitions`-array fix** the per-scene patch schema can't express. Removed {s45→s46} and {s46→s47}, spliced {s45→s47, style:none, duration_sec:0.0} to match the closing-act straight-cut pattern. Verified no s46 ref remains.

**Technical learnings this loop:**
- `text_emphasis` overlay is single-line (one ffmpeg drawtext, center-x). Do NOT emit `\n` in text_emphasis text — use spaces/separators like s24, or split into a different beat. (Same class as the loop-1 `quote_bottom` invention.)
- `merge`/`cut` demands must also clean the top-level `transitions` array, not just the `scenes` list — the auto-apply loop's scene-only edit leaves dangling transition refs. The skill's apply step should be extended to prune transitions whose from/to point at removed scene ids.

**Post-loop 2 distribution:** article_image 19 (41%), chart 12 (26%), slide 7 (15%), text_card 5 (11%), clip 2 (4%), generated_image 1 (2%). Text-heavy: 26% (down from 30%).

**Greenpass terms:** n/a — REWORK; all 3 demands applied, no blocking demands, eligible to loop to verification (loop 3).

## Loop 3 — 2026-05-27 — PASS ✅

**Arc read:** Builds, earns its turns, lands soft — no sag, no slideshow. 1440 manuscript hook → four centuries unchanging → plastic boom → clinical injury turn on animated charts → mechanism (speed/stove/tub/caustic-soda) → undercount → decline-curve → Canada ban vs US inaction → BMJ delay → three-product close → one rule.

**Verdict:** Clean PASS. All three loop-2 demands verified ON DISK:
- s13 → stat_big_number chart (38% / 顱骨骨折); brief-forbidden English number-card gone.
- s26 → map + single-line text_emphasis "美國選擇設計標準，而非禁令"; the `\n` two-liner was correctly flattened against the single-line renderer; wording is the lobbying outcome, distinct from s35. Duplicate-punchline defect resolved.
- s45 transitions → orphan gone: 45 transitions, zero s46 refs, s45→s47 (style:none) spliced. All transitions reference real scenes.

Fresh pass found no new defects. The s13 fix created an s11–s14 four-chart run — scrutinized and CLEARED as brief-intentional (the injury-stats block 230,676/74%/91%/38% the brief forbade flattening), varied subtype (stat→bar→stat→stat), broken by the s15 danger clip. The 12 remaining text-heavy scenes all pass "better or just different?".

**Dimensions:** Messaging — every verbatim punchline on an image as namecard; s26 redundancy resolved. Structure — arc matches required_sequence; merge artifact fully cleaned. Pacing — longest text-heavy run 3 (s41–43, producer-greenlit), s11–14 chart run brief-mandated. Visual coverage — every required_image used, both clips used, no bare conceptual stretch except deliberate hinges.

**Demands:** none.

**Greenpass terms (durable — do not re-litigate in future loops):**
1. The s11–s14 four-chart run is INTENTIONAL, not a defect — brief enumerates 230,676/74%/91%/38% as the injury block that "must not flatten into number-cards." Do NOT revert s13 to a text_card (re-introduces the loop-2 defect). The producer's chart-clustering term targeted cross-act beats 4–7, already broken by the s24 map.
2. The s41–s43 text-heavy run (activity-center enumeration) is permitted under producer greenlight term 3 (category description, no acquire), anchored by s40 generated_image and closed by s44 comparison chart.
3. s26's single-line text_emphasis wording is confirmed acceptable.
4. On publish: carry CC-BY/CC-BY-SA/CC0 attributions per CREDITS.md; flag both .mp4 clips as AI-generated; never assert "this is a baby walker" over the ambiguous boom-era clip (s8).

**Final distribution:** article_image 19 (41%), chart 12 (26%), slide 7 (15%), text_card 5 (11%), clip 2 (4%), generated_image 1 (2%). Text-heavy 26%. STORYBOARD CLEARED FOR TTS/RENDER.
