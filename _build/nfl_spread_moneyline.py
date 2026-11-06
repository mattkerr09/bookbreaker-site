"""Recompute _data/nfl_spread_moneyline.csv, and the table calc.py carries, from nflverse's public games file.

    curl -sL -o games.csv https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv
    PYTHONPATH=<app repo>/backend python3 _build/nfl_spread_moneyline.py games.csv 2026-11-06

For every completed regular-season and playoff game from 2015 to 2025 with a closing spread and both closing
moneylines: the favourite's closing spread, the favourite's chance in its own closing moneyline market with the
margin removed (the engine's four-method average), and whether the favourite won outright. One row per closing
spread with at least MIN_GAMES games. `spread_line` is the home team's closing margin (positive: home favoured) and
`result` is home score minus away score, so the favourite won outright when result has the spread's sign.

The browser runs calc.py alone, so the table is written into calc.py too, between the BEGIN and END markers.
render.py refuses to build if the two differ.
"""
import collections
import csv
import re
import sys
from pathlib import Path

from overlay_engine.devig import devig_all
from overlay_engine.odds import american_to_decimal

SOURCE = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
MIN_GAMES = 40
HERE = Path(__file__).resolve().parent
BEGIN = "# BEGIN NFL_SPREAD (written by _build/nfl_spread_moneyline.py; do not edit by hand)"
END = "# END NFL_SPREAD"


def main(path: str, read: str) -> None:
    rows = [r for r in csv.DictReader(open(path))
            if r["result"] not in ("", "NA") and r["spread_line"] not in ("", "NA")
            and r["home_moneyline"] not in ("", "NA") and r["away_moneyline"] not in ("", "NA")
            and 2015 <= int(r["season"]) <= 2025 and float(r["spread_line"]) != 0]
    cells = collections.defaultdict(lambda: {"games": 0, "won": 0, "tied": 0, "fair": 0.0})
    for r in rows:
        line = float(r["spread_line"])
        home_fav = line > 0
        home, away = american_to_decimal(float(r["home_moneyline"])), american_to_decimal(float(r["away_moneyline"]))
        fav, dog = (home, away) if home_fav else (away, home)
        margin = float(r["result"]) if home_fav else -float(r["result"])
        c = cells[abs(line)]
        c["games"] += 1
        c["won"] += margin > 0
        c["tied"] += margin == 0
        c["fair"] += devig_all([fav, dog]).consensus(0)
    table = []
    for spread in sorted(cells):
        c = cells[spread]
        if c["games"] < MIN_GAMES:
            continue
        table.append((spread, c["games"], c["won"], c["tied"], round(c["fair"] / c["games"], 4)))
    with open(HERE.parent / "_data" / "nfl_spread_moneyline.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["spread", "games", "won", "tied", "fair", "source", "read"])
        for spread, games, won, tied, fair in table:
            w.writerow([f"{spread:g}", games, won, tied, f"{fair:.4f}", SOURCE, read])
    calc = HERE / "calc.py"
    body = "\n".join([BEGIN, f"NFL_SPREAD_READ = {read!r}", f"NFL_SPREAD_GAMES = {len(rows)}", "NFL_SPREAD = {"]
                     + [f"    {spread:g}: ({games}, {won}, {tied}, {fair:.4f}),"
                        for spread, games, won, tied, fair in table] + ["}", END])
    text = calc.read_text()
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        raise SystemExit(f"calc.py has no {BEGIN!r} block to rewrite")
    calc.write_text(pattern.sub(lambda _: body, text, count=1))
    print(f"{len(rows)} games, {len(table)} spreads with at least {MIN_GAMES} games")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
