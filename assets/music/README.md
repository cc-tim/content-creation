# Music beds (audio axis)

One royalty-free music bed per mood, used by `pipeline compose music`. Mirrors the
`assets/sfx/` convention. **No audio is committed yet** — sourcing the tracks is a
manual step (the code errors clearly if a tagged mood has no bed).

## How to add a track

1. Download a track from the **YouTube Audio Library**, filtered to **"Attribution
   not required"** (so the main video stays credit-free — see the project rule
   "never add source credits unless explicitly asked").
2. Normalize to **48 kHz / stereo / ≈ −20 LUFS**, e.g.:
   ```bash
   ffmpeg -i in.mp3 -ar 48000 -ac 2 -af loudnorm=I=-20:TP=-1.5:LRA=11 \
     assets/music/<mood>/<name>.mp3
   ```
   Aim for ≥ 60 s (the bed loops if a cue is longer).
3. Set the entry in `library.json`: `file` = `"<mood>/<name>.mp3"`, plus
   `title` / `artist` / `source_url` / `duration_s` / `loudness_lufs` (provenance
   record — kept even though no attribution is required).

## Per-mood selection criteria (what makes a bed "right" for the mood)

| Mood       | Character |
|------------|-----------|
| tense      | sparse minor drone / low pulse, no melody, slow build, ~60–80 felt bpm |
| somber     | slow minor pad / lone piano, reflective-sad, minimal percussion |
| hopeful    | warm major pads + gentle piano/strings, gradually rising, ~80–100 bpm |
| triumphant | major, fuller arrangement, forward momentum / light percussion, resolved |
| reflective | neutral-warm ambient, steady, low emotional charge (analysis beats) |

`none` is silence (no track).

The first render target (baby-walker s19→s23) uses only **tense** and **hopeful**.
