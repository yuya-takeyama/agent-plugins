# Third-party notices

YES's MIT license covers its original code and instructions, not external engines,
voices, character assets, or generated speech rights.

## VOICEVOX

- Engine: https://github.com/VOICEVOX/voicevox_engine
- Official image: https://hub.docker.com/r/voicevox/voicevox_engine
- Terms and character-specific links: https://voicevox.hiroshiba.jp/term/

The engine image is downloaded from its publisher by Docker; it is not bundled
in this repository. Display `VOICEVOX:<character name>` with generated speech
and check the selected voice's terms. The default voice is ずんだもん.

## Optional character art

The bundled character definitions describe layer selections for 坂本アヒル's
ずんだもん and 四国めたん artwork. Source URLs are recorded in
`skills/video/characters/*.json` within the YES plugin. No PSD, exported PNG,
or generated HTML containing that art is distributed by this repository.

Voice-only inline cast members are the default example. Choosing a string cast
member enables automatic download into the user's cache. Before opting in,
read the artist's current terms at the source download page, including whether
your intended HTML distribution is permitted. An attribution is not a substitute
for permission. Use your own art or voice-only mode if those terms do not cover
your use. The repository does not claim a license for those materials.

## Dependencies and provenance

Python build dependencies: BudouX, imageio-ffmpeg, Playwright; optional art tooling:
psd-tools and Pillow. JavaScript development dependencies: Vitest and happy-dom.
They are installed separately and retain their own licenses. System fonts are
used; no third-party font files are redistributed.

The HTML video, quiz, course, and slides tools were extracted from Yuya Takeyama's
Stash project. The diagramming, dataviz, and design skills, their reference files,
and palette validator are intentionally not included or required.
