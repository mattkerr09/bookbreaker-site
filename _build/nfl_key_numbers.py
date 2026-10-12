"""Recompute _data/nfl_key_numbers.csv from nflverse's public games file.

    curl -sL -o games.csv https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv
    python3 _build/nfl_key_numbers.py games.csv 2026-10-12

Counts every completed regular-season and playoff game from 2015 to 2025: how often the final margin is each
number, and how often a closing spread of exactly 3 or 7 landed on the number (a push). `result` is home score
minus away score and `spread_line` is the home team's closing margin, so a push is result == spread_line.
"""
import collections
import csv
import sys

SOURCE = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"


def main(path: str, read: str) -> None:
    rows = [r for r in csv.DictReader(open(path)) if r["result"] not in ("", "NA") and 2015 <= int(r["season"]) <= 2025]
    n = len(rows)
    margin = collections.Counter(abs(int(float(r["result"]))) for r in rows)
    out = [("games", str(n)), ("first_season", "2015"), ("last_season", "2025")]
    for k in (1, 2, 3, 4, 6, 7, 10, 14):
        out.append((f"margin_{k}_pct", f"{100 * margin[k] / n:.2f}"))
    for line in (3.0, 7.0):
        hit = [r for r in rows if r["spread_line"] not in ("", "NA") and abs(float(r["spread_line"])) == line]
        push = sum(1 for r in hit if float(r["result"]) == float(r["spread_line"]))
        out += [(f"line_{int(line)}_games", str(len(hit))), (f"line_{int(line)}_pushes", str(push)),
                (f"line_{int(line)}_push_pct", f"{100 * push / len(hit):.2f}")]
    w = csv.writer(open("_data/nfl_key_numbers.csv", "w", newline=""))
    w.writerow(["key", "value", "source", "read"])
    for k, v in out:
        w.writerow([k, v, SOURCE, read])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
