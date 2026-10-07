"""Exercise the CI validator against matching and mismatched plugin manifests."""
import json
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PluginVersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'scripts').mkdir()
        shutil.copy(ROOT / 'scripts/validate.py', self.root / 'scripts/validate.py')
        self.add_plugin('yes', '1.2.3')

    def write_json(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data), encoding='utf-8')

    def add_plugin(self, name, version):
        for path in ('plugin.json', '.claude-plugin/plugin.json'):
            self.write_json(f'plugins/{name}/{path}', {'name': name, 'version': version})
        for skill in ('explain', 'slides', 'quiz', 'video', 'zundamon-video', 'course'):
            folder = self.root / f'plugins/{name}/skills/{skill}'
            folder.mkdir(parents=True)
            (folder / 'SKILL.md').write_text(f'---\nname: {skill}\ndescription: Test fixture.\n---\n')
        for path, source in (
            ('.claude-plugin/marketplace.json', f'./plugins/{name}'),
            ('.agents/plugins/marketplace.json', {'source': 'local', 'path': f'./plugins/{name}'}),
        ):
            target = self.root / path
            data = json.loads(target.read_text()) if target.exists() else {'plugins': []}
            data['plugins'].append({'name': name, 'source': source})
            self.write_json(path, data)

    def validate(self):
        return subprocess.run([sys.executable, str(self.root / 'scripts/validate.py')],
                              capture_output=True, text=True)

    def test_matching_versions_pass(self):
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_either_manifest_changed_alone_fails(self):
        for manifest in ('plugin.json', '.claude-plugin/plugin.json'):
            with self.subTest(manifest=manifest):
                path = f'plugins/yes/{manifest}'
                self.write_json(path, {'name': 'yes', 'version': '1.2.4'})
                result = self.validate()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('plugins/yes: plugin versions differ', result.stderr)
                self.assertIn('plugin.json=', result.stderr)
                self.assertIn('.claude-plugin/plugin.json=', result.stderr)
                self.assertIn('1.2.3', result.stderr)
                self.assertIn('1.2.4', result.stderr)
                self.write_json(path, {'name': 'yes', 'version': '1.2.3'})

    def test_each_plugin_has_its_own_version_but_must_match_both_hosts(self):
        self.add_plugin('another', '4.5.6')
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.write_json('plugins/another/.claude-plugin/plugin.json',
                        {'name': 'another', 'version': '4.5.7'})
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('plugins/another: plugin versions differ', result.stderr)

    def test_only_named_composed_previews_are_allowed(self):
        folder = self.root / 'docs/previews'
        folder.mkdir(parents=True)
        # The boundary check inspects container headers, not decoded pixel content.
        png_header = b'\x89PNG\r\n\x1a\n' + b'\0\0\0\rIHDR' + struct.pack('>II', 1280, 720)
        preview = folder / 'yes-intro.png'
        preview.write_bytes(png_header)
        video = folder / 'yes-intro.mp4'
        video.write_bytes(b'\0\0\0\x18ftypisom' + b'\0' * 12)
        self.assertEqual(self.validate().returncode, 0)
        preview.write_bytes(png_header[:16] + struct.pack('>II', 720, 1280))
        self.assertNotEqual(self.validate().returncode, 0)
        preview.write_bytes(png_header)
        raw = folder / 'character-layer.png'
        raw.write_bytes(png_header)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('generated/third-party media in source', result.stderr)


if __name__ == '__main__':
    unittest.main()
