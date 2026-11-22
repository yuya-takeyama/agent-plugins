"""YES narration: script text to VOICEVOX speech, shared by narration, video and zundamon-video.

reading  what is said: readings, spaces, numbers, and the script checks that catch misreadings
voices   where speech comes from: the bundled engine, another engine, a jobs API, a command or files
audio    WAV in and out: joining lines with pauses, loudness, silence, BGM, m4a/mp3
script   a narration script (chapters, scenes, lines, cast) as timed lines
manifest narration.json: what each line says, who says it, how long, and the credits
"""
from __future__ import annotations

import sys


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)
