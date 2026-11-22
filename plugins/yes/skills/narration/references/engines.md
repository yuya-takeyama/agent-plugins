All relative paths below are relative to the narration skill directory, one level above this reference.

# Speech sources

| Source | Set | VOICEVOX rules |
|---|---|---|
| bundled `yes-speak`, local Docker engine | nothing | always |
| bundled `yes-speak`, another VOICEVOX engine | `YES_VOICEVOX_URL` | always |
| a jobs API (whole script per request) | `YES_VOICEVOX_URL`, `YES_VOICEVOX_API=jobs` | always |
| a command | `YES_TTS_CMD` (alias `EV_TTS_CMD`), optional `YES_TTS_ENGINE` | unless `YES_TTS_ENGINE=other` |
| WAV files written by the agent | `YES_TTS_FILES=1`, `YES_TTS_ENGINE`, `YES_TTS_SPEAKERS` | when `YES_TTS_ENGINE=voicevox` |

The same variables drive `narrate.py`, `video/build.py` (video and
zundamon-video) and `yes-speak` itself. A command or files take precedence
over `YES_VOICEVOX_URL`.

VOICEVOX rules: only ずんだもん and 四国めたん (any talk style); a single
narrator is ずんだもん by its style id, never an engine's default voice; the
output carries each voice's credit (`VOICEVOX:ずんだもん`) and links the
engine, model and voice terms. Only the bundled local engine has a known
version, so only it links version-pinned terms; any other source links the
current ones.

## Another engine: `YES_VOICEVOX_URL`

The base URL of a VOICEVOX engine (`/version`, `/speakers`, `/audio_query`,
`/synthesis`), for instance one on a faster machine. `yes-speak` then starts
no Docker container and `--stop` stops nothing. Keep the address out of
committed files: set it in the shell or the agent's environment.

## A jobs API: `YES_VOICEVOX_API=jobs`

For a service that queues synthesis, with this contract:

- `GET /speakers`: the engine's speakers, `[{name, credit?, styles: [{name, id, type}]}]`.
- `POST /synthesize` `{text, speaker, speedScale}` → JSON with a short-lived
  signed `url` to the WAV, or `{error}` (used by `yes-speak` for one line).
- `POST /jobs` `{items: [{text, speaker, speedScale, intonationScale}]}`, up
  to 500 items → `202 {id}`; `503` while the engine starts (retried).
  `GET /jobs/<id>` → `{state: queued|running|done|failed, items: [{index,
  state, url, key?}]}`. The same items give the same job, so running again
  after a failure retries only the failed lines.

The build sends every line it lacks as one job (500 per batch), polls until
done, downloads each WAV into the cache and validates it (24000 Hz mono
16-bit). Signed URLs and the API's address are never written to
`narration.json`. The engine version is taken from the artifact key
(`voicevox-0.25.2/…`) when the API puts it there.

## A command: `YES_TTS_CMD`

Takes `--text T -o FILE --force --speed S [--speaker STYLE_ID]` and writes a
24000 Hz mono 16-bit WAV; `--list-speakers --json` prints the speaker list
above. An `HTTP 429` or `HTTP 503` on stderr is retried with backoff.

## Files: `YES_TTS_FILES=1`

`tts-plan` writes `out/tts-plan.json` `{engine, format, items: [{file, text,
speaker, style, style_id, speed}]}` for every line without audio (for example
for an MCP speech tool). Synthesize each `text` with that voice and speed,
write the WAV to `file`, then build. The build never synthesizes in this mode
and stops while a file is missing. `YES_TTS_SPEAKERS` is the speaker list.

## Cache

Each line's WAV is cached under `~/.cache/yes/tts/` (`EV_TTS_CACHE`) by a
hash of the source, the voice's style id, the speed and the spoken text. A
rebuild synthesizes only lines where one of these changed, and audio from one
source never stands in for another's. `EV_TTS_WORKERS` (default 4) sets how
many lines a command synthesizes at once.

## narration.json

`synth` writes `out/narration.json`; video builds write one beside the
page as well.

```json
{
  "format": 1, "title": "…",
  "engine": {"name": "VOICEVOX", "source": "bundled", "version": "0.25.2"},
  "credits": ["VOICEVOX:ずんだもん", "VOICEVOX:四国めたん"],
  "usageTerms": {"text": "…", "links": [{"title": "…", "url": "…"}]},
  "lines": [{"id": "c1.0", "chapter": "c1", "text": "TrueTime です", "spoken": "トゥルータイムです",
             "who": "metan", "speaker": "四国めたん", "style": "ノーマル", "style_id": 2,
             "speed": 1.0, "seconds": 1.333, "pause": 0.35, "sha256": "…", "key": "…",
             "credit": "VOICEVOX:四国めたん", "file": "narration/<key>.wav", "listen": ["…"]}]
}
```

`file` (in a narration project) is the line's WAV copied into the project,
so `mix` and `check` need neither the cache nor the engine. `sha256` is the
WAV's hash; `check` reports a file that no longer matches. `listen` is
present only on lines with a number pattern to check by ear.
