# Toon goldens: provenance

Minted on the hub on 2026-09-28 at commit 577b7a5, with
`UPDATE_GOLDENS=1 uv run pytest tests/unit/toon/test_goldens.py`.

| Library | Version |
|---|---|
| libcairo | 1.18.0 |
| cairocffi | 1.7.1 |
| Pillow | 12.2.0 |
| numpy | 2.4.4 |

The Mac (libcairo 1.18.4) renders these byte-identically: the mean abs diff is 0.0 on all three scene frames.
Each PNG was eyeballed before commit. Regenerate them on the hub only (see tests/golden_policy.py).
