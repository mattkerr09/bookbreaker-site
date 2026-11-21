"""The launch origin and the NFL credit are checked without network calls."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

import build
import check
from content import NFL_LICENSE, nfl_credit
from pages import DATA_PATHS, PLAYER_PATHS, SEARCH_PATHS
from page_rules import Document, clean
from redirects import NEW_ORIGIN


def assert_credit(test, source):
    doc = Document(source).root
    entries = [node for section in doc.classes('sources') for node in section.all('li')
               if clean(node.text()) == 'NFL data: nflverse , licensed CC BY 4.0 . Counts and ranges computed by BookBreaker.']
    test.assertEqual(len(entries), 1)
    links = {node.attrs.get('href'): clean(node.text()) for node in entries[0].all('a')}
    test.assertEqual(links, {'https://github.com/nflverse/nflverse-data': 'nflverse',
                             NFL_LICENSE: 'CC BY 4.0'})


class OriginAndCreditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.site = Path(cls.directory.name)
        with patch.object(build, 'SITE', cls.site), redirect_stdout(io.StringIO()):
            build.main()

    def test_every_data_page_has_the_credit_in_sources(self):
        for path in ['index.html', *SEARCH_PATHS, *DATA_PATHS, *PLAYER_PATHS]:
            with self.subTest(path=path):
                source = (self.site / path).read_text()
                assert_credit(self, source)
                self.assertIn(nfl_credit(), source)
                # The same assertion rejects a removed or unlinked credit, then passes the original.
                for broken in [source.replace(nfl_credit(), ''),
                               source.replace(NFL_LICENSE, 'https://unlisted.example/')]:
                    with self.assertRaises(AssertionError):
                        assert_credit(self, broken)
                assert_credit(self, source)

    def test_license_host_is_allowed_and_removal_is_detected(self):
        self.assertIn('creativecommons.org', check.allowed_hosts())
        with patch.object(check, 'NFL_LICENSE', ''):
            self.assertNotIn('creativecommons.org', check.allowed_hosts())
        self.assertIn('creativecommons.org', check.allowed_hosts())

    def test_current_origin_literal_occurs_only_in_build_constant(self):
        declaration = 'ORIGIN = ' + repr(build.ORIGIN)
        # Accept the repo's double-quote style, too.
        declaration = declaration.replace(repr(build.ORIGIN), json.dumps(build.ORIGIN))
        self.assertIn(declaration, (SOURCE / 'build.py').read_text())
        occurrences = [(str(path.relative_to(SOURCE)), line.strip())
                       for path in SOURCE.rglob('*') if path.suffix in ('.py', '.json', '.txt', '.csv')
                       for line in path.read_text().splitlines() if build.ORIGIN in line]
        self.assertEqual(occurrences, [('build.py', declaration)])

    def test_one_origin_switch_updates_all_metadata_sitemap_and_llms(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            with patch.object(build, 'SITE', site), patch.object(build, 'ORIGIN', NEW_ORIGIN), redirect_stdout(io.StringIO()):
                build.main()
            for path in site.rglob('*.html'):
                source = path.read_text()
                self.assertNotIn(build.ORIGIN, source)
                doc = Document(source).root
                relative = str(path.relative_to(site))
                url_path = '/' + relative.removesuffix('index.html') if relative.endswith('index.html') else '/' + relative
                expected = NEW_ORIGIN + url_path
                self.assertEqual([n.attrs.get('href') for n in doc.all('link')
                                  if n.attrs.get('rel') == 'canonical'], [expected])
                self.assertEqual([n.attrs.get('content') for n in doc.all('meta')
                                  if n.attrs.get('property') == 'og:url'], [expected])
                for script in doc.all('script'):
                    if script.attrs.get('type') == 'application/ld+json':
                        self.assertEqual(json.loads(script.text())['mainEntityOfPage'], expected)
            sitemap = (site / 'sitemap.xml').read_text()
            llms = (site / 'llms.txt').read_text()
            self.assertNotIn(build.ORIGIN, sitemap + llms)
            for node in ET.fromstring(sitemap):
                self.assertTrue(node[0].text.startswith(NEW_ORIGIN + '/'))
            self.assertIn(f'[Home]({NEW_ORIGIN}/)', llms)
            self.assertIn(f'[Privacy]({NEW_ORIGIN}/privacy/)', llms)
            for config in [*build.SEARCH_PAGES, build.NFL_INDEX, build.PLAYER_INDEX]:
                self.assertIn(f'({NEW_ORIGIN}/{config["slug"]}/)', llms)


if __name__ == '__main__':
    unittest.main()
