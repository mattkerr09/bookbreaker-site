"""Allowlisted weekly player data and the eligible 2025 page inventory. Offline."""
from __future__ import annotations

import csv
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from nfl_2026 import NFL_2026_DIR, NFL_2026_READ, long_date

PLAYER_DATA = Path('/Users/matthewkerr/bb-lab/research/nfl/data/nflverse-player-week')
PLAYER_READ = '2026-11-21'
PLAYER_SOURCES = tuple('https://github.com/nflverse/nflverse-data/releases/download/'
                       f'stats_player/stats_player_week_{year}.csv' for year in (2024, 2025))
PLAYER_2026_DATA = NFL_2026_DIR
PLAYER_2026_READ = NFL_2026_READ
PLAYER_2026_CHECKED = long_date(NFL_2026_READ)
PLAYER_2026_SOURCE = ('https://github.com/nflverse/nflverse-data/releases/download/'
                      'stats_player/stats_player_week_2026.csv')
MAIN_STAT = {'QB': 'passing_yards', 'RB': 'rushing_yards',
             'WR': 'receiving_yards', 'TE': 'receiving_yards'}
PLAYER_PAGE_FIELDS = (
    'player_id', 'player_display_name', 'position', 'season', 'week', 'season_type',
    'game_id', 'team', 'opponent_team', 'completions', 'attempts', 'passing_yards',
    'passing_tds', 'passing_interceptions', 'carries', 'rushing_yards', 'rushing_tds',
    'receptions', 'targets', 'receiving_yards', 'receiving_tds',
)


def read_player_rows(directory: Path = PLAYER_DATA, fields: tuple = PLAYER_PAGE_FIELDS) -> list[dict]:
    """The single player CSV boundary. Never access a cell outside the allowlist.

    The pooled study requests its smaller eight-field subset. Raw CSV records
    never become dictionaries; only approved cells are selected by column index.
    """
    if not set(fields) <= set(PLAYER_PAGE_FIELDS):
        raise ValueError('unapproved player fields')
    rows = []
    for season in (2024, 2025):
        with (directory / f'stats_player_week_{season}.csv').open(newline='') as handle:
            reader = csv.reader(handle)
            header = next(reader)
            positions = [(key, header.index(key)) for key in fields]
            for cells in reader:
                row = {key: cells[index] for key, index in positions}
                if row['season'] == str(season) and row['season_type'] == 'REG' and row['position'] in MAIN_STAT:
                    rows.append(row)
    return rows


def read_2026_rows(directory: Path = PLAYER_2026_DATA, fields: tuple = PLAYER_PAGE_FIELDS) -> list[dict]:
    """2026 regular-season rows for the separate so-far sections, through the same allowlist.

    They never enter the 2025 mark, the 2025 counts or the 2024-25 later check.
    """
    if not set(fields) <= set(PLAYER_PAGE_FIELDS):
        raise ValueError('unapproved player fields')
    with (directory / 'stats_player_week_2026.csv').open(newline='') as handle:
        reader = csv.reader(handle)
        header = next(reader)
        positions = [(key, header.index(key)) for key in fields]
        rows = ({key: cells[index] for key, index in positions} for cells in reader)
        return [row for row in rows if row['season'] == '2026' and row['season_type'] == 'REG']


def with_2026(players: list[dict], rows: list[dict] | None = None) -> list[dict]:
    """Retitle the pages of players with a recorded 2026 game. The 2025 catalog is unchanged."""
    played = {row['player_id'] for row in (read_2026_rows() if rows is None else rows)}
    for p in players:
        p['checked'], p['modified'] = PLAYER_2026_CHECKED, PLAYER_2026_READ
        if p['player_id'] in played:
            label = p['stat'].replace('_', ' ')
            p['title'] = f"{p['name']} {label} by game, 2025 and 2026"
            p['description'] = (f"{p['name']} {label} in every 2025 regular-season game and 2026 so far. "
                                'Last 5 and last 10 counts, Wilson ranges, splits and later games.')
    return players


def name_slug(name: str) -> str:
    plain = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', plain).strip('-')


def player_catalog(rows: list[dict] | None = None) -> list[dict]:
    logs = defaultdict(list)
    for row in read_player_rows() if rows is None else rows:
        if row['season'] == '2025' and row['season_type'] == 'REG' and row['position'] in MAIN_STAT:
            logs[row['player_id']].append(row)
    players = []
    for identity, log in logs.items():
        last = max(log, key=lambda r: int(r['week']))
        stat = MAIN_STAT[last['position']]
        mid = median(float(r[stat] or 0) for r in log)
        if len(log) < 8 or mid < 10:
            continue
        name = last['player_display_name']
        players.append(dict(player_id=identity, name=name, position=last['position'], team=last['team'],
                            teams=sorted({r['team'] for r in log}), stat=stat, median=mid,
                            games=len(log), short_slug=name_slug(name)))
    duplicates = Counter(p['short_slug'] for p in players)
    for p in players:
        if duplicates[p['short_slug']] > 1:
            p['short_slug'] += '-' + p['position'].lower()
    duplicates = Counter(p['short_slug'] for p in players)
    for p in players:
        if duplicates[p['short_slug']] > 1:
            p['short_slug'] += '-' + p['team'].lower()
        p['slug'] = 'nfl-player-stats/' + p['short_slug']
        label = p['stat'].replace('_', ' ')
        p['title'] = f"{p['name']} {label} by game, 2025 season"
        p['description'] = (f"{p['name']} {label} in the last 10 games and every 2025 regular-season game. "
                            'Last 5 and season counts, Wilson ranges, splits and a later-games check.')
    if len({p['slug'] for p in players}) != len(players):
        raise ValueError('player slug collision after position and team')
    return sorted(players, key=lambda p: (p['name'], p['player_id']))


def thresholds(mid: float) -> tuple[int, int, int]:
    base = math.ceil(mid)
    # Halfway values round upward, rather than Python's even-number rounding.
    return tuple(5 * math.floor(base * factor / 5 + .5) for factor in (.75, 1, 1.25))
