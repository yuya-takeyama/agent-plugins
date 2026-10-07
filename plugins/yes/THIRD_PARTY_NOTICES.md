# Third-party notices

YES's MIT license covers its original code and instructions, not external engines,
voices, character assets, or generated speech rights.

## VOICEVOX

- Engine: https://github.com/VOICEVOX/voicevox_engine
- Official image: https://hub.docker.com/r/voicevox/voicevox_engine
- Engine 0.25.2 terms and voice-specific links: https://github.com/VOICEVOX/voicevox_resource/blob/0.25.2/engine/README.md
- Voice model 0.16.4 terms: https://github.com/VOICEVOX/voicevox_vvm/blob/0.16.4/README.md
- General VOICEVOX software terms: https://voicevox.hiroshiba.jp/term/
- Default Zundamon / Metan voice terms: https://zunko.jp/con_ongen_kiyaku.html

The engine image is downloaded from its publisher by Docker; it is not bundled
in this repository. Display the selected voice's required credit with generated
speech; some voices require a CV name, not just `VOICEVOX:<character name>`.
The default voice is ずんだもん. The engine source, core, models, and container
dependencies have separate licenses; the image as a whole is not MIT.

`scripts/voicevox_voices.json` records credits and terms links from the pinned
engine's official list and the bundled 雨晴はう policy (whose current terms URL
is recorded separately), checked on 2026-10-07. It is a lookup aid, not a complete
review or permanent permission for every voice. Check each voice's current terms
for the user type, purpose, and publication/distribution format before use.
For example, [青山龍星](https://www.virvoxproject.com/voicevoxの利用規約)
requires prior application and permission for companies, sole proprietors, and
individuals contracted by companies, even without revenue.
[もち子](https://vtubermochio.wixsite.com/mochizora/利用規約) has additional
conditions for corporate involvement, audio works/materials, games, and file
distribution. Generated credits alone do not establish permission.

If you authorize someone else to use generated audio, require them to comply with
the voice-library terms and to impose the same obligations when authorizing
further users, as required by engine/model permission clauses 3 and 4. Ordinary
viewing is distinct from licensing the audio for reuse. Generated HTML carries
this notice and terms links in each video's description, including videos within
courses and asset bundles. Standalone WAV output has a `.license.txt` companion;
keep it with the file and provide a credit listeners can find. For audio-only
delivery, see the [VOICEVOX credit FAQ](https://voicevox.hiroshiba.jp/qa/).

## Character art

The bundled character definitions describe layer selections for 坂本アヒル's
ずんだもん and 四国めたん artwork. Source URLs are recorded in
`skills/video/characters/*.json` within the YES plugin. No PSD, exported PNG,
or generated HTML containing that art is distributed by this repository.

The zundamon-video example uses standing artwork by default. String cast members
enable automatic download into the user's cache. Before using the artwork,
read the artist's current terms at the source download page, including whether
your intended HTML distribution is permitted. An attribution is not a substitute
for permission. If those terms do not cover the intended use, resolve the artwork
choice with the user; do not silently downgrade a requested character video to
voices alone. The repository does not claim a license for those materials.

The pinned [Zundamon V3.2](https://uu.getuploader.com/s_ahiru/download/59) and
[Metan 2.1](https://uu.getuploader.com/s_ahiru/download/35) ZIP readmes allow
video/icon use and modification under the
[official character guidelines](https://zunko.jp/guideline.html), with optional
artist attribution and the （ず・ω・きょ） marker. The readmes were checked on
2026-10-07; check the author's current distribution-page terms as well.
Exported HTML and bundles contain extractable PNG layers. Permission to provide
a finished explanation does not establish permission to sell or redistribute a
general-purpose asset pack. Do not apply YES's MIT license to these assets.

## Dependencies and provenance

Python build dependencies: BudouX, imageio-ffmpeg, Playwright; optional art tooling:
psd-tools and Pillow. JavaScript development dependencies: Vitest and happy-dom.
They are installed separately and retain their own licenses. System fonts are
used; no third-party font files are redistributed.

The HTML video, quiz, course, and slides tools were extracted from Yuya Takeyama's
Stash project. The diagramming, dataviz, and design skills, their reference files,
and palette validator are intentionally not included or required.
