"""Check catalog paths, portable skill metadata, local links, and publication boundary."""
from pathlib import Path
import json
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
errors = []
def expect(ok, message):
    if not ok: errors.append(message)

def plugin_folder(catalog, data, entry):
    """Local catalog source, prefixed by Cursor's metadata.pluginRoot when set."""
    source = entry['source']
    rel = source if isinstance(source, str) else source.get('path')
    label = f'{catalog}: {entry.get("name")}'
    if not isinstance(rel, str) or '://' in rel:
        errors.append(f'{label}: plugin source must be a local relative path')
        return None
    prefix = (data.get('metadata') or {}).get('pluginRoot') or ''
    if prefix:
        if not isinstance(prefix, str) or Path(prefix).is_absolute() or '..' in Path(prefix).parts:
            errors.append(f'{label}: pluginRoot must be a relative path without ..')
            return None
        rel = str(Path(prefix) / rel.removeprefix('./'))
    path = Path(rel)
    if path.is_absolute() or '..' in path.parts:
        errors.append(f'{label}: plugin source must be a relative path without ..')
        return None
    return ROOT / path

def relative_manifest_path(label, value):
    """Cursor component paths stay inside the plugin: relative, no '..', no URL unless it is a logo."""
    if isinstance(value, list):
        for item in value:
            relative_manifest_path(label, item)
        return
    if not isinstance(value, str) or '://' in value:
        expect(isinstance(value, str), f'{label}: path must be a string')
        return
    path = Path(value)
    expect(not path.is_absolute() and '..' not in path.parts,
           f'{label}: path must be relative without ..: {value}')

CATALOGS = (
    '.claude-plugin/marketplace.json',
    '.agents/plugins/marketplace.json',
    '.cursor-plugin/marketplace.json',
)
for catalog in CATALOGS:
    data=json.loads((ROOT/catalog).read_text())
    expect(bool(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', data.get('name', ''))),
           f'{catalog}: marketplace name must be kebab-case')
    for entry in data['plugins']:
        folder=plugin_folder(catalog, data, entry)
        if folder is None or not folder.is_dir():
            expect(folder is not None and folder.is_dir(),
                   f'{catalog}: {entry.get("name")} source does not resolve')
            continue
        manifest=json.loads((folder/'plugin.json').read_text())
        claude=json.loads((folder/'.claude-plugin/plugin.json').read_text())
        cursor_path=folder/'.cursor-plugin/plugin.json'
        expect(cursor_path.is_file(), f'{folder.relative_to(ROOT)}: missing .cursor-plugin/plugin.json')
        if not cursor_path.is_file():
            continue
        cursor=json.loads(cursor_path.read_text())
        expect(manifest['name']==entry['name']==claude['name']==cursor['name'],
               f'{catalog}: plugin names differ')
        expect(bool(re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', entry['name'])),
               f'{catalog}: plugin name must be kebab-case')
        expect(manifest['version']==claude['version']==cursor['version'],
               f'{folder.relative_to(ROOT)}: plugin versions differ: '
               f'plugin.json={manifest["version"]!r}, '
               f'.claude-plugin/plugin.json={claude["version"]!r}, '
               f'.cursor-plugin/plugin.json={cursor["version"]!r}')
        if 'version' in entry:
            expect(entry['version']==manifest['version'],
                   f'{catalog}: {entry["name"]} version differs from plugin.json')
        for field in ('skills', 'rules', 'agents', 'commands', 'logo'):
            if field in cursor:
                relative_manifest_path(f'{folder.relative_to(ROOT)} .{field}', cursor[field])
        if isinstance(cursor.get('skills'), str):
            expect((folder/cursor['skills']).is_dir(),
                   f'{folder.relative_to(ROOT)}: cursor skills path missing')
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

for base in (ROOT/'plugins',ROOT/'docs',ROOT/'.cursor-plugin'):
    if not base.exists(): continue
    for path in base.rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts or 'out' in path.parts: continue
        if path.suffix in ('.psd', '.wav', '.m4a', '.png', '.mp4'):
            # Only reviewed, composed documentation previews may contain third-party art/audio.
            preview = path.relative_to(ROOT).as_posix()
            allowed = {'docs/previews/yes-intro.png', 'docs/previews/yes-intro.mp4'}
            expect(preview in allowed, f'{path}: generated/third-party media in source')
            if preview in allowed:
                with path.open('rb') as media:
                    header = media.read(24)
                expect(path.stat().st_size <= 25 * 1024 * 1024, f'{path}: preview exceeds 25 MiB')
                if path.suffix == '.png':
                    expect(len(header) == 24 and header[:8] == b'\x89PNG\r\n\x1a\n'
                           and struct.unpack('>II', header[16:24]) == (1280, 720),
                           f'{path}: expected a 1280x720 PNG preview')
                else:
                    expect(header[4:8] == b'ftyp', f'{path}: expected an MP4 preview')
            continue
        text=path.read_text()
        expect('stash.yuyat' not in text and 'voicevox.yuyat' not in text and 'window.stash' not in text,f'{path}: owner-specific service dependency')
        expect(not any(s in text for s in ('stash-diagramming','stash-dataviz','stash-design')),f'{path}: excluded skill reference')
        if path.suffix=='.md':
            for link in re.findall(r'\]\(([^)]+)\)',text):
                if ':' in link or link.startswith('#'): continue
                expect((path.parent/link.split('#')[0]).exists(),f'{path}: broken link {link}')
        if path.suffix in ('.html','.js','.css'):
            expect(not re.search(r'https://(?:fonts.googleapis|fonts.gstatic)',text),f'{path}: external font dependency')

expect(set(x.name for x in (ROOT/'plugins/yes/skills').iterdir())=={'design','explain','slides','quiz','video','zundamon-video','course'},'Unexpected skill scope')
if errors:
    raise SystemExit('\n'.join(errors))
print('Catalogs, skills, links, and publication boundary: OK')
