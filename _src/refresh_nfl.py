"""Tuesday refresh of the 2026 NFL sections: download, verify, point the build at the new read, rebuild, gate.

Usage: python3 _src/refresh_nfl.py            (download into a fresh dated folder, then build and gate)
It never commits or pushes. It prints VERDICT GREEN or VERDICT RED as its last line and exits 0 only on GREEN;
the caller commits by exact path only after reading that line (memory: gate before commit).
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
SITE = SOURCE.parent
CONFIG = SOURCE / 'data' / 'nfl_2026.json'
DATA_ROOT = Path('/Users/matthewkerr/bb-lab/research/nfl/data')
DOWNLOADS_LOG = Path('/Users/matthewkerr/ops/launch/ORG/DOWNLOADS-LOG.md')
FILES = {
    'stats_player_week_2026.csv': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.csv',
    'games.csv': 'https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv',
}
NEEDED = {'stats_player_week_2026.csv': ('player_id', 'season', 'week', 'season_type', 'game_id', 'team', 'opponent_team',
                                         'passing_yards', 'rushing_yards', 'receiving_yards'),
          'games.csv': ('game_id', 'season', 'game_type', 'week', 'gameday', 'home_team', 'away_team', 'home_score',
                        'away_score')}


def counts(folder: Path) -> tuple[int, int]:
    with (folder / 'stats_player_week_2026.csv').open(newline='') as handle:
        rows = sum(r['season'] == '2026' and r['season_type'] == 'REG' for r in csv.DictReader(handle))
    with (folder / 'games.csv').open(newline='') as handle:
        games = sum(g['season'] == '2026' and g['game_type'] == 'REG' and g['home_score'] not in ('', 'NA')
                    for g in csv.DictReader(handle))
    return rows, games


def fail(message: str) -> None:
    print(message)
    print('VERDICT RED')
    sys.exit(1)


def main() -> None:
    now = time.gmtime()
    stamp, read = time.strftime('%Y-%m-%dT%H:%M:%SZ', now), time.strftime('%Y-%m-%d', now)
    old = json.loads(CONFIG.read_text())
    folder = DATA_ROOT / f'nflverse-{read}'
    if folder.exists():
        fail(f'{folder} already exists; a read is never overwritten')
    folder.mkdir()
    manifest = []
    for name, url in FILES.items():
        with urllib.request.urlopen(url, timeout=120) as response:
            body = response.read()
        (folder / name).write_bytes(body)
        manifest.append((name, url, len(body), hashlib.sha256(body).hexdigest()))
        with (folder / name).open(newline='') as handle:
            header = next(csv.reader(handle))
        missing = [key for key in NEEDED[name] if key not in header]
        if missing:
            fail(f'{name} lacks {missing}')
    (folder / 'MANIFEST.tsv').write_text('file\turl\tbytes\tsha256\tread\n' + ''.join(
        f'{n}\t{u}\t{b}\t{h}\t{stamp}\n' for n, u, b, h in manifest) + 'licence\tCC BY 4.0 (nflverse-data)\t\t\t\n')
    before, after = counts(Path(old['dir'])), counts(folder)
    print(f'2026 player rows {before[0]} -> {after[0]}; completed 2026 games {before[1]} -> {after[1]}')
    if after[0] < before[0] or after[1] < before[1]:
        fail('the new read holds fewer 2026 rows or games than the last one')
    with DOWNLOADS_LOG.open('a') as log:
        log.write(f'\n- {stamp}, BookBreaker (Tuesday NFL refresh, refresh_nfl.py), RULES 70: '
                  + ', '.join(f'{n} {b:,} bytes' for n, _, b, _ in manifest)
                  + f' from nflverse-data GitHub releases (CC BY 4.0). Saved to {folder}/ with MANIFEST.tsv.\n')
    CONFIG.write_text(json.dumps({'dir': str(folder), 'read': read}) + '\n')
    for step in ([sys.executable, str(SOURCE / 'build.py')], [sys.executable, str(SOURCE / 'check.py')],
                 [sys.executable, '-m', 'unittest', 'discover', '-s', str(SOURCE / 'tests')]):
        result = subprocess.run(['nice', '-n', '19', *step], cwd=SITE, text=True, capture_output=True)
        print((result.stdout + result.stderr).strip().splitlines()[-1] if (result.stdout + result.stderr).strip() else '')
        if result.returncode:
            print((result.stdout + result.stderr)[-3000:])
            fail(f'step failed: {" ".join(step[1:])}; config left at the new read for inspection')
    print('VERDICT GREEN')


if __name__ == '__main__':
    main()
