"""The streak checker: its data matches the player pages, and its browser script matches an independent recount."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
SITE = SOURCE.parent
sys.path.insert(0, str(SOURCE))

import checker  # noqa: E402
from nfl_players import player_reports  # noqa: E402
from pages import PLAYER_PAGES  # noqa: E402


def reference(values, t, window):
    """Written apart from checker.SCRIPT: band by integer percent, spots from the trailing window, 5 later games each."""
    window = min(window, len(values))
    def band_of(k, n):
        pct = 100 * k / n
        return 0 if pct < 40 else 1 if pct < 60 else 2 if pct < 70 else 3 if pct < 80 else 4
    k = sum(v >= t for v in values[-window:])
    target = band_of(k, window)
    x = y = spots = 0
    d = window - 1
    while d < len(values):
        if band_of(sum(v >= t for v in values[d - window + 1:d + 1]), window) == target:
            later = values[d + 1:d + 6]
            spots += bool(later)
            x += sum(v >= t for v in later)
            y += len(later)
            d += 5
        else:
            d += 1
    return {'k': k, 'n': window, 'band': target, 'x': x, 'y': y, 'spots': spots, 'tooFew': y < 15}


class CheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((SITE / 'streak-checker' / 'nfl.json').read_text())
        cls.by_name = {}
        for p in cls.data['players']:
            cls.by_name.setdefault(p['n'], []).append(p)

    def test_published_data_is_the_built_data(self):
        self.assertEqual(self.data, json.loads(json.dumps(checker.checker_data())))
        self.assertEqual((SITE / 'streak-checker' / 'checker.js').read_text(), checker.SCRIPT)

    def test_every_player_page_log_matches_the_checker_data(self):
        reports = player_reports()
        for p in PLAYER_PAGES:
            r = reports[p['player_id']]
            matches = [c for c in self.by_name.get(p['name'], []) if c['s'] == p['stat'].replace('_', ' ')]
            self.assertTrue(matches, p['name'])
            values = [g[2] for g in matches[0]['g']]
            # The 2025 season and the 2026 games sit inside the checker's log in the same order.
            season = r['scores'] + [g['yards'] for g in r['now']]
            text = ','.join(map(str, values))
            self.assertIn(','.join(map(str, season)), text, p['name'])

    def test_shape_and_rules(self):
        self.assertGreater(len(self.data['players']), 600)
        for p in self.data['players']:
            self.assertGreaterEqual(len(p['g']), checker.MIN_GAMES)
            self.assertEqual(p['g'], sorted(p['g']))
            self.assertTrue(all(0 <= g[1] < len(self.data['teams']) and isinstance(g[2], int) for g in p['g']))
            self.assertIn(p['p'], ('QB', 'RB', 'WR', 'TE'))
            self.assertEqual(p['m'] % 5, 0)

    @unittest.skipUnless(shutil.which('node'), 'node is not installed')
    def test_browser_script_matches_independent_recount(self):
        cases = []
        for i, p in enumerate(self.data['players'][::7]):
            for t in (p['m'], p['m'] + 15, max(0, p['m'] - 20)):
                for window in (5, 10):
                    cases.append((self.data['players'].index(p), t, window))
        program = ("const c = require(process.argv[1]); const d = require(process.argv[2]);"
                   "const cases = JSON.parse(process.argv[3]);"
                   "console.log(JSON.stringify(cases.map(([i, t, w]) => c.check(d.players[i], t, w))));")
        result = subprocess.run(['node', '-e', program, str(SITE / 'streak-checker' / 'checker.js'),
                                 str(SITE / 'streak-checker' / 'nfl.json'), json.dumps(cases)],
                                capture_output=True, text=True, check=True)
        got = json.loads(result.stdout)
        self.assertGreater(len(cases), 500)
        for (i, t, window), answer in zip(cases, got):
            values = [g[2] for g in self.data['players'][i]['g']]
            self.assertEqual(answer, reference(values, t, window), (self.data['players'][i]['n'], t, window))
        self.assertTrue(any(not a['tooFew'] for a in got) and any(a['tooFew'] for a in got))


if __name__ == '__main__':
    unittest.main()
