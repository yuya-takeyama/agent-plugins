# YES introduction video

A complete Japanese introduction made with YES's Zundamon/Metan dialogue builder.
It explains the available formats, choosing an audience and example, installation,
authoring requests, review, and sharing through Claude Artifacts or ChatGPT Sites.
The hosting advice is based on official documentation checked on 2026-10-07;
see the [publishing notes and sources](../../../plugins/yes/README.md#recommended-places-to-share).
The source has no embedded character
art or generated speech.

From the repository root, with the [YES requirements](../../../plugins/yes/README.md#requirements) installed:

```sh
uv run plugins/yes/skills/video/build.py lint docs/examples/yes-intro
uv run plugins/yes/skills/video/build.py build docs/examples/yes-intro
uv run plugins/yes/skills/video/build.py shoot docs/examples/yes-intro
uv run docs/examples/yes-intro/record.py
```

The build produces `out/video.html`, a self-contained interactive player, and
the measured narration/timeline. `record.py` captures the complete browser
timeline at 1280 × 720 / 24 fps, muxes its actual narration, and adds visible
credits. It writes `out/yes-intro.mp4`, `out/yes-intro-preview.png`, and
`out/yes-intro.mp4.license.txt`. CSS fades are disabled during deterministic
frame capture; authored reveals, expressions, captions, and lip sync follow
the original measured timeline. Rendering can take several minutes.

Use `YES_BROWSER_CHANNEL=''` for installed Playwright Chromium instead of Chrome.
The HTML player is the standard skill output; MP4 recording is this example's
documentation helper. Generated intermediates stay in the ignored `out/` folder.

The README publishes only the composed [MP4](../../previews/yes-intro.mp4) and
[preview](../../previews/yes-intro.png), not the editable character layers.
See the [media notice](../../previews/NOTICE.md) and
[voice/artwork conditions](../../../plugins/yes/THIRD_PARTY_NOTICES.md).
