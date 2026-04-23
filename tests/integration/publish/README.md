# YouTube publish integration test

Runs a real upload + verify + delete cycle against a **sandbox channel**.

## One-time setup

1. Create a dedicated YouTube channel for testing (separate from any production channel).
2. Add a profile to `configs/youtube_channels.toml`:

   ```toml
   [profiles.sandbox]
   niche        = "sandbox"
   locale       = "en"
   channel_id   = ""   # fill in after first auth
   voice_guide  = "test"
   default_tags = []
   category_id  = 27

   [routing]
   "sandbox/en" = "sandbox"
   ```

3. Run OAuth: `uv run pipeline publish auth --profile sandbox`.
4. Place test fixtures:
   - `tests/fixtures/sample_final.mp4` — e.g. `ffmpeg -f lavfi -i color=c=black:s=1280x720:d=10 -f lavfi -i anullsrc -c:v libx264 -c:a aac -shortest tests/fixtures/sample_final.mp4`
   - `tests/fixtures/sample_thumbnail.png` — 1280x720 PNG (e.g. via `convert -size 1280x720 xc:black tests/fixtures/sample_thumbnail.png`).

## Running

```bash
YT_PUBLISH_SANDBOX=1 uv run pytest -m network tests/integration/publish/
```

Each test upload is deleted in teardown, so the sandbox channel stays clean.
