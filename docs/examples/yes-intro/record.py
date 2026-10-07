# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright>=1.50", "imageio-ffmpeg>=0.5"]
# ///
"""Capture this example's full HTML timeline as a 16:9 MP4, including its audio."""
import argparse
import base64
import json
import math
import os
from pathlib import Path
import subprocess

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--fps', type=int, default=24)
args = parser.parse_args()
if not 1 <= args.fps <= 60:
    parser.error('--fps must be between 1 and 60')
root = Path(__file__).resolve().parent
out = root / 'out'
data = json.loads((out / 'unit.json').read_text())['data']
duration = data['timeline']['duration']
# Use the player's exact embedded audio, independent of builder intermediates.
prefix = 'data:audio/mp4;base64,'
assert data['audio'].startswith(prefix), 'Expected embedded MP4 audio'
audio_path = out / 'capture-audio.m4a'
audio_path.write_bytes(base64.b64decode(data['audio'][len(prefix):], validate=True))
page_source = (out / 'video.html').read_text()
# Expose the existing timeline renderer only in this temporary capture copy.
# Sampling its clock avoids dropped frames and keeps mouth/captions aligned with audio.
marker = '  function render(x) {'
assert page_source.count(marker) == 1, 'Video renderer changed; review the capture adapter'
capture = out / 'capture.html'
capture.write_text(page_source.replace(marker, '  window.YES_CAPTURE_RENDER = render;\n' + marker))
target = out / 'yes-intro.mp4'
frames = math.ceil(duration * args.fps)
log = out / 'record.log'

with sync_playwright() as pw, log.open('w') as errors:
    browser = pw.chromium.launch(channel=os.environ.get('YES_BROWSER_CHANNEL', 'chrome') or None)
    page = browser.new_page(viewport={'width': 1280, 'height': 720}, device_scale_factor=1)
    page_errors = []
    page.on('pageerror', lambda error: page_errors.append(str(error)))
    page.goto(capture.as_uri() + '#t=0&shot')
    page.evaluate('document.fonts.ready')
    page.wait_for_function('Array.from(document.querySelectorAll(".ev-char img")).every(i => i.complete && i.naturalWidth > 0)')
    assert page.locator('.ev-char').count() == 2
    # Discrete sampling preserves authored reveals; wall-clock CSS transitions would
    # otherwise make the same timestamp depend on capture machine speed.
    page.add_style_tag(content='*, *::before, *::after { transition: none !important; animation: none !important; }')
    page.evaluate('''() => {
      const credit = document.createElement('div');
      credit.style.cssText = 'position:absolute;top:538px;left:300px;right:300px;text-align:center;font:12px/1.6 sans-serif;color:#697168;z-index:4';
      credit.innerHTML = '音声: VOICEVOX:ずんだもん / VOICEVOX:四国めたん<br>立ち絵: 坂本アヒル / キャラクター: 東北ずん子・ずんだもんプロジェクト';
      document.querySelector('.ev-stage').append(credit);
    }''')
    preview_line = next(line for line in data['timeline']['lines'] if line['scene'] == 'yes-formats' and line['idx'] == 5)
    page.evaluate('(t) => YES_CAPTURE_RENDER(t)', preview_line['start'] + .4)
    page.screenshot(path=str(out / 'yes-intro-preview.png'))
    capture_session = page.context.new_cdp_session(page)
    ff = subprocess.Popen([
        imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'warning',
        '-f', 'image2pipe', '-framerate', str(args.fps), '-vcodec', 'png', '-i', '-',
        '-i', str(audio_path), '-map', '0:v:0', '-map', '1:a:0',
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '21', '-pix_fmt', 'yuv420p',
        '-c:a', 'copy', '-t', str(duration), '-movflags', '+faststart',
        '-metadata', 'title=YES — 伝えたいことを、学べるHTMLに。',
        '-metadata', 'comment=VOICEVOX:ずんだもん / VOICEVOX:四国めたん; 立ち絵: 坂本アヒル. Voice and artwork retain their own terms.',
        str(target),
    ], stdin=subprocess.PIPE, stderr=errors)
    try:
        for frame in range(frames):
            page.evaluate('(t) => YES_CAPTURE_RENDER(t)', frame / args.fps)
            # Capture the freshly rendered surface without Playwright's per-frame
            # font/layout preparation; fonts and assets were checked above.
            shot = capture_session.send('Page.captureScreenshot', {
                'format': 'png', 'captureBeyondViewport': False, 'optimizeForSpeed': True,
            })
            ff.stdin.write(base64.b64decode(shot['data']))
            if frame % (args.fps * 15) == 0:
                print(f'Captured {frame / args.fps:.0f}/{duration:.1f}s', flush=True)
        ff.stdin.close()
        if ff.wait() != 0:
            raise RuntimeError(f'ffmpeg failed; see {log}')
        if page_errors:
            raise RuntimeError(page_errors)
    finally:
        if ff.poll() is None:
            ff.terminate()
            ff.wait()
        browser.close()

notice = out / 'yes-intro.mp4.license.txt'
notice.write_text('\n'.join(data['credits']) + '\n\n' + data['usageTerms']['text'] + '\n\n' +
                  '\n'.join(link['title'] + ': ' + link['url'] for link in data['usageTerms']['links']) + '\n')
print(f'{target}: {duration:.1f}s, 1280x720, {args.fps}fps, {target.stat().st_size / 1e6:.1f} MB', flush=True)
