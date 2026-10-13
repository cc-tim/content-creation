# toy3d parity references (E11 Sprint 12, EM ruling D1)

The frozen r7-3d snapshot's own renders of scene 001 beat 2 (look A), against which the toy3d
engine's render of `assets/toy3d/scenes/001-beat2-break-in.yaml` is compared
(`tests/integration/toy3d/test_parity_tryout.py`).

## Source

- snapshot: `output/projects/20260724-hybrid-ai-agent-controller/style-tryouts/r7-3d/frozen-v7-20261013/`
  (GuoGuo v7 approved and frozen by Tim, 2026-10-13; spec §12)
- `SHA256SUMS` sha256 `d9c61f636be2ee9adc537f2367224ebdf18bc2898fcec595fa2ca79f32715d75`, every entry
  checked before serving (`tests/toy3d_snapshot.py verify`)
- `scene.js` `4dbdf8e4e4fbccaf63a56dc05bba25ce6f2448fb2cc2e18c6da5650a4b000356`
- `stage.html` `0ee482aeac4bf999155a43be335ad38b0c1bd2b54d3cfbf8f75bc304cae3f8b2`
- `guo_trace.json` `c15df598781f350a850255b278210cd3d5bc312322944e3bf932d8633df8abaf`
- `locked_clip_v7.mp4` `79bc8fc16dba95726d03f68409dde01c733e8b026f198c4bc4c7aa086a4afe0d` (the tie
  check, below)
- three r170 from `src/toy3d/web/vendor/three-0.170.0/` (its `SHA256SUMS`
  `e87aae4c936a7ad4857ee36d3046271a829c87abf0d8931680c5a7c1ed8594eb`; the npm tarball whose sha512
  matches the snapshot's lockfile). The snapshot's `node_modules` is not part of it.

The snapshot's own `stage.html` and `scene.js` render each frame with its own `window.renderAt(t,
shot)`. `tests/toy3d_snapshot.py` drives them in place of `render.mjs`, on the engine's browser.
The served `scene.js` has one line appended, which exports its scene graph for Layer B. The file
on disk is unchanged.

## Render

- browser: Chrome for Testing `151.0.7922.34` (playwright 1.62.0, chromium-1234), flags
  `--use-angle=metal --ignore-gpu-blocklist`
- renderer: `ANGLE (Apple, ANGLE Metal Renderer: Apple M3 Pro, Unspecified Version)`
- machine: Tim's MacBook (M3 Pro), 2026-10-13
- 1920×1080 renders, downscaled to 960×540 with PIL LANCZOS (P2-R7)

| File | Frame |
|------|-------|
| `worked@0.600.png` | t 0.6: typing, the orbit |
| `worked@2.400.png` | t 2.4: the door spring, the walk, GuoGuo's hop |
| `worked@3.300.png` | t 3.3: the point, the bubble, the jab |
| `worked@4.000.png` | t 4.0: the shock, the turn, the push, the sweat |
| `worked@5.300.png` | t 5.3: the bulb flicker, the zoom |
| `worked@7.000.png` | t 7.0: the pull-back |
| `guo@0.714.png` | `STILLS.guo`: standing GuoGuo, 3/4, neutral (D3's standing design view) |

To re-render: `TOY3D_SNAPSHOT=<snapshot dir> uv run python -m tests.toy3d_snapshot refs <dir>`.

## Calibration (2026-10-13, this Mac)

- run to run: two reference renders are byte-identical (all 7);
- the engine against the references: max |diff| 0 on all 7 (pixel-identical);
- the tolerance: mean ≤ 0.1, 99.9th percentile ≤ 4, pixels over 8 levels ≤ 0.0005 (per-pixel max
  channel, 0–255). The margin covers a future driver's last-bit drift. A real change still fails:

| Sensitivity (at 960×540, against the reference) | mean | p99.9 | > 8 levels |
|---|---|---|---|
| Tim's right shoulder +5° at 4.0 | 0.087 | 22 | 0.0019 |
| Tim's decal shock → neutral at 4.0 | 0.213 | 80 | 0.0033 |
| GuoGuo's flippers held still at 2.4 | 0.102 | 36 | 0.0027 |

- tie to the locked clip: within H.264 noise. The evidence and the noise floor are in
  `tmp/toy3d-v0/parity/mp4_tie.txt`; Tim's side-by-side sheets are `tmp/toy3d-v0/parity/sheet_t*.png`.

These are Mac-Metal references. On another renderer string or build, the parity test skips by
name. The hub-canonical goldens are Layer C (`tests/fixtures/toy3d/goldens/`).
