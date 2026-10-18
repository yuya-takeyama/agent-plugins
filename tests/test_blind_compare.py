"""Blinding gives every version the same format and keeps the key out of the blind folder."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('blind_compare', ROOT / 'evals/design/blind_compare.py')
blind_compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind_compare)


def page(title, lines):
    timeline = {
        'duration': 61.2,
        'chapters': [{'id': 'c1', 'title': '木は低い'}],
        'scenes': [{'id': 'c1-1'}, {'id': 'c1-quiz'}],
        'lines': lines,
    }
    data = {'kind': 'video', 'data': {'title': title, 'goals': ['説明できる'], 'timeline': timeline}}
    return ('<section class="scene" data-scene="c1-1"><h2>3 段</h2><style>.x{}</style></section>'
            f'<script>const DATA = {json.dumps(data, ensure_ascii=False)};</script>')


LINES = [
    {'scene': 'c1-1', 'chapter': 'c1', 'who': 'metan', 'text': '木は 3 段よ。'},
    {'scene': 'c1-quiz', 'chapter': 'c1', 'who': 'metan', 'text': '何段かしら？'},
    {'scene': 'c1-quiz', 'chapter': 'c1', 'who': 'zundamon', 'text': '3 段なのだ。'},
]


class BlindCompareTest(unittest.TestCase):
    def test_markdown_keeps_speakers_board_and_quiz(self):
        md = blind_compare.to_markdown(page('B+Tree', LINES))
        self.assertIn('[on-screen] 3 段', md)
        self.assertIn('metan: 木は 3 段よ。', md)
        self.assertIn('[quiz] zundamon: 3 段なのだ。', md)
        self.assertIn('narration_chars: 8', md)
        self.assertNotIn('.x{}', md)

    def test_prepare_writes_letters_and_a_separate_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            versions = {}
            for name in ('existing', 'v1', 'v2'):
                path = root / f'{name}.html'
                path.write_text(page(name, LINES))
                versions[name] = path
            key = blind_compare.prepare(root / 'round', 'mysql', versions)
            self.assertEqual(sorted(key), ['A', 'B', 'C'])
            self.assertEqual(sorted(key.values()), ['existing', 'v1', 'v2'])
            blind = root / 'round/blind/mysql'
            self.assertEqual(sorted(p.name for p in blind.iterdir()), ['A.md', 'B.md', 'C.md'])
            for letter, name in key.items():
                self.assertIn(f'# {name}', (blind / f'{letter}.md').read_text())
            again = blind_compare.prepare(root / 'round', 'mysql', versions)
            self.assertEqual(again, key)


if __name__ == '__main__':
    unittest.main()
