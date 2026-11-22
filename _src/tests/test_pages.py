from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

SOURCE = Path(__file__).resolve().parents[1]
SITE = SOURCE.parent
sys.path.insert(0, str(SOURCE))

from articles import cost_rows, later
from content import CLAIMS, FACTS, cta, e, fact, table
from costs import annual_cost, planned_cost
from build import ORIGIN
from pages import DATA_PAGES, DATA_PATHS, NFL_INDEX, PLAYER_DATA_PAGES, PLAYER_INDEX, PLAYER_PATHS, PUBLISHED, SEARCH_PAGES, SEARCH_PATHS
from player_data import PLAYER_2026_READ
from stats import NFL_READ, NFL_SOURCE, example, held_up, season_scores, wilson
from page_rules import Document, article_issues, clean, jaccard, registry_issues, shingles, words


def read(path: str) -> str:
    return (SITE / path).read_text()


class BuildAndPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = subprocess.run([sys.executable, str(SOURCE / 'build.py')], cwd=SITE, text=True, capture_output=True)

    def test_build_and_checker_are_real_subprocesses(self):
        self.assertEqual(self.build.returncode, 0, self.build.stdout + self.build.stderr)
        check = subprocess.run([sys.executable, str(SOURCE / 'check.py')], cwd=SITE, text=True, capture_output=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn('SITE GREEN', check.stdout)

    def test_inventory_sitemap_llms_and_no_extra_pages(self):
        self.assertEqual(len(SEARCH_PAGES), 8)
        self.assertEqual(len(set(SEARCH_PATHS)), 8)
        self.assertEqual(set(PUBLISHED), set(SEARCH_PATHS + DATA_PATHS + PLAYER_PATHS) | {'index.html', 'pricing/index.html', 'privacy/index.html', 'streak-checker/index.html', 'streak-checker/nfl.json', 'streak-checker/checker.js', '404.html', 'llms.txt', 'robots.txt', 'sitemap.xml', 'README.md'})
        actual = {str(p.relative_to(SITE)) for p in SITE.rglob('*.html')
                  if not any(part.startswith('.') for part in p.relative_to(SITE).parts)
                  and p.relative_to(SITE).parts[0] != '_src'}
        self.assertEqual(actual, set(SEARCH_PATHS + DATA_PATHS + PLAYER_PATHS) | {'index.html', 'pricing/index.html', 'privacy/index.html', 'streak-checker/index.html', '404.html'})
        sitemap = ET.fromstring(read('sitemap.xml'))
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        entries = {u.find('s:loc', ns).text: u.find('s:lastmod', ns).text for u in sitemap}
        expected_urls = {ORIGIN + '/', ORIGIN + '/pricing/', ORIGIN + '/privacy/', ORIGIN + '/streak-checker/'} | {
            f'{ORIGIN}/{p["slug"]}/' for p in SEARCH_PAGES + DATA_PAGES + PLAYER_DATA_PAGES}
        self.assertEqual(set(entries), expected_urls)
        self.assertEqual({entries[f'{ORIGIN}/{p["slug"]}/'] for p in PLAYER_DATA_PAGES}, {PLAYER_2026_READ})
        self.assertEqual(entries[f'{ORIGIN}/streak-checker/'], PLAYER_2026_READ)
        self.assertEqual({v for k, v in entries.items() if k not in {f'{ORIGIN}/{p["slug"]}/' for p in PLAYER_DATA_PAGES}
                          | {f'{ORIGIN}/streak-checker/'}}, {'2026-11-21'})
        llms = read('llms.txt').split('## Guides and answers\n')[1]
        for page in SEARCH_PAGES:
            self.assertIn(f'{ORIGIN}/{page["slug"]}/', llms)
            self.assertIn(page['note'], llms)
        self.assertFalse((SITE / 'guides').exists())

    def test_template_guides_links_and_shared_early_cta(self):
        self.assertIn(cta(), read('index.html'))
        home = Document(read('index.html')).root
        home_lists = [n for n in home.all('main')[0].all('ul') if n.attrs.get('aria-label') == 'Guides']
        self.assertEqual(len(home_lists), 1)
        self.assertEqual(len(home_lists[0].all('a')), 10)
        for path in ['index.html', 'pricing/index.html', 'privacy/index.html', '404.html', *SEARCH_PATHS, *DATA_PATHS, *PLAYER_PATHS]:
            source = read(path)
            doc = Document(source).root
            self.assertEqual(len(doc.all('header')), 1, path)
            self.assertEqual(len(doc.all('footer')), 1, path)
            self.assertEqual(source.count('href="https://kerrandcompanyholdings.com/"'), 1, path)
            footer = doc.all('footer')[0]
            lists = [n for n in footer.all('ul') if n.attrs.get('aria-label') == 'Guides']
            self.assertEqual(len(lists), 1, path)
            links = {n.attrs['href'] for n in lists[0].all('a')}
            self.assertEqual(links, {f'/{p["slug"]}/' for p in SEARCH_PAGES + [NFL_INDEX, PLAYER_INDEX]}, path)
        for path in SEARCH_PATHS + DATA_PATHS + PLAYER_PATHS:
            self.assertIn(cta(player_study=path == 'does-a-player-streak-hold-up/index.html' or path in PLAYER_PATHS), read(path))

    def test_article_metadata_structure_and_word_limits(self):
        for config in SEARCH_PAGES:
            path = f'{config["slug"]}/index.html'
            with self.subTest(path=path):
                self.assertEqual(article_issues(read(path), config), [])

    def test_no_twins_including_home(self):
        sets = [(path, shingles(read(path))) for path in ['index.html', *SEARCH_PATHS]]
        for i, (path, a) in enumerate(sets):
            for other, b in sets[i + 1:]:
                self.assertLess(jaccard(a, b), 0.3, f'{path} / {other}: {jaccard(a, b):.6f}')

    def test_fact_and_claim_registries_are_unique_and_planned(self):
        raw_facts = json.loads(read('_src/data/facts.json'))
        raw_claims = json.loads(read('_src/data/claims.json'))
        self.assertEqual(len(FACTS), len(raw_facts))
        self.assertEqual(len(CLAIMS), len(raw_claims))
        for entry in raw_facts:
            self.assertEqual(set(entry), {'id', 'subject', 'text', 'source', 'readAt'})
            self.assertTrue(entry['text'])
            self.assertRegex(entry['readAt'], r'^2026-11-(20|21)(T[0-9:]+Z)?$')
            expected_sources = {
                'Linemate': 'https://apps.apple.com/us/app/id1635246793',
                'PropsMadness': 'https://www.propsmadness.com/',
                'Dimers Pro': 'https://www.dimers.com/subscription',
                'Method': 'PLAN-FIXES.md, section 1',
                'NBA': 'PLAN-FIXES.md, section 2',
                'NFL': 'PLAN-FIXES.md, section 2',
            }
            self.assertIn(entry['subject'], expected_sources)
            self.assertEqual(entry['source'], expected_sources[entry['subject']])
        for entry in raw_claims:
            self.assertEqual(set(entry), {'id', 'text', 'status'})
            self.assertEqual(entry['status'], 'planned')
            self.assertRegex(entry['text'], r'\bwill\b')

    def test_every_marked_fact_and_claim_matches_its_registry(self):
        for path in ['index.html', 'pricing/index.html', 'privacy/index.html', '404.html', *SEARCH_PATHS, *DATA_PATHS, *PLAYER_PATHS]:
            self.assertEqual(registry_issues(read(path), FACTS, CLAIMS), [], path)

    def test_links_are_exact_fact_sources_or_existing_allowed_hosts(self):
        from check import ALLOWED_HOSTS, NFL_LICENSE
        approved_sources = {entry['source'] for entry in FACTS.values() if entry['source'].startswith('https://')}
        hosts = ALLOWED_HOSTS | {urlsplit(NFL_LICENSE).hostname}
        for path in ['index.html', 'pricing/index.html', 'privacy/index.html', '404.html', *SEARCH_PATHS, *DATA_PATHS, *PLAYER_PATHS]:
            for node in Document(read(path)).root.all('a'):
                href = node.attrs.get('href', '')
                if href.startswith('https://'):
                    url = urlsplit(href)
                    self.assertTrue(href in approved_sources or url.hostname in hosts or url.hostname == 'bookbreaker.bet', (path, href))

    def test_checker_allows_fact_hosts_and_rejects_other_hosts(self):
        import check
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / '_src/data').mkdir(parents=True)
            (site / '_src/data/facts.json').write_text(json.dumps(list(FACTS.values())))
            with patch.object(check, 'SITE', site), patch.object(check, 'PUBLISHED', ['index.html']):
                self.assertTrue({'apps.apple.com', 'www.propsmadness.com', 'www.dimers.com'} <= check.allowed_hosts())
                for url, status in [('https://apps.apple.com/us/app/id1635246793', 0),
                                    ('https://creativecommons.org/licenses/by/4.0/', 0),
                                    ('https://unlisted.example/page', 1)]:
                    (site / 'index.html').write_text(f'<a href="{url}">Source</a>')
                    with redirect_stdout(io.StringIO()) as output:
                        self.assertEqual(check.main(), status)
                    self.assertIn('SITE GREEN' if status == 0 else
                                  'outbound link to unlisted.example is not allowed', output.getvalue())

    def test_league_patterns_are_code_text_without_placeholder_links(self):
        doc = Document(read('free-nba-player-game-logs/index.html')).root
        patterns = {'nba.com/stats/player/<id>/boxscores-traditional',
                    'nfl.com/players/<slug>/stats/logs/'}
        self.assertEqual({n.text() for n in doc.all('code')}, patterns)
        for node in doc.all('a'):
            self.assertNotIn('<id>', node.attrs.get('href', ''))
            self.assertNotIn('<slug>', node.attrs.get('href', ''))
        for key in ('nba-logs', 'nfl-logs'):
            self.assertIn('tested in a browser on 20 November 2026', FACTS[key]['text'])

    def test_plain_copy_and_no_retired_product_name(self):
        prohibited = re.compile(r'\b(?:best|beats|seamless|unlock|elevate|game.changer|supercharge|revolutioni[sz]e|effortless|empower|leverage|cutting.edge|streamline|revolutionary|unleash|game.changing)\b|#1\b|better than|unlike other apps|the only|not just[^.]*but', re.I)
        for path in ['index.html', 'pricing/index.html', 'privacy/index.html', '404.html', *SEARCH_PATHS]:
            source = read(path)
            self.assertNotRegex(Document(source).root.text(), prohibited, path)
            self.assertNotRegex(source, r'[\u2013\u2014]', path)
            self.assertNotRegex(source, r'(?i)outlier', path)

    def test_all_shipped_team_numbers_reproduce(self):
        x = example()
        source = read('how-often-did-a-player-clear-a-number/index.html')
        for label, k, n, lo, hi in [('Last 10 played', x['last_k'], x['last_n'], x['last_lo'], x['last_hi']),
                                   ('2025 regular season', x['k'], x['n'], x['lo'], x['hi'])]:
            self.assertIn(f'{label}</th><td>{k} of {n}</td>', source)
            self.assertIn(f'<td>{lo}% to {hi}%</td>', source)
        for game in x['games'][-10:]:
            self.assertIn(f'{game["date"]}</th><td>{game["site"]}</td><td>{game["opponent"]}</td><td>{game["points"]}</td>', source)
        source = read('is-a-10-game-trend-reliable/index.html')
        for n in (5, 10, 20):
            k = 3 * n // 5
            lo, hi = (round(100 * v) for v in wilson(k, n))
            self.assertIn(f'{k} of {n}</th><td>60%</td><td>{lo}% to {hi}%</td>', source)
        source = read('did-the-trend-hold-up/index.html')
        for row in held_up(season_scores()):
            self.assertIn(f'{e(row["band"])}</th><td>{row["spots"]}</td><td>{row["n"]}</td><td>{row["k"]} of {row["n"]} · {row["pct"]}%</td><td>{row["lo"]}% to {row["hi"]}%</td>', source)
        for path in SEARCH_PATHS:
            if path == 'does-a-player-streak-hold-up/index.html':
                continue  # This study cites the player CSVs, rather than schedules.
            self.assertIn(NFL_SOURCE, read(path))
            self.assertIn(NFL_READ, read(path))

    def test_later_table_suppresses_rates_and_ranges_for_tiny_samples(self):
        with patch('articles.season_scores', return_value={'A': [{'points': 24}] * 12}):
            source = later(example())
        rows = Document(source).root.all('tbody')[0].all('tr')
        self.assertEqual(len(rows), 5)
        for row in rows:
            cells = row.all('td')
            self.assertEqual(clean(cells[2].text()), 'Too few past spots to tell')
            self.assertEqual(clean(cells[3].text()), 'No score')
        self.assertEqual(clean(rows[-1].all('td')[1].text()), '2')

    def test_worked_costs_use_decimal_prices_and_keep_missing_plans_missing(self):
        self.assertEqual(annual_cost('$59.99', '$59.99', 3), '$179.97')
        self.assertEqual(annual_cost('$99.99', '$199.99', 3), '$499.97')
        self.assertEqual(annual_cost('$250.00', '$250.00', 2), '$500.00')
        self.assertEqual([planned_cost(y, True) for y in (1, 2, 3)], ['$39.00', '$58.00', '$77.00'])
        self.assertEqual(planned_cost(3, False), '$39.00')
        with self.assertRaises(ValueError):
            annual_cost('$59.99', '$59.99', 0)
        self.assertIn(table(['App', 'Assumption', 'First annual price', '1 year total', '2 years total', '3 years total'], cost_rows(),
                            'Costs if the stated annual prices stay fixed'), read('pay-once-sports-stats-app/index.html'))
        self.assertEqual(len(cost_rows()), 6)
        self.assertEqual({row[0] for row in cost_rows()[:4]},
                         {fact(r + '-name', 'th') for r in ('linemate', 'madness', 'dimers')})

    def test_build_is_repeatable_and_does_not_write_forbidden_files(self):
        paths = ['CNAME', '1d72346274f3ba1a3957eb72beea0f75.txt', '39a190ab445d73f57af4ed54a6992c18.txt', 'robots.txt',
                 'index.html', 'pricing/index.html', 'privacy/index.html', '404.html', 'sitemap.xml', 'llms.txt', *SEARCH_PATHS, *DATA_PATHS, *PLAYER_PATHS]
        before = {path: hashlib.sha256((SITE / path).read_bytes()).hexdigest() for path in paths}
        result = subprocess.run([sys.executable, str(SOURCE / 'build.py')], cwd=SITE, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, {path: hashlib.sha256((SITE / path).read_bytes()).hexdigest() for path in paths})

    def test_source_parses_on_python_39(self):
        for path in SOURCE.rglob('*.py'):
            ast.parse(path.read_text(), filename=str(path), feature_version=9)


if __name__ == '__main__':
    unittest.main()
