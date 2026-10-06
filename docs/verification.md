# Verification

Run the commands in the root README for metadata, Python and JavaScript checks.

```sh
uv run tests/smoke.py
```

This builds quizzes, single-narrator and dialogue players, and a mixed course
using deterministic test WAV audio. It exercises playback, slide navigation,
answer feedback, course review and resume in a real Chrome browser at desktop
and mobile widths. It rejects page errors, external resource requests, and
horizontal document overflow. It writes screenshots to the printed temp path;
inspect them before accepting visual changes. Routine CI explicitly selects the
voice-only alternative so it does not depend on the external art download host.
To check the default dialogue example with actual standing characters:

```sh
YES_SMOKE_CHARACTER_ART=1 uv run tests/smoke.py
```

This uses the character cache (or downloads missing art), checks that both
characters have loaded visible layers during playback, and captures desktop and
mobile views. Inspect those images for composition and play the page to verify
lip sync and expression changes; layer-loading assertions do not establish these.

For Linux CI without Chrome:

```sh
uv run --with playwright playwright install --with-deps chromium
YES_BROWSER_CHANNEL='' uv run tests/smoke.py
```

Real engine verification is separate:

```sh
plugins/yes/bin/yes-speak '動作確認なのだ。' -o /tmp/yes-smoke.wav
plugins/yes/bin/yes-speak --list-speakers --json
plugins/yes/bin/yes-speak --stop
```

The CI voicevox job runs this against the official Docker image. Generated
speech must still be listened to for pronunciation when authoring a real lesson.
Neither unit tests nor screenshots establish teaching quality.
