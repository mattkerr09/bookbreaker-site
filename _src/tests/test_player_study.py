"""Reproduce the saved study and reject a broken version of every new check."""
from __future__ import annotations

import copy
import csv
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
SITE = SOURCE.parent
sys.path.insert(0, str(SOURCE))

import player_study
from check import BANNED
from content import cta
from pages import PUBLISHED, SEARCH_PAGES
from page_rules import Document, article_issues, clean, jaccard, shingles
from player_study import (MAIN_STAT, PLAYER_FIELDS, PLAYER_READ, PLAYER_SOURCES,
                          player_logs, player_rows, player_spots, player_threshold, report_text, study)

PATH = 'does-a-player-streak-hold-up/index.html'
CONFIG = next(p for p in SEARCH_PAGES if p['slug'] == 'does-a-player-streak-hold-up')
NAME_POISON = 'Private Person Sentinel'


def read(path: str) -> str:
    return (SITE / path).read_text()


def cells(row) -> list[str]:
    return [clean(n.text()) for n in row.children if hasattr(n, 'tag') and n.tag in ('th', 'td')]


def fixture_row(season: int, week: int, value: float = 10, **changes) -> dict:
    return dict(player_id='private-id-sentinel', position='QB', season=str(season), week=str(week),
                season_type='REG', passing_yards=str(value), rushing_yards='0', receiving_yards='0', **changes)


def size_px(value: str, variables: dict, viewport: int) -> float:
    value = value.strip().replace('!important', '')
    if value.startswith('var('):
        return size_px(variables[value[4:-1]], variables, viewport)
    if value.startswith('clamp('):
        lower, preferred, upper = [size_px(v, variables, viewport) for v in value[6:-1].split(',')]
        return max(lower, min(preferred, upper))
    match = re.fullmatch(r'([\d.]+)(rem|px|vw)', value.strip())
    if not match:
        raise AssertionError('unhandled font size: ' + value)
    return float(match[1]) * {'rem': 16, 'px': 1, 'vw': viewport / 100}[match[2]]


def font_sizes(css: str, viewport: int) -> list[float]:
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    variables = dict(re.findall(r'(--[\w-]+)\s*:\s*([^;}]+)', css))
    sizes = []
    for prop, value in re.findall(r'(?:^|[;{])\s*(font-size|font)\s*:\s*([^;}]+)', css):
        if value.strip() == 'inherit':
            continue
        if prop == 'font':
            # Separate the size from weight, line height and family in shorthand.
            match = re.search(r'clamp\([^)]*\)|var\(--t-[\d]+\)|[\d.]+(?:rem|px|vw)\b', value)
            if not match:
                raise AssertionError('unhandled font shorthand: ' + value)
            value = match[0]
        sizes.append(size_px(value, variables, viewport))
    return sizes


def contrast(foreground: str, background: str) -> float:
    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
        return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))
    low, high = sorted((luminance(foreground), luminance(background)))
    return (high + .05) / (low + .05)


class PlayerStudyTests(unittest.TestCase):
    def test_every_saved_output_number(self):
        expected = read('_src/tests/fixtures/player-study-output.txt')
        self.assertEqual(report_text(study()), expected)

    def test_reader_retains_only_allowed_fields(self):
        self.assertEqual(PLAYER_FIELDS, ('player_id', 'position', 'season', 'week', 'season_type',
                                        'passing_yards', 'rushing_yards', 'receiving_yards'))
        raw_reader = csv.reader

        class GuardedCells(list):
            def __getitem__(self, key):
                if isinstance(key, int) and key >= len(PLAYER_FIELDS):
                    raise AssertionError('read a field outside the allowlist')
                return super().__getitem__(key)

        def guarded_reader(handle):
            reader = raw_reader(handle)
            yield next(reader)  # Column headings, without any unapproved values.
            for row in reader:
                yield GuardedCells(row)

        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for year in (2024, 2025):
                with (directory / f'stats_player_week_{year}.csv').open('w', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=[*PLAYER_FIELDS, 'player_name'])
                    writer.writeheader()
                    for week in range(1, 18):
                        writer.writerow(dict(fixture_row(year, week), player_name=NAME_POISON))
                    for row in (dict(fixture_row(year, 18), season_type='POST'),
                                dict(fixture_row(year, 19), position='K'), fixture_row(2026, 1)):
                        writer.writerow(dict(row, player_name=NAME_POISON))
            with patch.object(player_study.csv, 'reader', side_effect=guarded_reader):
                rows = player_rows(directory)
        self.assertEqual(len(rows), 34)
        self.assertTrue(all(set(row) == set(PLAYER_FIELDS) for row in rows))
        self.assertNotIn(NAME_POISON, str(rows))
        self.assertNotIn(NAME_POISON, report_text(study(rows)))

    def test_threshold_uses_2024_only_and_eligibility(self):
        rows = player_rows()
        original = player_logs(rows)
        changed = copy.deepcopy(rows)
        for row in changed:
            if row['season'] == '2025':
                for stat in MAIN_STAT.values():
                    row[stat] = '999999'
        thresholds = lambda logs: {key: player_threshold(log) for key, log in logs.items()}
        self.assertEqual(thresholds(original), thresholds(player_logs(changed)))
        values = [9, 9, 9, 9, 10, 10, 10, 10]
        prior = [{'season': 2024, 'yards': value} for value in values]
        self.assertEqual(player_threshold(prior), 10)  # A 9.5 median rounds up.
        self.assertIsNone(player_threshold(prior[:7]))
        self.assertIsNone(player_threshold([{'season': 2024, 'yards': 9}] * 8))
        self.assertEqual(MAIN_STAT, {'QB': 'passing_yards', 'RB': 'rushing_yards',
                                     'WR': 'receiving_yards', 'TE': 'receiving_yards'})

    def test_no_overlap_prefix_choice_and_partial_horizons(self):
        for log in player_logs(player_rows()).values():
            threshold = player_threshold(log)
            if threshold is None:
                continue
            for window in (5, 10):
                seen, last = [set() for _ in range(5)], [-6] * 5
                for spot in player_spots(log, threshold, window):
                    i, band = spot['index'], spot['band']
                    self.assertEqual(log[i]['season'], 2025)
                    hits = sum(r['yards'] >= threshold for r in log[i - window + 1:i + 1])
                    bounds = (0, .4, .6, .7, .8, 1.01)
                    self.assertTrue(bounds[band] <= hits / window < bounds[band + 1])
                    self.assertEqual(spot['shown'], hits / window)
                    future = list(range(i + 1, min(i + 6, len(log))))
                    self.assertEqual(spot['future'], future)
                    self.assertGreaterEqual(i - last[band], 6)
                    self.assertFalse(seen[band].intersection(future))
                    self.assertEqual(spot['k'], sum(log[j]['yards'] >= threshold for j in future))
                    self.assertEqual(spot['n'], len(future))
                    seen[band].update(future)
                    last[band] = i
        # Change all values after each cutoff. Earlier spot choices stay fixed.
        log = [{'season': 2024 if i < 8 else 2025, 'yards': 10} for i in range(25)]
        for window in (5, 10):
            original = player_spots(log, 10, window)
            self.assertTrue(any(s['n'] < 5 for s in original))
            self.assertTrue(all(s['k'] == s['n'] for s in original))
            for cutoff in range(8, len(log)):
                altered = [dict(r, yards=0) if i > cutoff else r for i, r in enumerate(log)]
                choices = lambda spots: [(s['index'], s['band'], s['shown']) for s in spots if s['index'] <= cutoff]
                self.assertEqual(choices(original), choices(player_spots(altered, 10, window)))

    def test_no_player_identity_or_advice_on_page(self):
        source = read(PATH)
        self.assertNotIn('player_id', source)
        self.assertNotIn(NAME_POISON, source)
        for row in player_rows():
            if row['player_id']:
                self.assertNotIn(row['player_id'], source)
        # Names never cross the input boundary. No player field is rendered.
        self.assertNotRegex(source, r'player_(?:name|display_name|first_name|last_name)')
        text = Document(source).root.all('body')[0].text()
        self.assertNotRegex(text, r'(?i)\b(?:hot|cold|due|lock|should|will)\b|regress to|[\u2013\u2014]')

    def test_page_structure_tables_and_svg_match_study(self):
        source = read(PATH)
        self.assertEqual(article_issues(source, CONFIG), [])
        main = Document(source).root.all('main')[0]
        self.assertIn(cta(player_study=True), source)
        tables = main.all('table')
        self.assertEqual(len(tables), 2)
        svg = main.all('svg')[0]
        self.assertEqual(len(main.all('svg')), 1)
        self.assertEqual(svg.attrs['role'], 'img')
        self.assertEqual(svg.attrs['aria-labelledby'], 'study-title study-desc')
        self.assertEqual(len(svg.all('circle')), 9)
        self.assertEqual(len(svg.all('rect')), 9)
        groups = svg.all('g')
        self.assertEqual(len(groups), 10)
        for panel, (window, result) in enumerate(study().items()):
            self.assertIn(f'Last {window}', tables[panel].all('caption')[0].text())
            rows = tables[panel].all('tbody')[0].all('tr')
            self.assertEqual(len(rows), 5)
            for i, (node, row) in enumerate(zip(rows, result['bands'])):
                group = groups[5 * panel + i]
                self.assertEqual(group.attrs['data-window'], str(window))
                self.assertEqual(group.attrs['data-band'], row['band'])
                if not row['spots']:
                    self.assertEqual(cells(node), [row['band'], '0', 'Not reachable', 'No later games', 'No range'])
                    self.assertFalse(group.all('circle') or group.all('rect') or group.all('line'))
                    continue
                lo, hi = row['range']
                self.assertEqual(cells(node), [row['band'], str(row['spots']), f"{row['shown']:.0%}",
                                               f"{row['k']} of {row['n']} · {row['later']:.0%}", f'{lo:.0%} to {hi:.0%}'])
                self.assertAlmostEqual(float(group.all('rect')[0].attrs['x']) + 4, 18 + 264 * row['shown'], places=2)
                self.assertAlmostEqual(float(group.all('circle')[0].attrs['cx']), 18 + 264 * row['later'], places=2)
                bars = group.classes('study-range')
                self.assertEqual(len(bars), 1)
                bar = bars[0]
                self.assertAlmostEqual(float(bar.attrs['x1']), 18 + 264 * lo, places=2)
                self.assertAlmostEqual(float(bar.attrs['x2']), 18 + 264 * hi, places=2)
        sources = main.classes('sources')[0]
        self.assertEqual({n.attrs['href'] for n in sources.all('a')}, set(PLAYER_SOURCES))
        self.assertEqual(sources.text().count(PLAYER_READ), 2)
        self.assertTrue(3 <= len(main.all('details')) <= 5)
        links = {n.attrs.get('href') for n in main.all('a')}
        self.assertTrue({'/did-the-trend-hold-up/', '/is-a-10-game-trend-reliable/', '/nfl-team-scoring/'} <= links)
        self.assertIn('40% shown became 42% later', clean(main.text()))

    def test_jaccard_below_point_three_against_every_page(self):
        a = shingles(read(PATH))
        for other in PUBLISHED:
            if other.endswith('.html') and other != PATH:
                self.assertLess(jaccard(a, shingles(read(other))), .3, other)

    def test_site_green(self):
        result = subprocess.run([sys.executable, str(SOURCE / 'check.py')], cwd=SITE, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'SITE GREEN')


class StyleTests(unittest.TestCase):
    def test_no_old_product_words_in_css(self):
        css = read('style.css')
        self.assertNotRegex(css, BANNED)
        self.assertNotRegex(css, r'(?i)profit|stake')

    def test_all_font_sizes_are_at_least_twelve_pixels(self):
        for viewport in (375, 1280):
            sizes = font_sizes(read('style.css'), viewport)
            self.assertGreater(len(sizes), 50)
            self.assertGreaterEqual(min(sizes), 12)
        # Include build.py's shared inline styles, which use the same tokens.
        from build import EXTRA_CSS
        self.assertGreaterEqual(min(font_sizes(read('style.css') + EXTRA_CSS, 375)), 12)

    def test_text_palette_meets_aa(self):
        css = read('style.css')
        tokens = dict(re.findall(r'(--[\w-]+):(#[0-9a-f]{6})', css))
        for ink in ('--ink', '--ink-2', '--ink-3', '--accent-hi'):
            for background in ('--bg', '--card', '--card-2', '--sink'):
                self.assertGreaterEqual(contrast(tokens[ink], tokens[background]), 4.5, (ink, background))
        brightness = float(re.search(r'\.btn\.primary:hover\{filter:brightness\(([\d.]+)\)', css)[1])
        for color in re.findall(r'#[0-9a-f]{6}', re.search(r'\.btn\.primary\{([^}]+)', css)[1]):
            self.assertGreaterEqual(contrast('#ffffff', color), 4.5)
            hover = '#' + ''.join(f'{min(255, round(int(color[i:i + 2], 16) * brightness)):02x}'
                                  for i in (1, 3, 5))
            self.assertGreaterEqual(contrast('#ffffff', hover), 4.5)


class PlayerStudyMutationTests(unittest.TestCase):
    def test_every_new_test_rejects_a_broken_input_then_restores(self):
        module = sys.modules[__name__]
        original_read, original_spots = read, player_spots
        changed = study()
        changed[5]['bands'][-1]['k'] += 1
        altered_code = (SOURCE / 'player_study.py').read_text().replace(
            "if r['season'] == 2024", "if r['season'] == 2025")
        namespace = {}
        exec(compile(altered_code, str(SOURCE / 'player_study.py'), 'exec'), namespace)
        mutations = [
            (PlayerStudyTests, 'test_every_saved_output_number', patch.object(module, 'study', return_value=changed)),
            (PlayerStudyTests, 'test_reader_retains_only_allowed_fields',
             patch.object(module, 'PLAYER_FIELDS', PLAYER_FIELDS + ('player_name',))),
            (PlayerStudyTests, 'test_threshold_uses_2024_only_and_eligibility',
             patch.object(module, 'player_threshold', namespace['player_threshold'])),
            (PlayerStudyTests, 'test_no_overlap_prefix_choice_and_partial_horizons',
             patch.object(module, 'player_spots', side_effect=lambda *args:
                          (lambda spots: spots[:1] + spots)(original_spots(*args)))),
            (PlayerStudyTests, 'test_site_green', patch.object(subprocess, 'run', return_value=
                                                            subprocess.CompletedProcess([], 1, 'FAIL', ''))),
        ]
        variants = [
            (PlayerStudyTests, 'test_no_player_identity_or_advice_on_page', PATH, '</main>',
             '<p>player_id ' + NAME_POISON + '</p></main>'),
            (PlayerStudyTests, 'test_page_structure_tables_and_svg_match_study', PATH, '482 of 860', '483 of 860'),
            (PlayerStudyTests, 'test_page_structure_tables_and_svg_match_study', PATH, 'class="study-range"', 'class="missing"'),
            (StyleTests, 'test_no_old_product_words_in_css', 'style.css', '/* Shared dark', '/* profit stake odds. Shared dark'),
            (StyleTests, 'test_all_font_sizes_are_at_least_twelve_pixels', 'style.css', '--t-1:.8125rem', '--t-1:.7rem'),
            (StyleTests, 'test_all_font_sizes_are_at_least_twelve_pixels', 'style.css', 'font:400 17px', 'font:400 11px'),
            (StyleTests, 'test_text_palette_meets_aa', 'style.css', '--ink-3:#969dad', '--ink-3:#333333'),
            (StyleTests, 'test_text_palette_meets_aa', 'style.css', 'brightness(1.04)', 'brightness(1.12)'),
        ]
        for cls, method, target, before, after in variants:
            self.assertIn(before, original_read(target))
            mutation = patch.object(module, 'read', side_effect=lambda p, t=target, b=before, a=after:
                                    original_read(p).replace(b, a) if p == t else original_read(p))
            mutations.append((cls, method, mutation))
        mutations.append((PlayerStudyTests, 'test_jaccard_below_point_three_against_every_page',
                          patch.object(module, 'read', side_effect=lambda p:
                                       original_read(PATH) if p == 'index.html' else original_read(p))))
        checked = set()
        for cls, method, mutation in mutations:
            with self.subTest(test=method), mutation:
                result = unittest.TestResult()
                cls(method).run(result)
                self.assertTrue(result.failures, f'mutation survived: {method}; errors: {result.errors}')
                checked.add(method)
        expected = {name for cls in (PlayerStudyTests, StyleTests) for name in dir(cls) if name.startswith('test_')}
        self.assertEqual(checked, expected)


if __name__ == '__main__':
    unittest.main()
