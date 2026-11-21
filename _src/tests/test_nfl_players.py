"""Recount the player batch and break each new check in memory before restoring it."""
from __future__ import annotations

import copy
import csv
import itertools
import math
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
SITE = SOURCE.parent
sys.path.insert(0, str(SOURCE))

import player_data
from content import cta
from nfl_players import (POSITION_FIELDS, player_answer, player_body, player_reports)
from pages import PLAYER_INDEX, PLAYER_PAGES, PLAYER_PATHS, PUBLISHED, TEAM_PAGES
from player_data import MAIN_STAT, PLAYER_PAGE_FIELDS, PLAYER_READ, PLAYER_SOURCES, player_catalog, read_player_rows, thresholds
from page_rules import Document, article_issues, clean, jaccard, shingles
from stats import NFL_SOURCE

FORBIDDEN = ('headshot_url', 'fantasy_points', 'fantasy_points_ppr', 'passing_epa', 'rushing_epa', 'receiving_epa',
             'cpoe', 'pacr', 'racr', 'wopr', 'target_share', 'air_yards_share', 'odds', 'spread_line', 'moneyline')
POISON = 'DiscardedFieldSentinel728391'
ADVICE = re.compile(r'\b(?:hot|cold|due|lock|should|will|expect|projection|fantasy|start|sit)\b', re.I)
SAMPLE = 'nfl-player-stats/aaron-rodgers/index.html'


def read(path):
    return (SITE / path).read_text()


def cells(row):
    return [clean(n.text()) for n in row.children if hasattr(n, 'tag') and n.tag in ('th', 'td')]


def main(path):
    return Document(read(path)).root.all('main')[0]


def reference_lines(mid):
    base = math.ceil(mid)
    return tuple(5 * ((round(base * fraction * 4) + 10) // 20) for fraction in (.75, 1, 1.25))


def reference_count(values, t):
    k, n = sum(v >= t for v in values), len(values)
    # Formula written independently of stats.wilson, with a fixed 95% z.
    z2 = 1.96 ** 2
    lo = (k + z2 / 2 - 1.96 * math.sqrt(k * (1 - k / n) + z2 / 4)) / (n + z2)
    hi = (k + z2 / 2 + 1.96 * math.sqrt(k * (1 - k / n) + z2 / 4)) / (n + z2)
    return [f'{k} of {n}', str(n), f'{round(100 * lo)}% to {round(100 * hi)}%']


def fixture(directory, rows, poison=True):
    for season in (2024, 2025):
        with (directory / f'stats_player_week_{season}.csv').open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=[*PLAYER_PAGE_FIELDS, *(FORBIDDEN if poison else ())])
            writer.writeheader()
            for row in rows:
                if row['season'] in (str(season), '2026'):
                    writer.writerow(dict(row, **({key: POISON for key in FORBIDDEN} if poison else {})))


def synthetic(name='Same Name', pos='QB', team='DET', identity='a', value='20'):
    return [dict.fromkeys(PLAYER_PAGE_FIELDS, '0') | dict(player_id=identity, player_display_name=name,
            position=pos, season='2025', week=str(w), season_type='REG', game_id=f'game-{w}',
            team=team, opponent_team='GB', **{MAIN_STAT[pos]: value}) for w in range(1, 9)]


class NFLPlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = read_player_rows()
        cls.reports = player_reports(cls.rows)

    def test_eligible_set_and_count_by_position(self):
        logs = defaultdict(list)
        for row in self.rows:
            if row['season'] == '2025':
                logs[row['player_id']].append(row)
        wanted = set()
        for identity, log in logs.items():
            pos = log[-1]['position']
            values = sorted(float(r[{'QB': 'passing_yards', 'RB': 'rushing_yards',
                                      'WR': 'receiving_yards', 'TE': 'receiving_yards'}[pos]] or 0) for r in log)
            n = len(values)
            mid = (values[(n - 1) // 2] + values[n // 2]) / 2
            if n >= 8 and mid >= 10:
                wanted.add((identity, pos))
        self.assertEqual({(p['player_id'], p['position']) for p in PLAYER_PAGES}, wanted)
        self.assertEqual(len(PLAYER_PAGES), 273)
        self.assertEqual(Counter(p['position'] for p in PLAYER_PAGES), {'QB': 37, 'RB': 60, 'WR': 116, 'TE': 60})
        self.assertEqual(player_catalog(synthetic(value='9.5')), [])
        self.assertEqual(len(player_catalog(synthetic(value='10'))), 1)
        self.assertEqual(player_catalog(synthetic()[:7]), [])

    def test_unique_slugs_and_collision_suffixes(self):
        self.assertEqual(len({p['slug'] for p in PLAYER_PAGES}), len(PLAYER_PAGES))
        for p in PLAYER_PAGES:
            self.assertRegex(p['slug'], '^nfl-player-stats/[a-z0-9]+(?:-[a-z0-9]+)*$')
        rows = (synthetic(identity='a', team='DET') + synthetic(identity='b', team='GB') +
                synthetic(pos='WR', identity='c'))
        self.assertEqual({p['short_slug'] for p in player_catalog(rows)}, {'same-name-qb-det', 'same-name-qb-gb', 'same-name-wr'})
        self.assertEqual(player_catalog(synthetic(name="D'Andre Test Jr."))[0]['short_slug'], 'd-andre-test-jr')

    def test_every_page_parts_metadata_and_answer(self):
        for p in PLAYER_PAGES:
            path = p['slug'] + '/index.html'
            r, source, node = self.reports[p['player_id']], read(path), main(path)
            self.assertEqual(article_issues(source, dict(p, answer=player_answer(p, r))), [], path)
            self.assertIn(cta(True), source)
            self.assertEqual(len(node.all('table')), 5, path)
            self.assertEqual(len(node.classes('trend-card')), 3)
            self.assertEqual(len(node.classes('held-card')), 1)
            self.assertEqual(len(node.all('details')), 3)
            self.assertEqual(len(node.all('svg')), 1)
            sources = node.classes('sources')[0]
            self.assertTrue(set(PLAYER_SOURCES) | {NFL_SOURCE} <= {n.attrs['href'] for n in sources.all('a')})
            self.assertIn(PLAYER_READ, sources.text())
            self.assertIn('PLAN-FIXES.md, section 1', sources.text())
            links = {n.attrs['href'] for n in node.classes('onward')[0].all('a')}
            self.assertTrue({'/nfl-player-stats/', '/does-a-player-streak-hold-up/'} <= links)
            self.assertTrue({f'/{t["slug"]}/' for t in TEAM_PAGES if t['abbreviation'] in p['teams']} <= links)
            peers = [other for other in PLAYER_PAGES if other != p and other['position'] == p['position']
                     and set(other['teams']) & set(p['teams'])][:2]
            self.assertTrue({f'/{other["slug"]}/' for other in peers} <= links)
            self.assertTrue(node.classes('player-observation'))

    def test_every_log_trend_split_and_chart(self):
        for p in PLAYER_PAGES:
            r, node = self.reports[p['player_id']], main(p['slug'] + '/index.html')
            rows = node.all('table')[0].all('tbody')[0].all('tr')
            self.assertEqual(len(rows), p['games'])
            fields = POSITION_FIELDS[p['position']]
            from nfl import TEAM_BY_CODE
            for row, g in zip(rows, r['games']):
                self.assertEqual(cells(row), [str(g['week']), g['date'], TEAM_BY_CODE[g['opponent']]['name'],
                                              g['site'].capitalize(), *[str(g[k]) for k, _ in fields]])
            lines = reference_lines(p['median'])
            self.assertEqual(tuple(int(c.attrs['data-threshold']) for c in node.classes('trend-card')), lines)
            for t, card in zip(lines, node.classes('trend-card')):
                for row, label, values in zip(card.all('tbody')[0].all('tr'), ('Last 5', 'Last 10', 'Season'),
                                               (r['scores'][-5:], r['scores'][-10:], r['scores'])):
                    self.assertEqual(cells(row), [label, *reference_count(values, t)])
            groups = ([g['yards'] for g in r['games'] if g['site'] == 'home'],
                      [g['yards'] for g in r['games'] if g['site'] == 'away'],
                      [g['yards'] for g in r['games'] if g['division']],
                      [g['yards'] for g in r['games'] if not g['division']])
            for row, label, values in zip(node.all('table')[-1].all('tbody')[0].all('tr'),
                                          ('Home', 'Away', 'Division', 'Other opponents'), groups):
                result = reference_count(values, lines[1]) if values else ['No played games', '0', 'No range']
                self.assertEqual(cells(row), [label, result[0], result[2]])
            svg = node.all('svg')[0]
            self.assertEqual(svg.attrs['role'], 'img')
            self.assertEqual(svg.attrs['aria-labelledby'], 'player-title player-desc')
            self.assertEqual(len(svg.all('circle')), len(r['games']))
            top = max(10, math.ceil(max(r['scores'] + [p['median']]) / 50) * 50)
            expected = ' '.join(f"{40 + (g['week'] - 1) * 30},{178 - g['yards'] / top * 140:.1f}" for g in r['games'])
            self.assertEqual(svg.all('polyline')[0].attrs['points'], expected)
            self.assertEqual(svg.classes('median-line')[0].attrs['y1'], f"{178 - p['median'] / top * 140:.1f}")
            for dot, g in zip(svg.all('circle'), r['games']):
                self.assertIn(f"Week {g['week']}: {g['yards']} yards", dot.text())

    def test_independent_recount_for_qb_rb_wr(self):
        frozen = {'Josh Allen': ('QB', 16, 3668), 'Derrick Henry': ('RB', 17, 1595),
                  'Justin Jefferson': ('WR', 17, 1048)}
        for name, (position, n, total) in frozen.items():
            p = next(p for p in PLAYER_PAGES if p['name'] == name)
            stat = {'QB': 'passing_yards', 'RB': 'rushing_yards', 'WR': 'receiving_yards'}[position]
            rows = sorted([r for r in self.rows if r['player_id'] == p['player_id'] and r['season'] == '2025'],
                          key=lambda r: int(r['week']))
            scores = [int(float(r[stat] or 0)) for r in rows]
            self.assertEqual((len(scores), sum(scores)), (n, total))
            r = self.reports[p['player_id']]
            self.assertEqual(r['scores'], scores)
            self.assertEqual(r['threshold'], reference_lines(median(scores))[1])
            # Compare the independently recounted window directly with the shipped card.
            card = main(p['slug'] + '/index.html').classes('trend-card')[1]
            self.assertEqual(cells(card.all('tbody')[0].all('tr')[1]),
                             ['Last 10', *reference_count(scores[-10:], r['threshold'])])
            for game, raw in zip(r['games'], rows):
                self.assertEqual(game['id'], raw['game_id'])
                self.assertEqual(game['team'], raw['team'])
                self.assertEqual(game['opponent'], raw['opponent_team'])

    def test_later_independent_spots_and_suppression(self):
        for p in PLAYER_PAGES:
            r = self.reports[p['player_id']]
            values = [int(float(row[p['stat']] or 0)) for row in sorted(
                [row for row in self.rows if row['player_id'] == p['player_id']],
                key=lambda row: (int(row['season']), int(row['week'])))]
            t = reference_lines(p['median'])[1]
            pct = 100 * sum(v >= t for v in r['scores'][-10:]) / min(10, len(r['scores']))
            limits = (0, 40, 60, 70, 80, 101)
            lower, upper = next((a, b) for a, b in zip(limits, limits[1:]) if a <= pct < b)
            d, k, n, spots, used = 9, 0, 0, 0, []
            while d < len(values):
                shown = 10 * sum(v >= t for v in values[d - 9:d + 1])
                if lower <= shown < upper:
                    future = list(range(d + 1, min(d + 6, len(values))))
                    k += sum(values[i] >= t for i in future)
                    n += len(future)
                    spots += bool(future)
                    used.extend(future)
                    d += 5
                else:
                    d += 1
            self.assertEqual(len(used), len(set(used)))
            self.assertEqual((r['later']['k'], r['later']['n'], r['later']['spots']), (k, n, spots))
            held = clean(main(p['slug'] + '/index.html').classes('held-card')[0].text())
            self.assertIn(f'Past spots with later games: {spots} · Later games: {n}', held)
            self.assertIn('Horizon: 5 played games.', held)
            if n < 15:
                self.assertIn('too few past spots to tell', held)
                self.assertNotIn(f'{k} of {n}', held)
                self.assertNotIn('Wilson 95% range:', held)
            else:
                self.assertNotIn('too few past spots to tell', held)
                self.assertIn(f'{k} of {n}', held)
                self.assertIn(f'Wilson 95% range: {reference_count([1] * k + [0] * (n - k), 1)[2]}', held)

    def test_allowlist_guards_and_poison_values(self):
        allowed = ('player_id', 'player_display_name', 'position', 'season', 'week', 'season_type', 'game_id',
                   'team', 'opponent_team', 'completions', 'attempts', 'passing_yards', 'passing_tds',
                   'passing_interceptions', 'carries', 'rushing_yards', 'rushing_tds', 'receptions', 'targets',
                   'receiving_yards', 'receiving_tds')
        self.assertEqual(PLAYER_PAGE_FIELDS, allowed)
        original_reader = csv.reader

        class GuardedCells(list):
            def __getitem__(self, index):
                if not isinstance(index, int) or index >= len(allowed):
                    raise AssertionError('accessed a forbidden cell')
                return super().__getitem__(index)

        def guarded_reader(handle):
            reader = original_reader(handle)
            yield next(reader)
            for row in reader:
                yield GuardedCells(row)

        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            fixture(directory, self.rows)
            with patch.object(player_data.csv, 'reader', side_effect=guarded_reader):
                safe = read_player_rows(directory)
            self.assertEqual(safe, self.rows)
            self.assertTrue(all(set(r) == set(allowed) for r in safe))
            poisoned_reports = player_reports(safe)
            for p in PLAYER_PAGES:
                body = player_body(p, poisoned_reports[p['player_id']])
                self.assertNotIn(POISON, body)
                self.assertIn(body, read(p['slug'] + '/index.html'))
        with self.assertRaises(ValueError):
            read_player_rows(fields=(*allowed, 'headshot_url'))
        for path in PLAYER_PATHS:
            source = read(path)
            self.assertNotIn(POISON, source)
            for field in FORBIDDEN:
                self.assertNotRegex(source, rf'(?i)\b{field}\b')

    def test_missed_games_never_become_zero_rows(self):
        p = next(p for p in PLAYER_PAGES if p['name'] == 'Brock Purdy')
        raw = [r for r in self.rows if r['player_id'] == p['player_id'] and r['season'] == '2025']
        self.assertLess(len(raw), 17)
        log = self.reports[p['player_id']]['games']
        self.assertEqual({g['week'] for g in log}, {int(r['week']) for r in raw})
        self.assertEqual(len(log), len(raw))
        self.assertEqual([g['yards'] for g in log], [int(float(r[p['stat']] or 0)) for r in sorted(raw, key=lambda r: int(r['week']))])
        self.assertEqual(len(main(p['slug'] + '/index.html').all('table')[0].all('tbody')[0].all('tr')), len(raw))
        eight = next(p for p in PLAYER_PAGES if p['games'] == 8)
        self.assertEqual(self.reports[eight['player_id']]['last']['n'], 8)

    def test_2026_and_postseason_rows_excluded(self):
        extras = [dict(self.rows[0], season='2026', passing_yards='987654321'),
                  dict(self.rows[-1], season_type='POST', receiving_yards='987654321')]
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            fixture(directory, self.rows + extras)
            rows = read_player_rows(directory)
            self.assertEqual(rows, self.rows)
            self.assertEqual({r['season'] for r in rows}, {'2024', '2025'})
            self.assertEqual({r['season_type'] for r in rows}, {'REG'})
            self.assertEqual(player_catalog(rows), PLAYER_PAGES)
            self.assertEqual(player_reports(rows), self.reports)
        for r in self.reports.values():
            self.assertEqual({g['season'] for g in r['games']}, {2025})

    def test_no_images_or_advice_and_plain_words(self):
        for path in PLAYER_PATHS:
            source = read(path)
            doc = Document(source).root
            self.assertEqual(doc.all('img'), [])
            self.assertEqual(doc.all('image'), [])
            self.assertNotIn('headshot', source.lower())
            self.assertNotRegex(source, '[\u2013\u2014]')
            text = clean(doc.all('main')[0].text())
            # Will Dissly is a recorded display name, never a future-tense verb.
            for p in PLAYER_PAGES:
                text = text.replace(p['name'], '')
            self.assertNotRegex(text, ADVICE)
            self.assertNotRegex(text, r'(?i)\b(?:seamless|unleash|supercharge|revolutionary)\b')

    def test_index_team_lists_and_sitemap(self):
        source = read('nfl-player-stats/index.html')
        node = main('nfl-player-stats/index.html')
        issues = article_issues(source, dict(PLAYER_INDEX, answer=clean(node.all('p')[0].text())))
        # A four-position directory table is longer than an individual article.
        self.assertEqual(issues, ['main length', 'body length'])
        tables = node.all('table')
        self.assertEqual(len(tables), 4)
        self.assertIn(cta(True), read('nfl-player-stats/index.html'))
        for position, table in zip(('QB', 'RB', 'WR', 'TE'), tables):
            players = [p for p in PLAYER_PAGES if p['position'] == position]
            for p, row in zip(players, table.all('tbody')[0].all('tr')):
                r = self.reports[p['player_id']]
                self.assertEqual(cells(row), [p['name'], ', '.join(p['teams']), str(p['games']), f'{p["median"]:g}',
                                              str(r['threshold']), *[reference_count(r['scores'][-10:], r['threshold'])[i] for i in (0, 2)]])
                self.assertEqual(row.all('a')[0].attrs['href'], f'/{p["slug"]}/')
            self.assertEqual(len(table.all('tbody')[0].all('tr')), len(players))
        for team in TEAM_PAGES:
            section = main(team['slug'] + '/index.html').classes('team-players')
            self.assertEqual(len(section), 1)
            self.assertEqual({n.attrs['href'] for n in section[0].all('a')},
                             {f'/{p["slug"]}/' for p in PLAYER_PAGES if team['abbreviation'] in p['teams']})
        self.assertEqual(set(PLAYER_PATHS), {p for p in PUBLISHED if p.startswith('nfl-player-stats/')})
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        entries = {u.find('s:loc', ns).text: u.find('s:lastmod', ns).text for u in ET.fromstring(read('sitemap.xml'))}
        for path in PLAYER_PATHS:
            self.assertEqual(entries['https://bookbreaker.bet/' + path.removesuffix('index.html')], '2026-11-21')
        self.assertEqual(read('llms.txt').count('[NFL player stats](https://bookbreaker.bet/nfl-player-stats/)'), 1)

    def test_jaccard_limits(self):
        sets = {p: shingles(read(p)) for p in PUBLISHED if p.endswith('.html')}
        players = PLAYER_PATHS[1:]
        for a, b in itertools.combinations(players, 2):
            self.assertLess(jaccard(sets[a], sets[b]), .5, f'{a} / {b}')
        others = [p for p in sets if p not in players]
        for a, b in itertools.product(players, others):
            self.assertLess(jaccard(sets[a], sets[b]), .3, f'{a} / {b}')

    def test_site_green(self):
        result = subprocess.run([sys.executable, str(SOURCE / 'check.py')], cwd=SITE, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'SITE GREEN')


class NFLPlayerMutationTests(unittest.TestCase):
    def test_each_new_check_fails_when_broken_then_restores(self):
        module = sys.modules[__name__]
        NFLPlayerTests.setUpClass()
        original_read, original_reader = read, read_player_rows
        altered = copy.deepcopy(NFLPlayerTests.reports)
        purdy = next(p['player_id'] for p in PLAYER_PAGES if p['name'] == 'Brock Purdy')
        altered[purdy]['games'].append(dict(altered[purdy]['games'][0], week=2, yards=0))
        mutations = [
            ('test_eligible_set_and_count_by_position', patch.object(module, 'PLAYER_PAGES', PLAYER_PAGES[:-1])),
            ('test_unique_slugs_and_collision_suffixes', patch.object(module, 'PLAYER_PAGES', PLAYER_PAGES + PLAYER_PAGES[:1])),
            ('test_missed_games_never_become_zero_rows', patch.object(NFLPlayerTests, 'reports', altered)),
            ('test_allowlist_guards_and_poison_values', patch.object(module, 'PLAYER_PAGE_FIELDS', (*PLAYER_PAGE_FIELDS, 'headshot_url'))),
            ('test_2026_and_postseason_rows_excluded', patch.object(module, 'read_player_rows', side_effect=lambda path:
                original_reader(path) + [dict(NFLPlayerTests.rows[0], season='2026')])),
            ('test_site_green', patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, 'FAIL', ''))),
        ]
        variants = [
            ('test_every_page_parts_metadata_and_answer', SAMPLE, 'class="ex trend-card"', 'class="ex"'),
            ('test_every_page_parts_metadata_and_answer', SAMPLE, 'property="og:title"', 'property="missing"'),
            ('test_every_log_trend_split_and_chart', SAMPLE, '<polyline points="', '<polyline points="0,0 '),
            ('test_every_log_trend_split_and_chart', SAMPLE, 'class="median-line"', 'class="missing"'),
            ('test_independent_recount_for_qb_rb_wr', 'nfl-player-stats/josh-allen/index.html', 'Last 10</th>', 'Wrong window</th>'),
            ('test_later_independent_spots_and_suppression', SAMPLE, 'Horizon: 5 played games.', 'Horizon: 4 played games.'),
            ('test_no_images_or_advice_and_plain_words', SAMPLE, '</main>', '<img src="/photo.png"></main>'),
            ('test_no_images_or_advice_and_plain_words', SAMPLE, '</main>', '<p>He will reach it.</p></main>'),
            ('test_index_team_lists_and_sitemap', 'nfl-player-stats/index.html', '<table>', '<section>'),
            ('test_allowlist_guards_and_poison_values', SAMPLE, '</main>', f'<p>{POISON}</p></main>'),
        ]
        for method, path, before, after in variants:
            self.assertIn(before, original_read(path))
            mutations.append((method, patch.object(module, 'read', side_effect=lambda p, t=path, b=before, a=after:
                             original_read(p).replace(b, a) if p == t else original_read(p))))
        # Fail fast on the first pair for both similarity classes.
        first, second = PLAYER_PATHS[1:3]
        for target in (second, 'index.html'):
            mutations.append(('test_jaccard_limits', patch.object(module, 'read', side_effect=lambda p, t=target:
                              original_read(first) if p == t else original_read(p))))
        checked = set()
        for method, mutation in mutations:
            with self.subTest(test=method), mutation:
                result = unittest.TestResult()
                NFLPlayerTests(method).run(result)
                self.assertTrue(result.failures or result.errors, f'mutation survived: {method}')
                checked.add(method)
        self.assertEqual(checked, {m for m in dir(NFLPlayerTests) if m.startswith('test_')})


if __name__ == '__main__':
    unittest.main()
