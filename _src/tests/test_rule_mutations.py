"""Break each content rule in memory and verify the same real validators reject it.

The saved pages and source files are never changed by these negative checks.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
SITE = SOURCE.parent
sys.path.insert(0, str(SOURCE))

from content import CLAIMS, FACTS, e, fact
from pages import SEARCH_PAGES
from page_rules import article_issues, jaccard, registry_issues, shingles


class RuleMutationTests(unittest.TestCase):
    def test_article_rules_reject_deliberately_broken_html(self):
        config = SEARCH_PAGES[4]
        original = (SITE / config['slug'] / 'index.html').read_text()
        self.assertEqual(article_issues(original, config), [])
        variants = {
            'title': re.sub(r'<title>.*?</title>', '<title>Changed</title>', original),
            'description': original.replace(e(config['description']), 'Changed'),
            'canonical': original.replace('rel="canonical"', 'rel="other"'),
            'analytics': original.replace('data-domain="bookbreaker.bet"', 'data-domain="wrong"'),
            'schema': original.replace('"@type": "Article"', '"@type": "Wrong"'),
            'h1': original.replace('</h1>', '</h1><h1>Another heading</h1>'),
            'answer length': original.replace(e(config['answer']), 'Too short.'),
            'answer text': original.replace('Choose the number before you count.', 'Fix the number before you count.'),
            'byline': original.replace('Checked 21 November 2026 · By Matthew Kerr, who makes BookBreaker', 'No byline'),
            'main length': re.sub(r'<div class="search-body">[\s\S]*?</article>', '<div class="search-body"></div></article>', original),
            'body length': original.replace('<div class="search-body">', '<div class="search-body">' + ('extra word ' * 1200)),
            'early app': original.replace('class="ex development"', 'class="ex"'),
            'visual': re.sub(r'<table\b[\s\S]*?</table>', '', original),
            'faq': re.sub(r'<details>[\s\S]*?</details>', '', original),
            'sources': original.replace('<h2>Sources</h2>', '<h2>Notes</h2>'),
            'onward': re.sub(r'<section class="onward">[\s\S]*?</section>', '', original),
        }
        for key in ('type', 'title', 'description', 'url', 'site_name'):
            variants['og:' + key] = original.replace(f'property="og:{key}"', f'property="wrong:{key}"')
        for rule, broken in variants.items():
            with self.subTest(rule=rule):
                self.assertNotEqual(original, broken)
                self.assertIn(rule, article_issues(broken, config))
        broken_json = original.replace('"@context":', 'broken-json:')
        self.assertIn('schema', article_issues(broken_json, config))

    def test_registry_rules_reject_changed_ids_text_dates_and_missing_coming(self):
        original = (SITE / 'free-nba-player-game-logs/index.html').read_text()
        self.assertEqual(registry_issues(original, FACTS, CLAIMS), [])
        variants = {
            'unknown fact': original.replace('data-fact="nba-logs"', 'data-fact="missing"'),
            'fact text': original.replace(fact('nba-logs', code='nba.com/stats/player/<id>/boxscores-traditional'), '<p data-fact="nba-logs">Changed fact.</p>'),
            'fact source': original.replace(FACTS['nba-logs']['source'], 'Missing reference'),
            'fact date': original.replace(FACTS['nba-logs']['readAt'], '2026-01-01'),
            'unknown claim': original.replace('data-claim="desktop"', 'data-claim="missing"'),
            'claim text': original.replace(e(CLAIMS['desktop']['text']), 'BookBreaker will do something else.'),
            'coming label': original.replace('<span class="coming">Coming</span>', ''),
            'present action': original.replace('<main>', '<main><p>BookBreaker shows stats now.</p>'),
        }
        for rule, broken in variants.items():
            with self.subTest(rule=rule):
                self.assertIn(rule, registry_issues(broken, FACTS, CLAIMS))
        hidden = original.replace('class="coming"', 'class="coming" hidden')
        self.assertIn('coming label', registry_issues(hidden, FACTS, CLAIMS))
        changed_claims = dict(CLAIMS)
        changed_claims['desktop'] = dict(CLAIMS['desktop'], status='measured')
        self.assertIn('claim status', registry_issues(original, FACTS, changed_claims))

    def test_duplicate_copy_breaks_jaccard_rule(self):
        source = (SITE / 'free-nba-player-game-logs/index.html').read_text()
        self.assertGreaterEqual(jaccard(shingles(source), shingles(source)), 0.3)

    def test_statistics_tests_fail_with_deliberately_broken_algorithms(self):
        import test_stats
        source = (SOURCE / 'stats.py').read_text()
        mutations = [
            ('test_wilson_known_values_and_boundaries', 'z: float = 1.96', 'z: float = 1.0'),
            ('test_rate_counts_threshold_equality', 'score >= threshold', 'score > threshold'),
            ('test_season_reader_orders_games_and_excludes_incomplete_and_postseason', 'r["game_type"] == "REG"', 'r["game_type"] != "REG"'),
            ('test_detroit_from_local_data', 'scores[-10:]', 'scores[-5:]'),
            ('test_band_boundaries', '(40, 60, 70, 80)', '(41, 60, 70, 80)'),
            ('test_spots_have_no_leakage', 'scores[d - window + 1:d + 1]', 'scores[d - window + 2:d + 2]'),
            ('test_no_overlap_partial_horizon_and_pooling', 'next_allowed = d + HORIZON', 'next_allowed = d + HORIZON - 1'),
            ('test_too_few_boundary_suppresses_score_and_range', 'MIN_FUTURE = 15', 'MIN_FUTURE = 14'),
            ('test_future_game_changes_outcome_but_not_past_spot', 'later = scores[d + 1:d + HORIZON + 1]', 'later = scores[d:d + HORIZON]'),
        ]
        names = ['BANDS', 'band', 'example', 'held_up', 'rate', 'season_scores', 'spots', 'wilson']
        for method, before, after in mutations:
            with self.subTest(mutation=method):
                self.assertIn(before, source)
                altered = {}
                exec(compile(source.replace(before, after), str(SOURCE / 'stats.py'), 'exec'), altered)
                with patch.multiple(test_stats, **{name: altered[name] for name in names}):
                    result = unittest.TestResult()
                    test_stats.StatisticsTests(method).run(result)
                    self.assertTrue(result.failures or result.errors, 'mutation survived: ' + method)


if __name__ == '__main__':
    unittest.main()
