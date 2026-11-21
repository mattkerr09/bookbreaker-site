from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stats import BANDS, band, example, held_up, rate, season_scores, spots, wilson


class StatisticsTests(unittest.TestCase):
    def test_wilson_known_values_and_boundaries(self):
        self.assertEqual(tuple(round(100 * v) for v in wilson(12, 17)), (47, 87))
        # Independent reference endpoints, including the zero and all-success cases.
        self.assertAlmostEqual(wilson(3, 5)[0], 0.2307199322)
        self.assertAlmostEqual(wilson(3, 5)[1], 0.8823817688)
        self.assertAlmostEqual(wilson(6, 10)[0], 0.3126695475)
        self.assertAlmostEqual(wilson(12, 20)[1], 0.7811960326)
        self.assertEqual(wilson(0, 5)[0], 0)
        self.assertEqual(wilson(5, 5)[1], 1)
        for args in ((0, 0), (-1, 5), (6, 5)):
            with self.assertRaises(ValueError):
                wilson(*args)

    def test_season_reader_orders_games_and_excludes_incomplete_and_postseason(self):
        fields = ["season", "game_type", "gameday", "game_id", "home_team", "away_team", "home_score", "away_score"]
        rows = [
            ["2025", "REG", "2025-09-14", "b", "DET", "GB", "24", "10"],
            ["2025", "REG", "2025-09-07", "a", "GB", "DET", "13", "23"],
            ["2025", "REG", "2025-09-21", "c", "DET", "GB", "NA", "NA"],
            ["2025", "POST", "2026-01-18", "d", "DET", "GB", "30", "14"],
            ["2024", "REG", "2024-09-08", "e", "DET", "GB", "30", "14"],
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "games.csv"
            with path.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(fields)
                writer.writerows(rows)
            teams = season_scores(path)
        self.assertEqual([g["points"] for g in teams["DET"]], [23, 24])
        self.assertEqual([g["site"] for g in teams["DET"]], ["away", "home"])
        self.assertEqual([g["points"] for g in teams["GB"]], [13, 10])

    def test_detroit_from_local_data(self):
        result = example()
        self.assertEqual((result["k"], result["n"], result["line"]), (12, 17, 24))
        self.assertEqual((result["lo"], result["hi"]), (47, 87))
        self.assertEqual((result["last_k"], result["last_n"]), (7, 10))
        self.assertEqual(sum(result["bars"]), result["k"])
        self.assertEqual(len(season_scores()), 32)
        self.assertEqual({len(games) for games in season_scores().values()}, {17})

    def test_rate_counts_threshold_equality(self):
        self.assertEqual(rate([23, 24, 25], 24)["k"], 2)
        with self.assertRaises(ValueError):
            rate([], 24)

    def test_band_boundaries(self):
        self.assertEqual([band(k, 100) for k in (0, 39, 40, 59, 60, 69, 70, 79, 80, 100)],
                         [0, 0, 1, 1, 2, 2, 3, 3, 4, 4])

    def test_spots_have_no_leakage(self):
        original = [20, 24, 31, 10, 30, 24, 14, 40, 28, 13, 33, 29, 14, 24, 23, 30, 10]
        # Check every cutoff and every band, including changes just after a spot.
        for window in (5, 10):
            for target in range(len(BANDS)):
                for cutoff in range(window - 1, len(original)):
                    expected = [d for d in spots(original, 24, window, target) if d <= cutoff]
                    for replacement in (0, 100):
                        changed = original[:cutoff + 1] + [replacement] * (len(original) - cutoff - 1)
                        self.assertEqual([d for d in spots(changed, 24, window, target) if d <= cutoff], expected)
                    self.assertEqual(spots(original[:cutoff + 1], 24, window, target), expected)

    def test_no_overlap_partial_horizon_and_pooling(self):
        scores = [24] * 17
        self.assertEqual(spots(scores, 24, 5, 4), [4, 9, 14])
        horizons = [list(range(d + 1, min(d + 6, len(scores)))) for d in spots(scores, 24, 5, 4)]
        flat = [index for horizon in horizons for index in horizon]
        self.assertEqual(len(flat), len(set(flat)))
        self.assertEqual(flat, list(range(5, 17)))
        teams = {name: [{"points": point} for point in scores] for name in ("A", "B")}
        result = held_up(teams, 24, 5)[4]
        self.assertEqual((result["k"], result["n"], result["spots"]), (24, 24, 6))
        self.assertFalse(result["too_few"])

    def test_too_few_boundary_suppresses_score_and_range(self):
        for future in (0, 14, 15):
            teams = {"A": [{"points": 24}] * (5 + future)}
            row = held_up(teams, 24, 5)[4]
            self.assertEqual(row["n"], future)
            self.assertEqual(row["too_few"], future < 15)
            if future < 15:
                self.assertEqual((row["pct"], row["lo"], row["hi"]), (None, None, None))
            else:
                self.assertEqual(row["pct"], 100)
                self.assertEqual((row["lo"], row["hi"]), (80, 100))

    def test_future_game_changes_outcome_but_not_past_spot(self):
        scores = [24] * 10 + [0] * 5
        self.assertEqual(spots(scores, 24, 10, 4), [9])
        changed = scores[:]
        changed[10] = 30
        self.assertEqual(spots(changed, 24, 10, 4)[0], 9)
        make_teams = lambda values: {str(i): [{"points": v} for v in values] for i in range(3)}
        self.assertEqual(held_up(make_teams(scores))[4]["k"], 0)
        self.assertEqual(held_up(make_teams(changed))[4]["k"], 3)


if __name__ == "__main__":
    unittest.main()
