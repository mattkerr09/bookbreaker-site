"""Offline player study: 2024 thresholds, 2025 spots and later games.

Only the eight approved CSV fields cross the read boundary. Names are never
read. The six-game step matches the saved research run, independently of the
team study's five-game step.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from statistics import median

from stats import BANDS, band, wilson

from player_data import MAIN_STAT, PLAYER_DATA, PLAYER_READ, PLAYER_SOURCES, read_player_rows

PLAYER_FIELDS = ('player_id', 'position', 'season', 'week', 'season_type',
                 'passing_yards', 'rushing_yards', 'receiving_yards')


def player_rows(directory: Path = PLAYER_DATA) -> list[dict]:
    return read_player_rows(directory, PLAYER_FIELDS)


def player_logs(rows: list[dict]) -> dict[tuple[str, str], list[dict]]:
    logs: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        if row['season_type'] != 'REG' or row['position'] not in MAIN_STAT or int(row['season']) not in (2024, 2025):
            continue
        key = (row['player_id'], row['position'])
        logs.setdefault(key, []).append({'season': int(row['season']), 'week': int(row['week']),
                                         'yards': float(row[MAIN_STAT[row['position']]] or 0)})
    return {key: sorted(log, key=lambda r: (r['season'], r['week'])) for key, log in logs.items()}


def player_threshold(log: list[dict]) -> int | None:
    prior = [r['yards'] for r in log if r['season'] == 2024]
    if len(prior) < 8:
        return None
    threshold = math.ceil(median(prior))
    return threshold if threshold >= 10 else None


def player_spots(log: list[dict], threshold: int, window: int) -> list[dict]:
    """Each spot uses its prefix only; partial 2025 outcomes are retained."""
    if window not in (5, 10):
        raise ValueError('study windows are 5 and 10')
    next_allowed = [0] * len(BANDS)
    selected = []
    for i in range(window - 1, len(log)):
        if log[i]['season'] != 2025:
            continue
        hits = sum(r['yards'] >= threshold for r in log[i - window + 1:i + 1])
        target = band(hits, window)
        if i < next_allowed[target]:
            continue
        future = [j for j in range(i + 1, min(i + 6, len(log))) if log[j]['season'] == 2025]
        if not future:
            continue
        selected.append({'index': i, 'band': target, 'shown': hits / window, 'future': future,
                         'k': sum(log[j]['yards'] >= threshold for j in future), 'n': len(future)})
        next_allowed[target] = i + 6
    return selected


def study(rows: list[dict] | None = None) -> dict[int, dict]:
    logs = player_logs(player_rows() if rows is None else rows)
    eligible = [(log, player_threshold(log)) for log in logs.values()]
    eligible = [(log, threshold) for log, threshold in eligible if threshold is not None]
    results = {}
    for window in (5, 10):
        bands = [dict(band=label.lower(), k=0, n=0, shown_sum=0.0, spots=0) for label in BANDS]
        for log, threshold in eligible:
            for spot in player_spots(log, threshold, window):
                row = bands[spot['band']]
                for key in ('k', 'n'):
                    row[key] += spot[key]
                row['shown_sum'] += spot['shown']
                row['spots'] += 1
        for row in bands:
            row['shown'] = row['shown_sum'] / row['spots'] if row['spots'] else None
            row['later'] = row['k'] / row['n'] if row['n'] else None
            row['range'] = wilson(row['k'], row['n']) if row['n'] else None
        results[window] = {'players': len(eligible), 'bands': bands}
    return results


def report_text(results: dict[int, dict]) -> str:
    """Reproduce the supplied output.txt, including its rounding and spacing."""
    lines = []
    for window, result in results.items():
        lines.append(f"window last {window}, players {result['players']} "
                     '(threshold = own 2024 median, rounded up; next 5 games of 2025)')
        for row in result['bands']:
            label = row['band']
            if not row['spots']:
                lines.append(f'  {label:14s} no spots (not reachable with this window)')
                continue
            lo, hi = row['range']
            lines.append(f"  {label:14s} spots {row['spots']:4d}  shown avg {row['shown']:5.0%}  "
                         f"later {row['k']:4d}/{row['n']:<4d} {row['later']:5.0%}  ({lo:.0%} to {hi:.0%})")
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    print(report_text(study()), end='')
