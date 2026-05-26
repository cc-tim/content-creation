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
