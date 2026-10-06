"""Check catalog paths, portable skill metadata, local links, and publication boundary."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
errors = []
def expect(ok, message):
    if not ok: errors.append(message)

for catalog in ('.claude-plugin/marketplace.json','.agents/plugins/marketplace.json'):
    data=json.loads((ROOT/catalog).read_text())
    for entry in data['plugins']:
        source=entry['source']
        folder=ROOT/(source if isinstance(source,str) else source['path'])
        manifest=json.loads((folder/'plugin.json').read_text())
        claude=json.loads((folder/'.claude-plugin/plugin.json').read_text())
        expect(manifest['name']==entry['name']==claude['name'],f'{catalog}: plugin names differ')
        expect(manifest['version']==claude['version'],f'{folder}: versions differ')
        names=[]
        for skill in (folder/'skills').iterdir():
            text=(skill/'SKILL.md').read_text()
            front=text.split('---',2)[1]
            name=re.search(r'^name: (.+)$',front,re.M).group(1)
            desc=re.search(r'^description: (.+)$',front,re.M).group(1)
            expect(name==skill.name and bool(re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',name)),f'{skill}: invalid name')
            expect(len(name)+len(manifest['name'])+1<=64 and 0<len(desc)<=1024,f'{skill}: metadata too long')
            names.append(name)
        expect(len(names)==len(set(names)),f'{folder}: duplicate skills')

for base in (ROOT/'plugins',ROOT/'docs'):
    if not base.exists(): continue
    for path in base.rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts or 'out' in path.parts: continue
        expect(path.suffix not in ('.psd','.wav','.m4a','.png'),f'{path}: generated/third-party media in source')
        text=path.read_text()
        expect('stash.yuyat' not in text and 'voicevox.yuyat' not in text,f'{path}: owner-specific service dependency')
        expect(not any(s in text for s in ('stash-diagramming','stash-dataviz','stash-design')),f'{path}: excluded skill reference')
        if path.suffix=='.md':
            for link in re.findall(r'\]\(([^)]+)\)',text):
                if ':' in link or link.startswith('#'): continue
                expect((path.parent/link.split('#')[0]).exists(),f'{path}: broken link {link}')
        if path.suffix in ('.html','.js','.css'):
            expect(not re.search(r'https://(?:fonts.googleapis|fonts.gstatic)',text),f'{path}: external font dependency')

expect(set(x.name for x in (ROOT/'plugins/yes/skills').iterdir())=={'explain','slides','quiz','video','zundamon-video','course'},'Unexpected skill scope')
if errors:
    raise SystemExit('\n'.join(errors))
print('Catalogs, skills, links, and publication boundary: OK')
