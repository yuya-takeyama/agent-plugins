# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright>=1.50", "budoux>=0.6", "imageio-ffmpeg>=0.5"]
# ///
"""Build all formats with deterministic test audio and exercise them in a real browser."""
from pathlib import Path
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import shutil
import subprocess
import sys
import tempfile
from threading import Thread
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
SKILLS=ROOT/'plugins/yes/skills'
work=Path(tempfile.mkdtemp(prefix='yes-smoke-'))
fake=work/'fake_tts.py'
fake.write_text('''import json, sys, wave, math, struct
if '--list-speakers' in sys.argv:
    print(json.dumps([{'name':n,'styles':[{'name':s,'id':i*10+j,'type':'talk'} for j,s in enumerate(['ノーマル','ツンツン','なみだめ'])],'credit':'VOICEVOX:'+n} for i,n in enumerate(['四国めたん','ずんだもん'])])); sys.exit()
with wave.open(sys.argv[sys.argv.index('-o')+1], 'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
    w.writeframes(b''.join(struct.pack('<h',int(1000*math.sin(2*math.pi*220*i/24000))) for i in range(12000)))
''')
import shlex
env=dict(os.environ,EV_TTS_CMD=shlex.join([sys.executable,str(fake)]),EV_TTS_CACHE=str(work/'cache'))
def run(kind,*args):
    subprocess.run([sys.executable,str(SKILLS/kind/'build.py'),*map(str,args)],env=env,check=True)

video=work/'video'; shutil.copytree(SKILLS/'video/example',video)
script=json.loads((video/'script.json').read_text())
script['sources']=[{'title':'Reference fixture','url':'https://example.com/reference','note':'Primary source'}]
(video/'script.json').write_text(json.dumps(script,ensure_ascii=False))
dialogue=work/'dialogue'; shutil.copytree(SKILLS/'zundamon-video/example',dialogue)
with_art=os.environ.get('YES_SMOKE_CHARACTER_ART')=='1'
if not with_art:
    # Routine CI exercises the voice-only option without downloading external art.
    script=dialogue/'script.json'
    data=json.loads(script.read_text())
    data['cast']=[{'id':'metan','speaker':'四国めたん','color':'#d9418c'},
                  {'id':'zundamon','speaker':'ずんだもん','color':'#4f8a38'}]
    script.write_text(json.dumps(data,ensure_ascii=False))
slides=work/'slides.html'; shutil.copy(SKILLS/'slides/example.html',slides)
quiz=work/'quiz.json'; shutil.copy(SKILLS/'quiz/example/quiz.json',quiz)
run('quiz','build',quiz)
run('video','build',video,'--format','bundle')
run('video','build',dialogue)
course=work/'course'; course.mkdir()
(course/'course.json').write_text(json.dumps({'id':'smoke','title':'Smoke course','lessons':[
    {'id':'l1','title':'Learn','summary':'A lesson','units':[{'kind':'video','src':str(video)},{'kind':'quiz','src':str(quiz)}]},
    {'id':'l2','title':'Review','summary':'Another lesson','units':[{'kind':'slides','src':str(slides)},{'kind':'quiz','src':str(quiz)}]},
]}))
run('course','build',course,'--format','bundle')
run('course','check',course)

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass

server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(work)))
Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}'
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel=os.environ.get('YES_BROWSER_CHANNEL','chrome') or None)
    for name,path in [('slides',slides),('quiz',work/'out/quiz.html'),
                      ('video',video/'out/video.html'),('video-bundle',video/'out/video-bundle/index.html'),
                      ('dialogue',dialogue/'out/video.html'),('course-bundle',course/'out/course-bundle/index.html')]:
        for width in (1280,390):
            page=browser.new_page(viewport={'width':width,'height':844})
            errors=[]; external=[]; missing=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('response',lambda response:missing.append((response.status,response.url)) if response.status>=400 else None)
            def route(req):
                if not req.request.url.startswith(base+'/'):
                    external.append(req.request.url); req.abort()
                else: req.continue_()
            page.route('**/*',route)
            page.goto(base+'/'+path.relative_to(work).as_posix()); page.wait_for_timeout(500)
            if name=='course-bundle':
                page.evaluate('location.hash = "#l1-video"')
                page.wait_for_timeout(300)
            if name.startswith('video') or name in ('dialogue','course-bundle'):
                page.keyboard.press('Space'); page.wait_for_timeout(800)
                assert page.evaluate('document.querySelector("audio").currentTime')>0,(name,'audio did not advance')
                if name=='dialogue' and with_art:
                    assert page.locator('.ev-char').count()==2,'Both standing characters must render'
                    page.wait_for_function('Array.from(document.querySelectorAll(".ev-char")).every(c=>getComputedStyle(c).visibility==="visible" && Array.from(c.querySelectorAll("img")).some(i=>!i.hidden && i.naturalWidth>0))')
                page.keyboard.press('Space')
            if name=='slides':
                page.keyboard.press('ArrowRight')
                assert page.evaluate('YESSlides.state.slide')>=1
                page.wait_for_timeout(700)
            if name=='quiz':
                page.locator('.qz-ch').first.click()
                assert page.locator('.qz-why').first.is_visible()
            if name in ('video','video-bundle','course-bundle'):
                assert page.locator('.ev-desc-sources a').first.get_attribute('href')=='https://example.com/reference'
            if name=='course-bundle':
                video_box=page.locator('[data-unit="l1-video"]')
                video_box.locator('audio').evaluate('a => { a.currentTime=a.duration-.15; a.play(); }')
                end=video_box.locator('.ev-end'); end.wait_for(state='visible')
                assert end.locator('h1').inner_text()=='次は確認テスト'
                assert 'ev-counting' in end.get_attribute('class')
                page.screenshot(path=str(work/f'course-end-{width}.png'))
                if width==390:
                    assert end.evaluate('e=>e.parentElement.classList.contains("ev-video")')
                    assert end.locator('.ev-end-go').bounding_box()['height']>=44
                    end.get_by_role('button',name='とどまる',exact=True).click()
                    page.wait_for_timeout(10500)
                    assert page.evaluate('location.hash').startswith('#l1-video')
                    end.locator('.ev-end-go').click()
                else:
                    page.wait_for_function('location.hash==="#l1-quiz"',timeout=15000)
                page.wait_for_function('location.hash==="#l1-quiz"')
                for uid in ('l1-quiz','l2-quiz'):
                    page.evaluate('(id)=>location.hash=id',uid)
                    box=page.locator(f'[data-unit="{uid}"]'); box.wait_for(state='visible')
                    for i,q in enumerate(json.loads(quiz.read_text())['questions']):
                        box.locator('.qz-q').nth(i).locator('.qz-ch').nth(q['answer']).click()
                    if uid=='l1-quiz':
                        box.locator('.qz-act.primary').click()
                        page.wait_for_function('location.hash==="#l2-slides"')
                    else:
                        assert box.locator('.qz-act.primary').count()==0,'Last unit must not loop to itself'
            assert not errors,(name,errors)
            assert not external,(name,external)
            assert not missing,(name,missing)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'),(name,width,'horizontal overflow')
            page.screenshot(path=str(work/f'{name}-{width}.png'))
            page.close()
    browser.close()
server.shutdown()
print(f'Browser smoke passed; frames: {work}')
