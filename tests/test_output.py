import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('output',Path(__file__).resolve().parents[1]/'plugins/yes/scripts/output.py')
output=importlib.util.module_from_spec(spec); spec.loader.exec_module(output)


class OutputTests(unittest.TestCase):
    def test_bundle_assets_are_relative_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'video.html'
            p.write_text('<audio src="data:audio/mp4;base64,YWJj"></audio><script>const a="data:audio/mp4;base64,YWJj";</script>')
            target=output.export(p,'bundle')
            assets=list((target.parent/'assets').iterdir())
            self.assertEqual(len(assets),1)
            self.assertEqual(assets[0].read_bytes(),b'abc')
            self.assertNotIn('data:audio',target.read_text())
            self.assertEqual(target.read_text().count('assets/'),2)
            self.assertEqual(output.export(p),p)
            with self.assertRaises(ValueError): output.export(p,max_bytes=1)


if __name__=='__main__': unittest.main()
