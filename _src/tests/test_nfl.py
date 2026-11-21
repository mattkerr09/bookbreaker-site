"""Recount the batch from allowlisted source rows, then reject broken copies."""
from __future__ import annotations

import csv
import io
import math
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from itertools import combinations, product
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
SITE = SOURCE.parent
sys.path.insert(0, str(SOURCE))

import build
import stats
from content import cta
from nfl import answer, team_report
from pages import DATA_PAGES, DATA_PATHS, NFL_TEAMS, PUBLISHED, TEAM_PAGES
from page_rules import Document, article_issues, clean, jaccard, shingles, words
from stats import NFL_READ, NFL_SOURCE, SCHEDULE_FIELDS, schedule_rows, season_scores, wilson

# These are test field names, never values read from the real file.
FORBIDDEN = ('away_moneyline', 'home_moneyline', 'spread_line', 'away_spread_odds', 'home_spread_odds',
             'total_line', 'under_odds', 'over_odds', 'result', 'total')
FIELD_POISON = '987654.321987'
SEASON_POISON = '999983'


def read(path: str) -> str:
    return (SITE / path).read_text()


def setUpModule():
    result = subprocess.run([sys.executable, str(SOURCE / 'build.py')], cwd=SITE, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)


def raw_games(code: str, season: int = 2025) -> list[dict]:
    """Independent team view and recount, using the one safe CSV entry point."""
    result = []
    for row in sorted(schedule_rows(season=season), key=lambda r: (r['gameday'], r['game_id'])):
        if code not in (row['home_team'], row['away_team']):
            continue
        side = 'home' if row['home_team'] == code else 'away'
        other = 'away' if side == 'home' else 'home'
        result.append(dict(week=int(row['week']), date=row['gameday'], side=side,
                           points=int(row[side + '_score']), allowed=int(row[other + '_score']),
                           opponent=row[other + '_team'], overtime=row['overtime'] == '1',
                           division=row['div_game'] == '1'))
    return result


def main(path: str):
    return Document(read(path)).root.all('main')[0]


def cells(row) -> list[str]:
    return [clean(n.text()) for n in row.children if hasattr(n, 'tag') and n.tag in ('th', 'td')]


def fixture(path: Path, extra: list[dict] | None = None, poison: bool = False) -> None:
    fields = list(SCHEDULE_FIELDS) + (list(FORBIDDEN) if poison else [])
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in schedule_rows(season=2024) + schedule_rows() + (extra or []):
            # All real rows here have already crossed the allowlist boundary.
            writer.writerow(dict(row, **({key: FIELD_POISON for key in FORBIDDEN} if poison else {})))


def rebuild_from(path: Path) -> dict[str, str]:
    safe_reader = stats.schedule_rows
    with tempfile.TemporaryDirectory() as folder:
        with patch.object(build, 'SITE', Path(folder)), patch.object(
                stats, 'schedule_rows', side_effect=lambda _path, season: safe_reader(path, season)):
            with redirect_stdout(io.StringIO()):
                build.main()
        return {p: (Path(folder) / p).read_text() for p in PUBLISHED if (Path(folder) / p).exists()}


class NFLScoringTests(unittest.TestCase):
    def test_inventory_mapping_and_sitemap(self):
        self.assertEqual(len(NFL_TEAMS), 32)
        codes = {r[side + '_team'] for r in schedule_rows() for side in ('home', 'away')}
        self.assertEqual({t['abbreviation'] for t in NFL_TEAMS}, codes)
        for key in ('abbreviation', 'name', 'slug'):
            self.assertEqual(len({t[key] for t in NFL_TEAMS}), 32)
        for team in NFL_TEAMS:
            self.assertEqual(set(team), {'abbreviation', 'name', 'slug'})
            self.assertRegex(team['slug'], r'^[a-z0-9]+(?:-[a-z0-9]+)+$')
        self.assertEqual(len(DATA_PATHS), 33)
        self.assertEqual(len(set(DATA_PATHS)), 33)
        self.assertEqual(set(DATA_PATHS), {p for p in PUBLISHED if p.startswith('nfl-team-scoring/')})
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        entries = {u.find('s:loc', ns).text: u.find('s:lastmod', ns).text
                   for u in ET.fromstring(read('sitemap.xml'))}
        for path in DATA_PATHS:
            self.assertTrue((SITE / path).is_file(), path)
            self.assertEqual(entries['https://bookbreaker.bet/' + path.removesuffix('index.html')], '2026-11-21')
        self.assertEqual(read('llms.txt').count('[NFL team scoring](https://bookbreaker.bet/nfl-team-scoring/)'), 1)

    def test_metadata_content_and_links(self):
        current, previous = season_scores(), season_scores(season=2024)
        for team in TEAM_PAGES:
            path = team['slug'] + '/index.html'
            source, node = read(path), main(path)
            report = team_report(current[team['abbreviation']], previous[team['abbreviation']])
            self.assertEqual(article_issues(source, dict(team, answer=answer(team, report))), [], path)
            self.assertIn(cta(), source)
            self.assertEqual(len(node.all('table')), 5)
            self.assertEqual(len(node.classes('trend-card')), 3)
            self.assertEqual(len(node.classes('held-card')), 1)
            self.assertIn('Held up later', node.classes('held-card')[0].text())
            self.assertEqual(len(node.all('svg')), 1)
            self.assertTrue(3 <= len(node.all('details')) <= 5)
            self.assertIn(NFL_SOURCE, source)
            self.assertIn(NFL_READ, node.classes('sources')[0].text())
            self.assertIn('PLAN-FIXES.md, section 1', node.classes('sources')[0].text())
            expected_codes = []
            for game in reversed(raw_games(team['abbreviation'])):
                if game['division'] and game['opponent'] not in expected_codes:
                    expected_codes.append(game['opponent'])
            expected_rivals = {f'/{t["slug"]}/' for t in TEAM_PAGES if t['abbreviation'] in expected_codes[:2]}
            links = {n.attrs['href'] for n in node.classes('onward')[0].all('a')}
            self.assertEqual(links, expected_rivals | {'/nfl-team-scoring/', '/did-the-trend-hold-up/',
                                                     '/is-a-10-game-trend-reliable/'})
            self.assertNotRegex(node.text(), r'(?i)\b(?:best|hot|cold|lock|due|should)\b|#1|will score')
            self.assertNotRegex(source, '[\u2013\u2014]')

    def test_every_game_trend_and_split_matches_source(self):
        names = {t['abbreviation']: t['name'] for t in NFL_TEAMS}
        for team in TEAM_PAGES:
            games = raw_games(team['abbreviation'])
            node = main(team['slug'] + '/index.html')
            rows = node.all('table')[0].all('tbody')[0].all('tr')
            self.assertEqual(len(rows), len(games))
            self.assertEqual(len(games), 17)
            for row, g in zip(rows, games):
                self.assertEqual(cells(row), [str(g['week']), g['date'], names[g['opponent']], g['side'].capitalize(),
                                             str(g['points']), str(g['allowed']), 'Yes' if g['overtime'] else 'No'])
            scores = [g['points'] for g in games]
            median = sorted(scores)[len(scores) // 2]
            cards = node.classes('trend-card')
            self.assertEqual([int(c.attrs['data-threshold']) for c in cards], [median - 7, median, median + 7])
            for threshold, card in zip((median - 7, median, median + 7), cards):
                for row, label, selected in zip(card.all('tbody')[0].all('tr'), ('Last 5', 'Last 10', 'Season'),
                                                (scores[-5:], scores[-10:], scores)):
                    k, n = sum(s >= threshold for s in selected), len(selected)
                    lo, hi = (round(100 * v) for v in wilson(k, n))
                    self.assertEqual(cells(row), [label, f'{k} of {n}', str(n), f'{lo}% to {hi}%'])
            predicates = (lambda g: g['side'] == 'home', lambda g: g['side'] == 'away',
                          lambda g: g['division'], lambda g: not g['division'])
            for row, label, predicate in zip(node.all('table')[-1].all('tbody')[0].all('tr'),
                                             ('Home', 'Away', 'Division', 'Other opponents'), predicates):
                selected = [g['points'] for g in games if predicate(g)]
                k, n = sum(s >= median for s in selected), len(selected)
                lo, hi = (round(100 * v) for v in wilson(k, n))
                self.assertEqual(cells(row), [label, f'{k} of {n}', f'{lo}% to {hi}%'])

    def test_detroit_independent_recount_and_wilson_reference(self):
        games = raw_games('DET')
        scores = [g['points'] for g in games]
        ppg = sum(scores) / len(scores)
        k, n = sum(p >= 24 for p in scores), len(scores)
        self.assertEqual((k, n), (12, 17))
        self.assertEqual(sum(scores), 481)
        self.assertEqual(tuple(round(100 * v) for v in wilson(12, 17)), (47, 87))
        rows = main('nfl-team-scoring/index.html').all('tbody')[0].all('tr')
        detroit = next(row for row in rows if cells(row)[0] == 'Detroit Lions')
        self.assertEqual(cells(detroit), ['Detroit Lions', str(n), f'{ppg:.1f}', f'{k} of {n}', '47% to 87%'])
        first = main('nfl-team-scoring/detroit-lions/index.html').all('p')[0].text()
        self.assertIn(f'{sum(scores)} points across {n} games', first)
        self.assertIn(f'{ppg:.1f} per game', first)
        self.assertIn(f'24 points in {k} of {n}', first)

    def test_later_check_independent_recount_and_suppression(self):
        for team in TEAM_PAGES:
            code = team['abbreviation']
            current = [g['points'] for g in raw_games(code)]
            threshold = sorted(current)[len(current) // 2]
            percentage = 10 * sum(s >= threshold for s in current[-10:])
            limits = (0, 40, 60, 70, 80, 101)
            lower, upper = next((a, b) for a, b in zip(limits, limits[1:]) if a <= percentage < b)
            scores = [g['points'] for g in raw_games(code, 2024)] + current
            d, x, y, spots = 9, 0, 0, 0
            used = []
            while d < len(scores):
                pct = 10 * sum(s >= threshold for s in scores[d - 9:d + 1])
                if lower <= pct < upper:
                    future = list(range(d + 1, min(d + 6, len(scores))))
                    used += future
                    spots += bool(future)
                    x += sum(scores[i] >= threshold for i in future)
                    y += len(future)
                    d += 5
                else:
                    d += 1
            self.assertEqual(len(used), len(set(used)))
            report = team_report(season_scores()[code], season_scores(season=2024)[code])
            self.assertEqual((report['later']['k'], report['later']['n'], report['later']['spots']), (x, y, spots))
            held = clean(main(team['slug'] + '/index.html').classes('held-card')[0].text())
            self.assertIn(f'Past spots with later games: {spots} · Later games: {y}', held)
            self.assertIn('Search: 2024 and 2025 regular seasons. Horizon: 5 played games.', held)
            if y < 15:
                self.assertIn('too few past spots to tell', held)
                self.assertNotIn(f'{x} of {y}', held)
                self.assertNotIn('Wilson 95% range:', held)
            else:
                lo, hi = (round(100 * v) for v in wilson(x, y))
                self.assertIn(f'{x} of {y}', held)
                self.assertIn(f'Wilson 95% range: {lo}% to {hi}%', held)
                self.assertNotIn('too few past spots to tell', held)

    def test_forbidden_fields_and_values_never_reach_pages(self):
        for path in DATA_PATHS:
            source = read(path)
            for field in FORBIDDEN:
                self.assertNotRegex(source.lower(), rf'\b{field}\b')
            self.assertNotIn(FIELD_POISON, source)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'games.csv'
            fixture(path, poison=True)
            rows = schedule_rows(path)
            self.assertTrue(rows)
            for row in rows:
                self.assertEqual(set(row), set(SCHEDULE_FIELDS))
                self.assertNotIn(FIELD_POISON, row.values())
            generated = rebuild_from(path)
        for path, source in generated.items():
            self.assertEqual(source, read(path), path)
            self.assertNotIn(FIELD_POISON, source)

    def test_2026_season_is_excluded_even_with_completed_rows(self):
        extra = dict(schedule_rows()[0], season='2026', gameday='2026-09-01', game_id='2026_poison',
                     home_score=SEASON_POISON, away_score=SEASON_POISON)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'games.csv'
            fixture(path, extra=[extra])
            self.assertEqual({r['season'] for r in schedule_rows(path)}, {'2025'})
            self.assertEqual({r['season'] for r in schedule_rows(path, 2024)}, {'2024'})
            with self.assertRaises(ValueError):
                season_scores(path, 2026)
            generated = rebuild_from(path)
        for path, source in generated.items():
            self.assertNotIn(SEASON_POISON, source)
            self.assertEqual(source, read(path), path)
        self.assertIn('the 2026 season is not used', clean(main('nfl-team-scoring/index.html').text()))

    def test_jaccard_limits_for_every_pair(self):
        teams = [(p, shingles(read(p))) for p in DATA_PATHS[1:]]
        others = [(p, shingles(read(p))) for p in PUBLISHED if p.endswith('.html') and p not in DATA_PATHS[1:]]
        for (left, a), (right, b) in combinations(teams, 2):
            self.assertLess(jaccard(a, b), .5, f'{left} / {right}')
        for (left, a), (right, b) in product(teams, others):
            self.assertLess(jaccard(a, b), .3, f'{left} / {right}')

    def test_index_sortable_table_and_all_team_numbers(self):
        node = main('nfl-team-scoring/index.html')
        table = node.all('table')[0]
        headers = table.all('thead')[0].all('th')
        self.assertEqual([h.attrs.get('aria-sort') for h in headers], ['ascending', None, None, None, None])
        self.assertEqual(len(table.all('button')), 5)
        self.assertTrue(all(b.attrs.get('type') == 'button' for b in table.all('button')))
        rows = table.all('tbody')[0].all('tr')
        self.assertEqual(len(rows), 32)
        self.assertEqual([cells(row)[0] for row in rows], sorted(t['name'] for t in NFL_TEAMS))
        for row, team in zip(rows, sorted(NFL_TEAMS, key=lambda t: t['name'])):
            scores = [g['points'] for g in raw_games(team['abbreviation'])]
            k, n = sum(s >= 24 for s in scores), len(scores)
            lo, hi = (round(100 * v) for v in wilson(k, n))
            self.assertEqual(cells(row), [team['name'], str(n), f'{sum(scores) / n:.1f}',
                                         f'{k} of {n}', f'{lo}% to {hi}%'])
            self.assertEqual(row.all('a')[0].attrs['href'], f'/nfl-team-scoring/{team["slug"]}/')
            self.assertEqual(float(row.all('td')[1].attrs['data-sort']), sum(scores) / n)
        source = read('nfl-team-scoring/index.html')
        self.assertIn("button.addEventListener('click'", source)
        self.assertIn("Number(left) - Number(right)", source)
        config = DATA_PAGES[0]
        self.assertEqual(article_issues(source, dict(config, answer=clean(node.all('p')[0].text()))), [])

    def test_svg_has_each_week_and_exact_score(self):
        for team in TEAM_PAGES:
            games = raw_games(team['abbreviation'])
            svg = main(team['slug'] + '/index.html').all('svg')[0]
            self.assertEqual(svg.attrs['role'], 'img')
            self.assertEqual(svg.attrs['aria-labelledby'], 'score-title score-desc')
            self.assertEqual(len(svg.all('circle')), 17)
            self.assertEqual(svg.all('title')[0].attrs['id'], 'score-title')
            self.assertEqual(svg.all('desc')[0].attrs['id'], 'score-desc')
            top = math.ceil(max(g['points'] for g in games) / 10) * 10
            expected = ' '.join(f"{40 + (g['week'] - 1) * 30},{178 - g['points'] / top * 140:.1f}" for g in games)
            self.assertEqual(svg.all('polyline')[0].attrs['points'], expected)
            for dot, game in zip(svg.all('circle'), games):
                self.assertIn(f"Week {game['week']}: {game['points']} points", dot.text())


class NFLMutationTests(unittest.TestCase):
    def test_every_new_check_rejects_a_broken_input(self):
        """Run each new test against a broken input, with patches restored at exit."""
        module = sys.modules[__name__]
        original_read = read
        original_reader = schedule_rows
        det = 'nfl-team-scoring/detroit-lions/index.html'
        idx = 'nfl-team-scoring/index.html'
        mutations = [
            ('test_inventory_mapping_and_sitemap', 'inventory', patch.object(module, 'DATA_PATHS', DATA_PATHS[:-1])),
            ('test_inventory_mapping_and_sitemap', 'mapping', patch.object(module, 'NFL_TEAMS', NFL_TEAMS[:-1])),
            ('test_forbidden_fields_and_values_never_reach_pages', 'field leak',
             patch.object(module, 'read', side_effect=lambda p: original_read(p) + (FIELD_POISON if p == det else ''))),
            ('test_2026_season_is_excluded_even_with_completed_rows', 'season leak',
             patch.object(module, 'schedule_rows', side_effect=lambda path=stats.NFL_FILE, season=2025:
                          original_reader(path, season) + ([dict(original_reader(path, season)[0], season='2026')]
                                                         if path != stats.NFL_FILE else []))),
            ('test_jaccard_limits_for_every_pair', 'team twin',
             patch.object(module, 'read', side_effect=lambda p: original_read(det) if p == DATA_PATHS[1] else original_read(p))),
            ('test_jaccard_limits_for_every_pair', 'other twin',
             patch.object(module, 'read', side_effect=lambda p: original_read('index.html') if p == det else original_read(p))),
        ]
        variants = [
            ('test_metadata_content_and_links', 'missing log', det, '<table>', '<section>'),
            ('test_metadata_content_and_links', 'missing trend', det, 'class="ex trend-card"', 'class="ex"'),
            ('test_metadata_content_and_links', 'missing held line', det, 'Held up later', 'Missing'),
            ('test_metadata_content_and_links', 'missing FAQ', det, '<details>', '<section>'),
            ('test_metadata_content_and_links', 'missing source', det, 'PLAN-FIXES.md, section 1', 'Missing source'),
            ('test_metadata_content_and_links', 'missing rival', det, 'href="/nfl-team-scoring/chicago-bears/"', 'href="/missing/"'),
            ('test_every_game_trend_and_split_matches_source', 'wrong game score', det, '<td>13</td>', '<td>999</td>'),
            ('test_every_game_trend_and_split_matches_source', 'wrong trend', det, 'data-threshold="17"', 'data-threshold="18"'),
            ('test_detroit_independent_recount_and_wilson_reference', 'wrong average', idx, '>28.3</td>', '>28.4</td>'),
            ('test_later_check_independent_recount_and_suppression', 'wrong horizon', det, 'Horizon: 5 played games.', 'Horizon: 4 played games.'),
            ('test_index_sortable_table_and_all_team_numbers', 'wrong sort', idx, 'aria-sort="ascending"', 'aria-sort="descending"'),
            ('test_svg_has_each_week_and_exact_score', 'wrong SVG', det, '<polyline points="', '<polyline points="0,0 '),
        ]
        for method, label, path, before, after in variants:
            self.assertIn(before, original_read(path), label)
            def altered(p, target=path, before=before, after=after):
                text = original_read(p)
                return text.replace(before, after) if p == target else text
            mutations.append((method, label, patch.object(module, 'read', side_effect=altered)))
        checked = set()
        for method, label, mutation in mutations:
            with self.subTest(mutation=label), mutation:
                result = unittest.TestResult()
                NFLScoringTests(method).run(result)
                self.assertTrue(result.failures or result.errors, 'mutation survived: ' + label)
                checked.add(method)
        self.assertEqual(checked, {name for name in dir(NFLScoringTests) if name.startswith('test_')})


if __name__ == '__main__':
    unittest.main()
