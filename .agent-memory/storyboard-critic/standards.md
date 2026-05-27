# Storyboard Critic — Standing Standards

Standards accrue from real review loops. Don't invent thresholds — these are lessons from actual storyboards that failed.

---

## From the baby-walker review (project 20260504-115232, loop 1, 2026-05-26)

**video_brief per-beat visual specs are binding, not advisory.**
If the video_brief names a visual treatment for a beat ("animated text overlay on the map, NOT as a bare text_card"), the storyboard must follow it. A text_card is never an acceptable substitute for a brief-specified visual. Flag every mismatch.

**Verbatim quotes get overlay-on-image, never bare text_card.**
A verbatim quote has been flagged by the author as a punchline — it's a decided creative call, not just a piece of narration. Rendering it as a text_card on a black background buries it. Always pair a verbatim quote with its natural image (the map for the policy quote, the chart for the data quote) as overlay — or demand the image if it doesn't exist.

**Product-comparison closing sections are the highest-risk slideshow zone.**
"The three products called X" style sections reliably collapse to 8-10 slides listing names, properties, and recommendations. Each named product must be anchored by its physical image in an article_image scene. Slides and text_cards for product descriptions are acceptable only *between* the image scenes — not as their replacement.

**A run of 4+ scenes without article_image/clip/generated_image/chart is a slideshow act — always flag it.**
Walk the storyboard looking for these runs specifically. The closing section is where they concentrate. Even if each consecutive slide is a different text topic, a viewer sees an unbroken black screen with text and the experience is a slideshow.

**Required images that don't appear in any scene are the highest-priority demand.**
If an image is listed in required_images and zero scenes reference it, the storyboard dropped a visual the author explicitly acquired. File a rewrite or merge demand first — before any stylistic demands.

**Charts authored in the video_brief must appear as chart scenes, not as narration-only beats.**
If key_facts or video_brief reference an authored chart (bar, line, comparison, stat_big_number), the corresponding scene must be visual.type="chart" with a chart_spec block. A text_card narrating the same number is not a substitute.

**Verbatim quote overlay type: use `namecard`, not `quote_bottom`.**
`quote_bottom` does not exist in the renderer. Use overlay `{"type": "namecard", "name": "<quote text>", "role": "<attribution>"}` — renders at 65-79% height with name (36px white) + role (24px grey), safe from subtitle collision. Confirmed from loop 1 of baby-walker (2026-05-26).

## From the baby-walker post-mortem (project 20260504-115232, loop 3 PASSED but render had 4 defects, 2026-05-27)

**Check `preferred_variant` in context.json BEFORE crediting any overlay — this is the first thing you do.**
`grep preferred_variant output/projects/<ID>/context.json`. If it is `no_overlay`, the delivered video burns NO per-scene overlays and NO subtitles — namecard, text_emphasis, text_bottom, text_top all render to nothing. In that case, review every scene AS IF the `overlay` field were absent: a scene's meaning, differentiation, and verbatim-quote payload must live entirely in the visual. Do not pass a scene whose point depends on an overlay that won't render. (Loop-3 PASS shipped three blank maps and four identical push-toy frames because every differentiator I credited was an overlay, and the delivered variant was no_overlay.)

**A blank/basemap/diagram asset is a substrate, NOT a self-sufficient visual.**
For every article_image, ask: if the overlay were stripped, does the bare frame still communicate the beat? A photograph (kettle, baby-in-walker, bathtub) carries meaning alone — pass. A blank grey political map, an empty chart frame, a featureless diagram carries NO meaning without its labels/markers/highlight. If the asset's entire semantic content lives in the overlay, then in a no_overlay variant it communicates nothing. Demand the meaning be baked INTO the asset (a map with Canada highlighted + "BANNED 2004" / US "STILL SOLD" rendered into the image file, or a chart scene whose labels are part of the chart render) — never a blank substrate + overlay.

**Count asset-path reuse across the whole storyboard; 3+ reuses of one image is a repetition defect unless each instance is visibly distinct in the DELIVERED frame.**
Walk every scene and tally `visual.path`. If one image path appears 3+ times, flag it. Reuse is acceptable ONLY when each instance is differentiated by something that survives into the rendered variant — a distinct camera_motion (different focus_point/zoom), a distinct crop, or a distinct refit — NOT by a distinct overlay (overlays may not render) and NOT by distinct narration (the viewer sees the screen, not the script). Identical frame + no camera motion + (stripped) overlay = the same shot N times. Prefer: demand a second real asset, a generated_image, a chart, or merge the redundant beats. (s36/s38/s45/s47 were the identical Baby_Walker.jpg with no camera motion; s24/s25/s26 the identical blank map.)

**On a PORTED video (source_locale ≠ locale), a `slide`/`text_card` burning target-locale text is a porting liability AND usually a missed visual — challenge every one.**
Check `source_locale` vs `locale` in context.json. When they differ, burned translated text is locale-locked (cannot be reused for another locale, reads like a subtitle baked into the frame). For each text slide ask: is the concept DEPICTABLE? A beat like "女性回到職場" → a generated_image of a woman working; "塑膠射出成型" → injection-molding machinery; "郊區開放格局" → a suburban open-plan home. A depictable concept is richer AND language-neutral as a generated_image. Reserve text slides for the genuinely non-depictable (pure abstractions, rhetorical questions, numeric checklists where the words ARE the content). "No archival photo exists" is the WRONG test — the right test is "can a generated_image depict this concept?"

**The differentiator must survive into the delivered frame — overlays and narration do not count.**
General form of the reuse and blank-map lessons: when you justify passing a scene by saying "it's differentiated/meaningful because of X," X must be something a viewer sees in the final rendered variant. Camera motion, crop, the baked-in image content, and chart labels survive. Overlays survive ONLY if the variant burns them (check preferred_variant). Narration never appears on screen. If your justification for a PASS leans on a non-surviving layer, it is not a PASS.

**Transitions must be semantically motivated, not uniform — review the `transitions[]` array against `section` boundaries.**
A distinctive transition (book-page-turn, wipe, slide) marks a *meaningful* boundary — an era/chapter/act change — not every seam. The baby-walker board applied `book-page-turn-v2` to all 29 opening seams (hook→context→rising→climax), turning "turning the pages of history" into a gimmick that page-turns between injury charts and policy beats. The intended design (dashboard verifier) is page-turn for the **intro + history scenes only**. Rule: a distinctive transition belongs only where the cut itself means something — within the history/book act, and the boundary into/out of it (e.g. "closing the history book" at the history→present-day seam). Within an analytical act (chart→chart, stat→stat), use straight cuts (`style:none`). Flag any distinctive transition applied to more than ~1/3 of seams, or spanning unrelated sections, as uniform decoration.
