"""Offline redirect checks, including deliberately broken copies of each part."""
from __future__ import annotations

import csv
import io
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

SOURCE = Path(__file__).resolve().parents[1]
SITE = SOURCE.parent
sys.path.insert(0, str(SOURCE))

from build import ORIGIN
import redirects
from page_rules import Document, clean


class RedirectTests(unittest.TestCase):
    def test_mapping_covers_sitemap_and_extras_with_identical_paths(self):
        entries = [node.text for node in ET.parse(SITE / 'sitemap.xml').findall(
            '{http://www.sitemaps.org/schemas/sitemap/0.9}url/'
            '{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
        pairs = redirects.mapping(SITE / 'sitemap.xml', redirects.NEW_ORIGIN)
        old_urls = [old for old, new in pairs]
        extras = {ORIGIN + p for p in ('/llms.txt', '/sitemap.xml', '/robots.txt', '/privacy/')}
        self.assertEqual(set(old_urls), set(entries) | extras)
        self.assertEqual(len([old for old in old_urls if old in entries]), len(entries))
        self.assertEqual(len(old_urls), len(set(old_urls)))
        for old, new in pairs:
            self.assertEqual(urlsplit(old).path, urlsplit(new).path)
            self.assertEqual(urlsplit(new).netloc, 'streakgauge.com')
            self.assertEqual(urlsplit(new).scheme, 'https')

    def test_mapping_deduplicates_and_keeps_trailing_slashes(self):
        with tempfile.TemporaryDirectory() as directory:
            sitemap = Path(directory) / 'sitemap.xml'
            paths = ['/', '/privacy/', '/privacy/', '/Case%20kept/', '/no-slash']
            sitemap.write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(
                f'<url><loc>{ORIGIN}{path}</loc></url>' for path in paths) + '</urlset>')
            pairs = redirects.mapping(sitemap, redirects.NEW_ORIGIN + '/')
        self.assertEqual([urlsplit(old).path for old, new in pairs],
                         ['/', '/privacy/', '/Case%20kept/', '/no-slash', '/llms.txt', '/sitemap.xml', '/robots.txt'])
        self.assertTrue(all(new == redirects.NEW_ORIGIN + urlsplit(old).path for old, new in pairs))
        with self.assertRaises(ValueError):
            redirects.mapping(SITE / 'sitemap.xml', redirects.NEW_ORIGIN.replace('streakgauge.com', 'wrong.example'))

    def test_csv_has_no_header_and_320_data_rows_and_saved_artifact(self):
        pairs = redirects.mapping(SITE / 'sitemap.xml', redirects.NEW_ORIGIN)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'redirects.csv'
            redirects.write_csv(pairs, out)
            with out.open(newline='') as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(out.read_bytes(), (SITE / '_launch/bulk-redirects.csv').read_bytes())
        self.assertEqual(len(rows), 320)
        self.assertEqual([tuple(row[:2]) for row in rows], pairs)
        for row in rows:
            self.assertEqual(len(row), 7)
            self.assertEqual(row[2:], ['301', 'true', 'false', 'false', 'false'])

    def test_stubs_have_only_canonical_refresh_and_visible_target(self):
        pairs = redirects.mapping(SITE / 'sitemap.xml', redirects.NEW_ORIGIN)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            redirects.write_stubs(pairs, out)
            self.assertEqual(len([p for p in out.rglob('*') if p.is_file()]), len(pairs))
            for old, new in pairs:
                path = urlsplit(old).path
                rel = path.lstrip('/') + ('index.html' if path.endswith('/') else '')
                source = (out / rel).read_text()
                doc = Document(source).root
                self.assertEqual([n.attrs for n in doc.all('link')], [{'rel': 'canonical', 'href': new}])
                self.assertEqual([n.attrs['content'] for n in doc.all('meta')
                    if n.attrs.get('http-equiv') == 'refresh'], ['0; url=' + new])
                self.assertEqual([n.attrs['href'] for n in doc.all('a')], [new])
                self.assertEqual(clean(doc.all('body')[0].text()), 'This page has moved.')
                self.assertEqual(set(re.findall(r'https?://[^"<>\s]+', source)), {new})
                self.assertEqual(doc.all('script'), [])
        with self.assertRaises(ValueError):
            redirects.write_stubs(pairs, SITE)

    def test_verify_rejects_each_miss_and_continues(self):
        pairs = redirects.mapping(SITE / 'sitemap.xml', redirects.NEW_ORIGIN)[:5]
        responses = [(302, {'Location': pairs[0][1]}), (200, {}),
                     (301, {'Location': pairs[2][1] + 'wrong'}), (301, {}),
                     (301, {'location': pairs[4][1]})]
        calls = []
        def transport(url):
            calls.append(url)
            return responses[len(calls) - 1]
        output = io.StringIO()
        self.assertEqual(redirects.verify(pairs, transport, output), 1)
        self.assertEqual(calls, [old for old, new in pairs])
        self.assertEqual(output.getvalue().count('MISS '), 4)
        self.assertIn('5 redirects checked; 4 misses', output.getvalue())
        for old, new in pairs[:4]:
            self.assertIn('MISS ' + old, output.getvalue())

    def test_verify_passes_correct_301_and_reports_transport_errors(self):
        pairs = redirects.mapping(SITE / 'sitemap.xml', redirects.NEW_ORIGIN)[:1]
        output = io.StringIO()
        self.assertEqual(redirects.verify(pairs, lambda url: (301, {'Location': pairs[0][1]}), output), 0)
        self.assertIn('1 redirects checked; 0 misses', output.getvalue())
        def unavailable(url):
            raise OSError('offline')
        self.assertEqual(redirects.verify(pairs, unavailable, output), 1)
        self.assertIn('offline', output.getvalue())

    def test_transport_makes_one_get_without_following_location(self):
        with patch.object(redirects.http.client, 'HTTPSConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 301
            response.getheaders.return_value = [('Location', redirects.NEW_ORIGIN + '/')]
            self.assertEqual(redirects.request(ORIGIN + '/?keep=yes'),
                             (301, {'Location': redirects.NEW_ORIGIN + '/'}))
            connection.assert_called_once_with('bookbreaker.bet', timeout=15)
            connection.return_value.request.assert_called_once_with('GET', '/?keep=yes')
            connection.return_value.getresponse.assert_called_once_with()
            connection.return_value.close.assert_called_once_with()

    def test_cli_verify_returns_failure_without_network(self):
        pairs = dict(redirects.mapping(SITE / 'sitemap.xml', redirects.NEW_ORIGIN))
        probes = {
            ORIGIN + '/no-such-page/': 'https://streakgauge.com/no-such-page/',
            ORIGIN + '/llms.txt?x=1': 'https://streakgauge.com/llms.txt?x=1',
            ORIGIN.replace('://', '://www.') + '/no-such-page/': 'https://streakgauge.com/no-such-page/',
        }
        self.assertTrue(probes.keys().isdisjoint(pairs))
        expected = {**pairs, **probes}
        calls = []
        def transport(url):
            calls.append(url)
            return 301, {'Location': expected[url]}
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(redirects.main(['--verify'], lambda url: (200, {})), 1)
            self.assertEqual(redirects.main(['--verify'], transport), 0)
            self.assertEqual(calls, list(expected))
            self.assertIn('323 redirects checked; 0 misses', output.getvalue())
            for probe in probes:
                with self.subTest(probe=probe):
                    def broken(url):
                        if url == probe:
                            if '?' in url:
                                return 301, {'Location': expected[url].split('?')[0]}
                            return 200, {}
                        return 301, {'Location': expected[url]}
                    self.assertEqual(redirects.main(['--verify'], broken), 1)


class RedirectMutationTests(unittest.TestCase):
    def test_redirect_checks_reject_broken_code_and_restore(self):
        source = (SOURCE / 'redirects.py').read_text()
        cases = [
            ('test_cli_verify_returns_failure_without_network', 'return verify(pairs, transport)',
             'return verify(pairs[:-3], transport)'),
            ('test_cli_verify_returns_failure_without_network', '+ "/llms.txt?x=1"', '+ "/llms.txt"'),
            ('test_mapping_covers_sitemap_and_extras_with_identical_paths',
             'for old in dict.fromkeys(urls)', 'for old in dict.fromkeys(urls[1:])'),
            ('test_mapping_covers_sitemap_and_extras_with_identical_paths',
             'new_origin.rstrip("/") + urlsplit(old).path', 'new_origin.rstrip("/") + "/wrong/"'),
            ('test_csv_has_no_header_and_320_data_rows_and_saved_artifact', 'writer = csv.writer(stream)',
             'writer = csv.writer(stream); writer.writerow(("source_url", "target_url", "status_code", "preserve_query_string", "include_subdomains", "subpath_matching", "preserve_path_suffix"))'),
            ('test_csv_has_no_header_and_320_data_rows_and_saved_artifact', '301, "true", "false", "false", "false"',
             '302, "false", "true", "true", "true"'),
            ('test_stubs_have_only_canonical_refresh_and_visible_target', 'rel="canonical"', 'rel="wrong"'),
            ('test_stubs_have_only_canonical_refresh_and_visible_target', 'content="0; url={url}"', 'content="1; url={url}"'),
            ('test_stubs_have_only_canonical_refresh_and_visible_target', '</head><body>',
             '</head><body><a href="https://unlisted.example/">Other</a>'),
            ('test_verify_rejects_each_miss_and_continues', 'status == 301 and location == new',
             'status in (301, 302) and location == new'),
            ('test_verify_rejects_each_miss_and_continues', 'status == 301 and location == new',
             'status in (200, 301) and location in (None, new)'),
            ('test_verify_rejects_each_miss_and_continues', 'status == 301 and location == new', 'status == 301'),
            ('test_verify_passes_correct_301_and_reports_transport_errors', 'status == 301 and location == new', 'False'),
        ]
        for method, before, after in cases:
            with self.subTest(method=method, mutation=after):
                self.assertIn(before, source)
                altered = {'__file__': str(SOURCE / 'redirects.py')}
                exec(compile(source.replace(before, after), str(SOURCE / 'redirects.py'), 'exec'), altered)
                names = ['mapping', 'write_csv', 'write_stubs', 'verify', 'main']
                with patch.multiple(redirects, **{name: altered[name] for name in names}):
                    result = unittest.TestResult()
                    RedirectTests(method).run(result)
                    self.assertTrue(result.failures or result.errors, 'mutation survived')
                result = unittest.TestResult()
                RedirectTests(method).run(result)
                self.assertTrue(result.wasSuccessful(), result.failures or result.errors)


if __name__ == '__main__':
    unittest.main()
