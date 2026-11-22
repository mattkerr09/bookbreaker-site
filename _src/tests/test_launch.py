"""The Streakgauge launch build: same pages, new name and origin, nothing of the old name left, and its gate bites."""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

import launch  # noqa: E402
from pages import PUBLISHED  # noqa: E402


class LaunchBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.out = Path(cls.directory.name) / 'site'
        with contextlib.redirect_stdout(io.StringIO()):
            launch.make(cls.out)

    def test_gate_is_green_and_every_page_is_built(self):
        self.assertEqual(launch.gate(self.out), [])
        for rel in PUBLISHED:
            self.assertTrue((self.out / rel).exists(), rel)
        self.assertEqual((self.out / 'CNAME').read_text(), 'streakgauge.com\n')
        self.assertIn('Sitemap: https://streakgauge.com/sitemap.xml', (self.out / 'robots.txt').read_text())

    def test_name_origin_and_analytics_moved(self):
        home = (self.out / 'index.html').read_text()
        self.assertIn('<link rel="canonical" href="https://streakgauge.com/">', home)
        self.assertIn('data-domain="streakgauge.com"', home)
        self.assertIn('>Streakgauge</a>', home.replace(launch.MARK, ''))
        self.assertNotIn('msvalidate.01', home)
        self.assertIn(launch.MARK, home)
        llms = (self.out / 'llms.txt').read_text()
        self.assertTrue(llms.startswith('# Streakgauge'))
        self.assertIn('(https://streakgauge.com/pricing/)', llms)

    def test_gate_catches_a_leftover_name_and_a_missing_icon(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'site'
            with contextlib.redirect_stdout(io.StringIO()):
                launch.make(out)
            page = out / 'pricing' / 'index.html'
            page.write_text(page.read_text().replace('Streakgauge price', 'BookBreaker price', 1))
            (out / 'favicon.ico').unlink()
            script = out / 'streak-checker' / 'checker.js'
            script.write_text(script.read_text() + '\n// bookbreaker.bet\n')
            fails = launch.gate(out)
            self.assertTrue(any('old name' in f and 'pricing' in f for f in fails), fails)
            self.assertIn('missing favicon.ico', fails)
            self.assertTrue(any('old name' in f and 'checker.js' in f for f in fails), fails)

    def test_refuses_a_non_empty_folder(self):
        with self.assertRaises(SystemExit):
            launch.make(self.out)


if __name__ == '__main__':
    unittest.main()
