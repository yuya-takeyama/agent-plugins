"""Quoted claims are matched against source text, and a changed number never passes."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_claims', ROOT / 'plugins/yes/scripts/check_claims.py')
check_claims = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_claims)

SOURCE = {'ok': True, 'text': ('Once, after I had watched a little one of four years repeat this exercise '
                               'sixteen times, I had the children sing in order to distract her. ' * 3)}


class VerdictTest(unittest.TestCase):
    def test_exact_quote_is_found(self):
        status, _ = check_claims.verdict('a little one of four years repeat this exercise sixteen times', SOURCE)
        self.assertEqual(status, 'found')

    def test_small_wording_drift_is_found(self):
        status, _ = check_claims.verdict('a little one of four years repeated this exercise sixteen times', SOURCE)
        self.assertEqual(status, 'found')

    def test_changed_number_is_not_found(self):
        status, _ = check_claims.verdict('a little one of four years repeat this exercise sixty times', SOURCE)
        self.assertEqual(status, 'NOT FOUND')

    def test_unreadable_source_needs_a_person(self):
        self.assertEqual(check_claims.verdict('anything', {'ok': False, 'why': 'HTTP 403'}), ('unfetched', 'HTTP 403'))

    def test_line_ids_match_the_build(self):
        script = {'chapters': [{'id': 'c1', 'scenes': [{'id': 'c1-1', 'lines': ['a', {'text': 'b'}]}],
                                'quiz': {'q': 'q?', 'a': 'a.'}}]}
        self.assertEqual(check_claims.narrated_lines(script),
                         {'c1-1.0': 'a', 'c1-1.1': 'b', 'c1-quiz.0': 'q?', 'c1-quiz.1': 'a.'})


if __name__ == '__main__':
    unittest.main()
