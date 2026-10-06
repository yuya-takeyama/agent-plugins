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
inspect them before accepting visual changes. Tests do not fetch character art.

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
