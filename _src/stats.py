"""Build-time arithmetic from the local nflverse schedules file. No network."""
from __future__ import annotations

import csv
import math
from pathlib import Path

NFL_FILE = Path("/Users/matthewkerr/bb-lab/research/nfl/data/games.csv")
NFL_SOURCE = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
NFL_READ = "2026-10-22"
BANDS = ("Under 40%", "40 to 59%", "60 to 69%", "70 to 79%", "80% and over")
HORIZON = 5
MIN_FUTURE = 15


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion; endpoints are fractions."""
    if n <= 0 or not 0 <= k <= n:
        raise ValueError("need 0 <= k <= n and n > 0")
    p = k / n
    divisor = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / divisor
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / divisor
    return max(0.0, centre - half), min(1.0, centre + half)


def rate(scores: list[int], threshold: int) -> dict:
    n = len(scores)
    if not n:
        raise ValueError("need games")
    k = sum(score >= threshold for score in scores)
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "pct": round(100 * k / n),
            "lo": round(100 * lo), "hi": round(100 * hi)}


def season_scores(path: Path = NFL_FILE, season: int = 2025) -> dict[str, list[dict]]:
    """Only completed regular-season games, once per team, in date/game-id order."""
    teams: dict[str, list[dict]] = {}
    with path.open(newline="") as source:
        rows = [r for r in csv.DictReader(source)
                if r["season"] == str(season) and r["game_type"] == "REG"
                and r["home_score"] not in ("", "NA") and r["away_score"] not in ("", "NA")]
    for row in sorted(rows, key=lambda r: (r["gameday"], r["game_id"])):
        for side, other in (("home", "away"), ("away", "home")):
            team = row[f"{side}_team"]
            teams.setdefault(team, []).append({"date": row["gameday"], "id": row["game_id"],
                                              "points": int(row[f"{side}_score"]), "site": side,
                                              "opponent": row[f"{other}_team"]})
    return teams


def example(path: Path = NFL_FILE) -> dict:
    games = season_scores(path)["DET"]
    scores = [game["points"] for game in games]
    threshold = 24
    whole = rate(scores, threshold)
    last = rate(scores[-10:], threshold)
    first, after = rate(scores[:8], threshold), rate(scores[8:], threshold)
    return dict(whole, team="Detroit", season=2025, line=threshold, last_k=last["k"], last_n=last["n"],
                last_lo=last["lo"], last_hi=last["hi"], last_pct=last["pct"],
                first_k=first["k"], first_n=first["n"], first_pct=first["pct"],
                after_k=after["k"], after_n=after["n"], after_pct=after["pct"],
                bars=[score >= threshold for score in scores], games=games)


def band(k: int, n: int) -> int:
    if n <= 0 or not 0 <= k <= n:
        raise ValueError("invalid count")
    # Compare integers so exact band boundaries never depend on float rounding.
    for index, upper in enumerate((40, 60, 70, 80)):
        if 100 * k < upper * n:
            return index
    return 4


def spots(scores: list[int], threshold: int, window: int, target_band: int) -> list[int]:
    """Select a band's spots using only the prefix ending at each spot.

    Selection runs independently for each target band, as a card would for its
    current band. A spot remains a spot even if it has no later games yet.
    """
    if window <= 0 or target_band not in range(len(BANDS)):
        raise ValueError("invalid window or band")
    selected = []
    next_allowed = window - 1
    for d in range(window - 1, len(scores)):
        if d < next_allowed:
            continue
        k = sum(value >= threshold for value in scores[d - window + 1:d + 1])
        if band(k, window) == target_band:
            selected.append(d)
            next_allowed = d + HORIZON
    return selected


def held_up(teams: dict[str, list[dict]], threshold: int = 24, window: int = 10) -> list[dict]:
    """Pool each band's future games across subjects, keeping partial horizons."""
    results = []
    for target, label in enumerate(BANDS):
        k, n, with_future = 0, 0, 0
        for games in teams.values():
            scores = [game["points"] for game in games]
            for d in spots(scores, threshold, window, target):
                later = scores[d + 1:d + HORIZON + 1]
                with_future += bool(later)
                k += sum(score >= threshold for score in later)
                n += len(later)
        too_few = n < MIN_FUTURE
        interval = wilson(k, n) if not too_few else None
        results.append({"band": label, "k": k, "n": n, "spots": with_future,
                        "too_few": too_few, "pct": None if too_few else round(100 * k / n),
                        "lo": None if too_few else round(100 * interval[0]),
                        "hi": None if too_few else round(100 * interval[1])})
    return results
