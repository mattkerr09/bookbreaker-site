"""The current 2026 NFL read, named in data/nfl_2026.json. refresh_nfl.py rewrites that file each Tuesday."""
from __future__ import annotations

import json
from pathlib import Path

_CONFIG = json.loads((Path(__file__).resolve().parent / 'data' / 'nfl_2026.json').read_text())
NFL_2026_DIR = Path(_CONFIG['dir'])
NFL_2026_READ = _CONFIG['read']
MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December')


def long_date(iso: str) -> str:
    return f'{int(iso[8:10])} {MONTHS[int(iso[5:7]) - 1]} {iso[:4]}'
