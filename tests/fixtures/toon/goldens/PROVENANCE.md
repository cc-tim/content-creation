# Toon goldens: provenance

Minted on the hub on 2026-09-28 at commit 577b7a5, with
`UPDATE_GOLDENS=1 uv run pytest tests/unit/toon/test_goldens.py`.

| Library | Version |
|---|---|
| libcairo | 1.18.0 |
| cairocffi | 1.7.1 |
| Pillow | 12.2.0 |
| numpy | 2.4.4 |

The Mac (libcairo 1.18.4) does not render these byte-identically. Re-measured directly (960×540,
`PIPELINE_GOLDEN_STRICT=1`, no downscale) against the committed PNGs: `s001_04.70.png` and
`s001_12.20.png` are byte-identical (0 differing pixels), but `s001_01.50.png` differs by 1
pixel out of 518,400, by 1 colour level (max channel diff 1) — a libcairo 1.18.0-vs-1.18.4
rasterization rounding difference, not a semantic drift. `tests/golden_policy.py` skips the
byte-exact compare off-hub for this reason; run with `PIPELINE_GOLDEN_STRICT=1` to force it.
Each PNG was eyeballed before commit. Regenerate them on the hub only (see tests/golden_policy.py).
