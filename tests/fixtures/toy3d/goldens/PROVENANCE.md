# toy3d Layer C goldens (E11 Sprint 12, S12-12)

Pixel goldens of the toy3d engine: the worked scene's 6 key frames, and the cast model sheet
(`toy3d.sheet`: standing GuoGuo 3/4, the two-shot and the close-up at t 4.6). They are
hub-canonical, and both machines compare against them with `tests/golden_policy.py`
`assert_close_to_golden` (`tests/integration/toy3d/test_goldens.py`).

## Minting

- driver: `UPDATE_GOLDENS=1 uv run pytest tests/integration/toy3d/test_goldens.py::test_layer_c_goldens --integration`,
  on the hub only (the helper refuses UPDATE_GOLDENS anywhere else), in an isolated clone at
  `971d526`, 2026-10-13
- browser: Chrome for Testing `151.0.7922.34` (playwright 1.62.0, chromium-1234), flags
  `--use-angle=gl-egl --ignore-gpu-blocklist`
- hub renderer: `ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1050/PCIe/SSE2, OpenGL ES 3.2)`
- Mac renderer (compared, never minted): `ANGLE (Apple, ANGLE Metal Renderer: Apple M3 Pro, Unspecified Version)`
- 1920×1080 renders, downscaled to 960×540 with PIL LANCZOS (P2-R7)

## The limits, between the noise floor and the sensitivity set

The metrics are per-pixel max-channel |diff| (0–255): the mean, the 99.9th percentile, the
fraction over 8 levels, and the worst 24-px tile mean (a local change).

| View | hub run to run | Mac against the hub golden |
|---|---|---|
| worked@0.600 | 0 (max 1) | mean 0.271, p99.9 3, >8 0.00037, tile 2.57 |
| worked@2.400 | 0 (max 1) | mean 0.379, p99.9 3, >8 0.00005, tile 1.16 |
| worked@3.300 | 0 (max 1) | mean 0.332, p99.9 6, >8 0.00086, tile 8.20 |
| worked@4.000 | 0 | mean 0.339, p99.9 3, >8 0.00011, tile 1.23 |
| worked@5.300 | 0 (max 1) | mean 0.380, p99.9 5, >8 0.00054, tile 2.95 |
| worked@7.000 | 0 (max 1) | mean 0.344, p99.9 4, >8 0.00045, tile 8.34 |
| sheet_guo_34 | 0 (max 1) | mean 0.310, p99.9 37, >8 0.00204, tile 10.69 |
| sheet_twoshot | 0 (max 1) | mean 0.331, p99.9 4, >8 0.00038, tile 7.02 |
| sheet_closeup | 0 (max 1) | mean 0.333, p99.9 8, >8 0.00092, tile 5.23 |

The floor is the maximum of the two columns: the Mac against the hub. It's deterministic. The two
GPUs differ most in GuoGuo's shell fur, so his view gets its own limits.

| Limits | mean | p99.9 | > 8 levels | tile |
|---|---|---|---|---|
| key frames, two-shot, close-up | 0.6 | 16 | 0.0013 | 15 |
| `sheet_guo_34` | 0.6 | 48 | 0.004 | 15 |

The sensitivity set fails on both machines (in bold, the metric over its limit):

| Change (against the golden) | on the hub | on the Mac |
|---|---|---|
| Tim's decal shock → neutral, close-up | **>8 0.0199**, **tile 96** | **>8 0.0207**, **tile 97** |
| Tim's right shoulder +5°, 4.0 | **>8 0.00190**, **tile 25.0** | **>8 0.00200**, **tile 25.0** |
| GuoGuo hidden, 2.4 | **>8 0.0150**, **tile 159** | **>8 0.0151**, **tile 159** |
| the lioness's dress `#a8a8c6` → `#b4a8c6`, 4.0 | **>8 0.00556** | **>8 0.00573** |
| GuoGuo's fur shells 22 → 11, `sheet_guo_34` | **>8 0.00977**, **p99.9 57** | **>8 0.0118**, **p99.9 57** |

Re-mint only for a deliberate look change, on the hub, and re-measure this table. The parity
references (Mac Metal, the frozen snapshot's own renders) are in `../tryout_ref/`.
