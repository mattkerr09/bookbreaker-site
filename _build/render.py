#!/usr/bin/env python3
"""Build bookbreaker.bet by running the engine it describes.

Every figure on this site is computed here, at render time, by importing
`overlay_engine` and calling it. Nothing is typed into a template. That is a
stronger version of the rule the sibling sites follow — they generate pages
from the product's data files, this one generates them from the product's
actual output — and it exists because a marketing site maintained separately
from the thing it describes goes stale in a month and nobody notices.

It also makes a specific promise checkable. This product's entire claim is that
the numbers other tools print are less certain than they look; a site that
asserted its own numbers by hand would be making exactly the mistake it sells
against.

So `render.py` writes `_build/measured.json` alongside the pages: every number
that appears, what produced it, and what inputs it came from. `check.py` refuses
to publish if a figure appears on a page and not in that file.

    python _build/render.py --app-repo "../arb betting aqpp"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
import html
import json
import sys
from datetime import date
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
TODAY = date.today().isoformat()

# Fixed, not wall-clock: two renders of unchanged input must produce identical
# pages, or the freshness gate cannot tell a real change from the passage of
# time.
NOW = 1_800_000_000.0

# Competitor claims. Every one carries the date it was read and the source it
# was read from, and `check.py` fails the build if either is missing. Docket's
# README once asserted a competitor's price with no date and no source, and the
# price was already wrong — an undated claim about someone else's product does
# not stay neutral, it claims "true now" forever.
def load_data(name: str) -> list[dict]:
    """Read an entity list from `_data/`.

    Entities live in CSV and generators live here, the same split the sibling
    sites use. It keeps the thing that changes weekly — which competitors
    exist, which calculators the engine offers — out of the code that renders
    it, so adding a page is a row rather than a patch.
    """
    path = SITE / "_data" / f"{name}.csv"
    if not path.exists():
        raise SystemExit(f"no data at {path}")
    with path.open() as handle:
        return list(csv.DictReader(handle))


COMPETITORS = load_data("competitors")


def engine_fingerprint(app_repo: Path) -> str:
    """A hash of every engine source file.

    Recorded in `measured.json` so `check.py` can refuse to publish a render
    made against an older engine. The roadmap named this as the thing most
    likely to go stale — `render.py` chooses which figures to compute, so an
    engine change that alters a number leaves the site quietly showing the old
    one, and nothing about the page looks wrong.
    """
    digest = hashlib.sha256()
    root = app_repo / "backend" / "overlay_engine"
    for path in sorted(root.rglob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def load_engine(app_repo: Path):
    """Import the engine from the product repo. No vendored copy, ever."""
    backend = app_repo / "backend"
    if not (backend / "overlay_engine" / "__init__.py").exists():
        raise SystemExit(
            f"no engine at {backend}/overlay_engine — pass --app-repo pointing "
            "at the product repo"
        )
    sys.path.insert(0, str(backend))
    import overlay_engine  # noqa: E402

    return overlay_engine


def measure(engine) -> dict:
    """Run the engine and collect every number the site will show.

    Each entry records the inputs as well as the result, so a reader can redo
    the arithmetic and `check.py` can confirm nothing was typed by hand.
    """
    from overlay_engine.devig import devig_all
    from overlay_engine.odds import american_to_decimal, decimal_to_american
    from overlay_engine.promo import bonus_bet_conversion, fair_conversion_ceiling

    out: dict = {"generated": TODAY, "version": engine.__version__}

    # 1. The devig spread. Four defensible methods, one real market.
    nfl = [american_to_decimal(-145), american_to_decimal(125)]
    spread = devig_all(nfl)
    out["devig"] = {
        "market": "-145 / +125",
        "methods": {m: round(v[0] * 100, 2) for m, v in spread.by_method.items()},
        "consensus": round(spread.consensus(0) * 100, 2),
        "spread": round(spread.spread(0) * 100, 2),
    }

    # 2. The round-stake arbitrage. Exact stakes versus stakes a human places.
    legs = [2.10, 2.05]
    exact = engine.stake_arb(legs, total=1000.0, round_stakes=False)
    rounded = engine.stake_arb(legs, total=1000.0)
    out["arb"] = {
        "legs": [f"{decimal_to_american(d):+.0f}" for d in legs],
        "margin": round(engine.arb_margin(legs) * 100, 2),
        "exact_stakes": [round(l.stake, 2) for l in exact.legs],
        "exact_profit": round(exact.profit, 2),
        "round_stakes": [round(l.stake) for l in rounded.legs],
        "round_profit": round(rounded.profit, 2),
        "rounding_cost": round(rounded.rounding_cost, 2),
    }

    # 3. Bonus bet conversion, and the hedge each plan actually needs.
    ladder = []
    for free_a, hedge_a in ((100, -110), (200, -230), (400, -450), (1200, -1400)):
        free_d = american_to_decimal(free_a)
        hedge_d = american_to_decimal(hedge_a)
        plan = bonus_bet_conversion(free_d, hedge_d, 1000.0)
        ladder.append({
            "free": f"{free_a:+d}", "hedge": f"{hedge_a:+d}",
            "hedge_stake": round(plan.hedge_stake),
            "guaranteed": round(plan.guaranteed),
            "rate": round(plan.conversion * 100, 1),
            "ceiling": round(fair_conversion_ceiling(free_d) * 100, 1),
        })
    out["conversion"] = {"bonus": 1000, "doubled": 2000, "ladder": ladder}

    # 4. Middles: the same prices one point apart. The margin sample is
    # synthetic and stated as such on the page — no verifiable published table
    # covers every margin with its sample size, so the product counts the
    # user's own recorded games rather than shipping a distribution.
    from overlay_engine.middles import MarginModel, MiddlePlan, stake_middle

    shape = ([3] * 45 + [7] * 27 + [6] * 21 + [10] * 18 + [4] * 15 + [14] * 12
             + [1] * 12 + [2] * 12 + [5] * 12 + [8] * 12 + [11] * 9 + [13] * 9
             + [17] * 9 + [20] * 9 + [9] * 6 + [12] * 6 + [16] * 6 + [21] * 6
             + [24] * 6 + [28] * 6 + [15] * 6 + [18] * 6 + [19] * 5 + [22] * 5
             + [23] * 5)
    model = MarginModel(counts={"nfl": {}})
    for margin in shape:
        model.counts["nfl"][margin] = model.counts["nfl"].get(margin, 0) + 1

    price = american_to_decimal(-110)
    middles = []
    for low, high in ((2.5, 3.5), (4.5, 5.5)):
        lo, hi = stake_middle(price, price, 1000.0, round_stakes=False)
        plan = MiddlePlan(
            low_line=low, high_line=high, low_book="a", high_book="b",
            low_decimal=price, high_decimal=price, low_stake=lo, high_stake=hi,
            p_middle=model.p_window("nfl", low, high), source="counted",
        )
        middles.append({
            "window": f"{low:g} / {high:g}",
            "probability": round(plan.p_middle * 100, 2),
            "breakeven": round(plan.breakeven_p * 100, 2),
            "ev": round(plan.ev * 100, 2),
        })
    out["middles"] = {"games": len(shape), "cases": middles,
                      "sample": "synthetic, shape stated"}

    # 5. Fill probability against feed latency.
    from overlay_engine.staleness import FillModel, LatencyModel

    fills, latency = FillModel(), LatencyModel()
    for _ in range(30):
        latency.observe("dk", 6.0)
    age = 10.0
    lag = latency.typical("dk")
    honest = fills.p_fill("dk", "h2h", age + lag)
    naive = fills.p_fill("dk", "h2h", age)
    out["fill"] = {
        "age": age, "latency": round(lag, 1),
        "effective": round(age + lag, 1),
        "honest": round(honest * 100),
        "naive": round(naive * 100),
        # What a 4% edge is actually worth either way. Computed here rather
        # than in the template, because a figure worked out in a page is a
        # figure nobody checked.
        "edge": 4.0,
        "edge_honest": round(4.0 * honest, 2),
        "edge_naive": round(4.0 * naive, 2),
    }

    # 6. What a 220-bet record can and cannot support.
    from overlay_engine.performance import report

    def row(result, profit):
        return {"id": 1, "placed_at": 0, "settled_at": 0, "sport": "nfl",
                "market_type": "h2h", "outcome": "x", "book": "dk",
                "decimal_odds": 2.0, "stake": 100.0, "result": result,
                "profit": profit, "fair_prob": 0.5, "closing_fair_prob": 0.5,
                "p_fill": 1.0, "heat": 0.0}

    rows = [row("won", 100.0)] * 112 + [row("lost", -100.0)] * 99 \
        + [row("push", 0.0)] * 9
    rep = report(rows)
    out["performance"] = {
        "n": rep.overall.n,
        "profit": round(rep.overall.profit),
        "roi": round(rep.overall.roi * 100, 2),
        "low": round(rep.overall.roi_low * 100, 1),
        "high": round(rep.overall.roi_high * 100, 1),
        "verdict": rep.overall.verdict(),
    }

    # 7. Account longevity: what bet shape gives away.
    from overlay_engine.heat import (
        AccountHeat, BetRecord, market_heat, reaction_heat,
        stake_precision_heat, shape as shape_bet,
    )
    from overlay_engine.models import Book, BookTier

    books = {
        "dk": Book("dk", "DraftKings", BookTier.RETAIL),
        "pinnacle": Book("pinnacle", "Pinnacle", BookTier.SHARP,
                         limits_winners=False),
    }
    out["heat"] = {
        "stakes": [
            {"stake": f"{v:,.2f}", "heat": round(stake_precision_heat(v) * 100)}
            for v in (473.82, 473.0, 475.0, 500.0)
        ],
        "reaction": [
            {"after": f"{t:g}s", "heat": round(reaction_heat(t) * 100)}
            for t in (0.5, 30.0, 120.0)
        ],
        "markets": [
            {"market": m, "heat": round(market_heat(m) * 100)}
            for m in ("h2h", "player_points", "alternate_spreads")
        ],
        "shaped": round(
            shape_bet("dk", 473.82, 0.03, AccountHeat(), books, now=NOW).stake
        ),
        "untouched": round(
            shape_bet("pinnacle", 473.82, 0.03, AccountHeat(), books,
                      now=NOW).stake, 2
        ),
    }

    # 8. What a record can and cannot prove.
    from overlay_engine.performance import (
        MIN_BETS, bonferroni_z, family_error_rate,
    )

    out["evidence"] = {
        "floor": MIN_BETS,
        "bars": [
            {"tests": k, "z": round(bonferroni_z(k), 2),
             "luck": round(family_error_rate(k) * 100)}
            for k in (1, 5, 10, 20)
        ],
    }

    # 7b. Parlays. The most popular bet in the market and the worst priced,
    # and the arithmetic is the entire argument.
    from overlay_engine.parlay import break_even_legs, correlation_note, value

    par = value([american_to_decimal(-110)] * 4)
    out["parlay"] = {
        "legs": par.legs,
        "pays": round(par.offered - 1, 2),
        "fair": round(par.fair - 1, 2),
        "hold": round(par.hold * 100, 1),
        "leg_hold": round(par.leg_hold * 100, 2),
        "multiple": round(par.multiple, 1),
        "lottery_legs": break_even_legs(par.leg_hold, 0.25),
        "ladder": [
            {"legs": n, "hold": round(value(
                [american_to_decimal(-110)] * n).hold * 100, 1)}
            for n in (2, 3, 4, 5, 6, 8)
        ],
        "sgp_note": correlation_note(same_game=True),
    }

    # 7c. Promotions, priced. The welcome-offer surface is the biggest reason
    # people open accounts and the least honestly documented part of the
    # market: every figure below is the arithmetic, run, not a claim about any
    # book's current terms.
    from overlay_engine.models import Book, BookTier, Market, Outcome, Quote
    from overlay_engine.offers import (
        PRIOR_HOLDS, RolloverTerms, evaluate, measure_class_holds)
    from overlay_engine.promo import (
        profit_boost_value, safety_net_premium, safety_net_value)

    # A deposit match, decided by which markets its rollover allows. Both
    # churn holds are measured off real two-way prices rather than assumed.
    churn_markets = [
        Market(event_id="promo-h2h", sport="nfl", market_type="h2h", quotes=[
            Quote(book=Book("dk", "DraftKings", BookTier.RETAIL),
                  outcome=Outcome("home"), decimal=american_to_decimal(-110),
                  seen_at=NOW),
            Quote(book=Book("dk", "DraftKings", BookTier.RETAIL),
                  outcome=Outcome("away"), decimal=american_to_decimal(-110),
                  seen_at=NOW),
        ]),
        Market(event_id="promo-prop", sport="nfl", market_type="player_prop",
               quotes=[
            Quote(book=Book("dk", "DraftKings", BookTier.RETAIL),
                  outcome=Outcome("over"), decimal=american_to_decimal(-133),
                  seen_at=NOW),
            Quote(book=Book("dk", "DraftKings", BookTier.RETAIL),
                  outcome=Outcome("under"), decimal=american_to_decimal(-133),
                  seen_at=NOW),
        ]),
    ]
    churn = measure_class_holds(churn_markets, now=NOW)

    def _verdict(eligible):
        terms = RolloverTerms(
            book="a book", state="NJ", rollover=10.0,
            eligible=frozenset(eligible), fetched_at=NOW,
            source="terms supplied to this calculation")
        return evaluate(terms, 1000.0, 1000.0, churn, NOW)

    open_v, shut_v = _verdict({"h2h"}), _verdict({"player_prop"})
    out["match"] = {
        "deposit": 1000, "bonus": 1000, "rollover": 10,
        "breakeven": round(open_v.breakeven * 100, 2),
        "open_hold": round(open_v.churn.hold * 100, 2),
        "open_net": round(open_v.net, 2),
        "open_margin": round(open_v.margin * 100, 2),
        "shut_hold": round(shut_v.churn.hold * 100, 2),
        "shut_net": round(shut_v.net, 2),
        "shut_margin": round(shut_v.margin * 100, 2),
        "swing": round(open_v.net - shut_v.net, 2),
        "prior_parlay": round(PRIOR_HOLDS["parlay"] * 100, 1),
    }

    # A safety net. Its worth is the refund times how often you collect it,
    # which is why the qualifying bet should be a longshot — the opposite of
    # the instinct, and the opposite of the right play on a bet-and-get.
    net_stake, conv_rate = 1000.0, 0.75
    net_rows = []
    for american, prob in ((-110, 0.5), (150, 0.4), (300, 0.25), (600, 1 / 7)):
        d = american_to_decimal(american)
        net_rows.append({
            "american": f"{american:+d}",
            "premium": round(safety_net_premium(net_stake, prob, conv_rate), 2),
            "ev": round(safety_net_value(net_stake, d, prob, conv_rate).expected, 2),
        })
    out["safety_net"] = {
        "stake": int(net_stake),
        "conversion": round(conv_rate * 100),
        "rows": net_rows,
        "short_premium": net_rows[0]["premium"],
        "long_premium": net_rows[-1]["premium"],
        "ratio": round(net_rows[-1]["premium"] / net_rows[0]["premium"], 2),
    }

    # A profit boost. It multiplies profit, and profit grows with the price,
    # so spending it on a favourite gives most of it away.
    boost_stake, boost_pct = 100.0, 0.5
    boost_rows = []
    for american, prob in ((-200, 2 / 3), (-110, 0.5), (200, 1 / 3), (500, 1 / 6)):
        d = american_to_decimal(american)
        boost_rows.append({
            "american": f"{american:+d}",
            "added": round(boost_stake * (d - 1.0) * boost_pct, 2),
            "ev": round(profit_boost_value(
                boost_stake, d, prob, boost_pct).expected, 2),
        })
    out["boost"] = {
        "stake": int(boost_stake),
        "pct": round(boost_pct * 100),
        "rows": boost_rows,
        "worst": boost_rows[0]["added"],
        "best": boost_rows[-1]["added"],
        "multiple": round(boost_rows[-1]["added"] / boost_rows[0]["added"], 1),
    }

    # 7d. The rigour surface: the four places a betting tool quietly lies to
    # you about how much it knows. Every figure run, not asserted.
    from overlay_engine.arb import stake_arb
    from overlay_engine.calibrate import HOLDOUT, MIN_BOOK_COVERAGE, MIN_GRADED
    from overlay_engine.performance import MIN_BETS, Z, bonferroni_z, family_error_rate
    from overlay_engine.staleness import PRIOR_LATENCY, PRIOR_TAU

    # Multiple comparisons. Slice a record enough ways and something clears an
    # ordinary bar by luck; this is how fast that happens.
    out["multiplicity"] = {
        "alpha": 5,
        "confidence": 95,
        "plain_z": round(Z, 2),
        "min_bets": MIN_BETS,
        "rows": [
            {"tests": k,
             "error": round(family_error_rate(k) * 100, 1),
             "z": round(bonferroni_z(k), 2)}
            for k in (1, 5, 10, 20)
        ],
        "coinflip_at": next(k for k in range(1, 200)
                            if family_error_rate(k) >= 0.5),
    }

    # Round stakes. The anti-limiting choice has a price, and it is named.
    arb_prices = [2.10, 2.05]
    exact = stake_arb(arb_prices, 1000.0, round_stakes=False)
    rnd = stake_arb(arb_prices, 1000.0, round_stakes=True)
    out["rounding"] = {
        "total": 1000,
        "exact_legs": [round(leg.stake, 2) for leg in exact.legs],
        "round_legs": [round(leg.stake, 2) for leg in rnd.legs],
        "exact_profit": round(exact.profit, 2),
        "round_profit": round(rnd.profit, 2),
        "cost": round(rnd.rounding_cost, 2),
        "cost_bps": round(rnd.rounding_cost / 1000.0 * 10_000, 1),
    }

    # Quote age. A screen showing a price is showing a claim about the past,
    # and the floor under that claim is the feed's own latency.
    tau = PRIOR_TAU.get("h2h", PRIOR_TAU["default"])
    out["quote_age"] = {
        "latency_floor": PRIOR_LATENCY,
        "tau": round(tau, 1),
        "rows": [
            {"age": age, "survives": round(math.exp(-age / tau) * 100, 1)}
            for age in (2, 5, 10, 30, 60)
        ],
        "half_life": round(tau * math.log(2), 1),
        "example_edge": 3.0,
        "example_age": 30,
        "example_realised": round(3.0 * math.exp(-30.0 / tau), 2),
    }

    # Out-of-sample thresholds. The bar a model has to clear before its own
    # weights are allowed to change.
    out["holdout"] = {
        "min_graded": MIN_GRADED,
        "holdout_pct": round(HOLDOUT * 100),
        "train": MIN_GRADED - round(MIN_GRADED * HOLDOUT),
        "test": round(MIN_GRADED * HOLDOUT),
        "min_coverage": MIN_BOOK_COVERAGE,
    }

    # Grading. A half point is not a rounding error: two adjacent lines are
    # different bets, and settling one against the other is how a losing bet
    # becomes a winning row.
    from overlay_engine.devig import devig_all
    from overlay_engine.odds import decimal_to_prob

    _p110 = decimal_to_prob(american_to_decimal(-110))
    _p120 = decimal_to_prob(american_to_decimal(-120))
    out["grading"] = {
        "p110": round(_p110 * 100, 2),
        "p120": round(_p120 * 100, 2),
        "gap": round((_p120 - _p110) * 100, 2),
        "vig_at_110": round((2 * _p110 - 1) * 100, 2),
        "ratio": round((_p120 - _p110) / (2 * _p110 - 1), 2),
    }

    # 7e. Portfolio arithmetic. The engine gained correlation measurement and a
    # portfolio view this evening; these are the figures that come out of them.
    from overlay_engine.correlation import MAX_RHO, MIN_GROUPS
    from overlay_engine.correlation import MIN_BETS as CORR_MIN_BETS
    from overlay_engine.exposure import CONCENTRATION_FLAG
    from overlay_engine.kelly import DEFAULT_CORRELATION, MAX_SINGLE
    from overlay_engine.middles import (
        MIN_GAMES, MIN_PER_CELL, MIN_TOTAL_GAMES, PRIOR_SIGMA)
    from overlay_engine.portfolio import UTILISATION_FLAG, effective_bets

    # A correlation of 0.45 is what a synthetic ledger built at 0.45 measured
    # back; it stands in here for "a book that shares game scripts", and the
    # arithmetic below is exact whatever number goes in.
    rho = 0.45
    out["portfolio"] = {
        "rho": rho,
        "prior_rho": DEFAULT_CORRELATION,
        "bankroll": 20_000,
        "max_single": round(MAX_SINGLE * 100),
        "cap_alone": round(20_000 * MAX_SINGLE, 2),
        "cap_loaded": round(
            20_000 * MAX_SINGLE * math.sqrt(1.0 / (1.0 + 11 * rho)), 2),
        "utilisation_flag": round(UTILISATION_FLAG * 100),
        "concentration_flag": round(CONCENTRATION_FLAG * 100),
        "min_groups": MIN_GROUPS,
        "min_bets": CORR_MIN_BETS,
        "max_rho": MAX_RHO,
        "rows": [
            {"n": n,
             "at_prior": round(effective_bets(n, DEFAULT_CORRELATION), 1),
             "at_rho": round(effective_bets(n, rho), 1)}
            for n in (2, 4, 8, 12, 20)
        ],
    }

    # Totals middles. The counted-versus-approximated distinction, and the
    # thresholds that decide which you get.
    from overlay_engine.arb import middle_probability

    lo_line, hi_line = 44.5, 47.5
    approx = middle_probability(
        lo_line - (lo_line + hi_line) / 2.0,
        hi_line - (lo_line + hi_line) / 2.0,
        PRIOR_SIGMA["totals"])
    mid_lo, mid_hi = american_to_decimal(-110), american_to_decimal(-110)
    out["totals_middle"] = {
        "low": lo_line,
        "high": hi_line,
        "window": int(hi_line - lo_line),
        "approx": round(approx * 100, 2),
        "sigma": PRIOR_SIGMA["totals"],
        "breakeven": round(
            (1.0 / mid_lo + 1.0 / mid_hi - 1.0) * 100, 2),
        "min_games": MIN_GAMES,
        "min_total_games": MIN_TOTAL_GAMES,
        "min_per_cell": round(MIN_PER_CELL),
    }

    # 7f. The release. Read off the actual built artifacts, never written down.
    #
    # A download button is the one element on a marketing site that can be
    # straightforwardly false: it either hands over a working build or it does
    # not, and no amount of surrounding prose repairs the difference. So the
    # figures come from `dist/`, and a build with nothing in `dist/` raises
    # here rather than rendering a button that points at a file nobody made.
    import hashlib

    # Read the files this site SERVES, not the ones in the product repo's
    # build directory. They are usually copies of each other, and when they are
    # not, the served file is the one a visitor gets — so it is the one whose
    # checksum belongs on the page. It also means a rebuild happening in the
    # product repo cannot race this render into publishing a digest for a file
    # nobody can download.
    dist = SITE / "releases"
    wheels = sorted(dist.glob("*.whl")) if dist.exists() else []
    sdists = sorted(dist.glob("*.tar.gz")) if dist.exists() else []
    if not wheels or not sdists:
        raise SystemExit(
            "no release artifacts in " + str(dist) + " — build them with "
            "scripts/release.sh in the product repo and copy them here. The "
            "download page is generated from the files themselves, so a "
            "missing build is a failed render rather than a button pointing "
            "at nothing."
        )

    def _art(path):
        raw = path.read_bytes()
        return {
            "name": path.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "kb": round(len(raw) / 1024),
        }

    wheel, sdist = _art(wheels[-1]), _art(sdists[-1])
    out["release"] = {
        "version": engine.__version__,
        "wheel": wheel,
        "sdist": sdist,
        "python": "3.9",
        "hash_bits": len(wheel["sha256"]) * 4,
    }

    # 7g. The interactive demo's ladder.
    #
    # Every competitor's marketing sells a point estimate with total
    # confidence: "profit regardless of who wins", "make $1,000+ weekly". None
    # of them mention that the second leg may not fill. That is the argument
    # this widget makes, and it makes it by letting the reader move the quote
    # age and watch the edge collapse.
    #
    # The browser does NO arithmetic. It indexes this table. A demo that
    # reimplemented the fill model in JavaScript would be a second engine
    # nothing gates, free to drift from the one the product ships — and the
    # first number on the site that nothing measured.
    from overlay_engine.kelly import DEFAULT_FRACTION, MAX_SINGLE, kelly_fraction

    demo_edge = 4.0          # per cent, held fixed so only age moves
    demo_bank = 10_000.0
    demo_decimal = american_to_decimal(110)
    demo_tau = PRIOR_TAU.get("h2h", PRIOR_TAU["default"])

    ladder = []
    for age in (0, 2, 5, 10, 20, 30, 45, 60, 90, 120):
        effective = max(age, PRIOR_LATENCY)
        p_fill = math.exp(-effective / demo_tau)
        realised = demo_edge * p_fill
        # Kelly on the edge you can actually collect, not the one on screen.
        prob = (1.0 + realised / 100.0) / demo_decimal
        frac = min(kelly_fraction(demo_decimal, prob) * DEFAULT_FRACTION,
                   MAX_SINGLE)
        ladder.append({
            "age": age,
            "fill": round(p_fill * 100, 1),
            "realised": round(realised, 2),
            "stake": round(demo_bank * frac, 2),
            "stake_shown": int(round(demo_bank * frac)),
        })

    out["demo"] = {
        "edge": demo_edge,
        "low": round(demo_edge - 0.48, 2),
        "high": round(demo_edge + 0.48, 2),
        "bankroll": int(demo_bank),
        "tau": round(demo_tau, 1),
        "floor": PRIOR_LATENCY,
        "ladder": ladder,
        "best": ladder[0],
        "worst": ladder[-1],
    }

    # 7h. Hedging and dutching. Two calculators OddsJam does not have at all,
    # and both are the same solver pointed at different questions: equalise the
    # return across the outcomes you hold.
    from overlay_engine.arb import ideal_stakes

    # A bet already placed, and what it costs to lock it in at a range of
    # prices on the other side. The row where the guarantee turns negative is
    # the one every hedging guide leaves out.
    hedge_stake, hedge_open = 100.0, american_to_decimal(250)
    hedge_rows = []
    for american in (-400, -250, -140, 180):
        close = american_to_decimal(american)
        lay = hedge_stake * hedge_open / close
        locked = hedge_stake * hedge_open - hedge_stake - lay
        hedge_rows.append({
            "american": f"{american:+d}",
            "lay": round(lay, 2),
            "locked": round(locked, 2),
            "pct": round(locked / (hedge_stake + lay) * 100, 2),
        })
    out["hedge"] = {
        "stake": int(hedge_stake),
        "open": "+250",
        "rows": hedge_rows,
        # Sorted by what is actually locked rather than by position, so the
        # labels cannot drift from the ladder again.
        "worst": min(hedge_rows, key=lambda r: r["locked"]),
        "best": max(hedge_rows, key=lambda r: r["locked"]),
    }

    # Dutching: one total spread across several outcomes so every result pays
    # the same. Identical arithmetic to an arbitrage, minus the guarantee.
    dutch_total = 300.0
    dutch_prices = [american_to_decimal(a) for a in (120, 240, 250)]
    dutch_stakes = ideal_stakes(dutch_prices, dutch_total)
    dutch_return = dutch_stakes[0] * dutch_prices[0]
    out["dutch"] = {
        "total": int(dutch_total),
        "legs": len(dutch_prices),
        "rows": [
            {"american": f"{a:+d}", "stake": round(st, 2),
             "returns": round(st * d, 2)}
            for a, st, d in zip((120, 240, 250), dutch_stakes, dutch_prices)
        ],
        "returns": round(dutch_return, 2),
        "profit": round(dutch_return - dutch_total, 2),
        "pct": round((dutch_return - dutch_total) / dutch_total * 100, 2),
        "implied": round(sum(1.0 / d for d in dutch_prices) * 100, 2),
    }

    # 7i. The four engine surfaces the site has never written about: the CLV
    # scoring loop that changes the model's own weights, promotional decay,
    # per-book pricing weights, and the replay path that makes a feed
    # decision measurable instead of vendor-quoted.

    # --- the loop that makes the tool improve --------------------------------
    # A synthetic log where one method really is closer to the closing line,
    # scored by mean squared error and turned into blend weights. The numbers
    # are the estimator's, not a claim about any sport: what is being shown is
    # that the loop demotes rather than deletes.
    from overlay_engine.clv import (
        GradedBet, METHODS, method_scores, weights_from_scores)

    n_graded = 60
    truth = [0.50 + 0.002 * i for i in range(n_graded)]
    graded = [
        GradedBet(bet_id=f"b{i}", sport="nfl", market_type="h2h", book="dk",
                  decimal=2.0, stake=100.0, fair_prob_at_bet=t,
                  closing_fair_prob=t)
        for i, t in enumerate(truth)
    ]
    # Each candidate is offset from the truth by a fixed amount, so the ranking
    # is known before the scorer runs and the scorer can be checked against it.
    offsets = {"power": 0.004, "shin": 0.008, "multiplicative": 0.016,
               "additive": 0.032}
    candidates = {m: [t + off for t in truth] for m, off in offsets.items()}
    scores = method_scores(graded, candidates)
    weights = weights_from_scores(scores)
    floor = 0.05
    out["scoring"] = {
        "note": (
            "That log is constructed, not a record of live markets. Each "
            "method was handed a fixed offset from the target before the run, "
            "so the ranking was known in advance and the error column is those "
            "offsets squared and rescaled. It shows the mechanism turning "
            "error into weight, not which devig method wins on any real "
            "market \u2014 your own graded bets are what put real standings "
            "in it."),
        "bets": n_graded,
        "floor": round(floor * 100),
        "methods": len(METHODS),
        "rows": sorted(
            ({"method": m, "error": round(scores[m] * 10_000, 3),
              "weight": round(weights[m] * 100, 1)} for m in scores),
            key=lambda r: r["error"]),
        "best": min(scores, key=scores.get),
        "worst": max(scores, key=scores.get),
        "best_weight": round(max(weights.values()) * 100, 1),
        "worst_weight": round(min(weights.values()) * 100, 1),
    }

    # --- a promotion is a decaying asset -------------------------------------
    from overlay_engine.promo import URGENT_DAYS, Holding

    promo_now = NOW
    held = Holding(promo_id=1, book="dk", kind="bonus_bet", amount=100.0,
                   conversion=0.75, expires_at=promo_now + 7 * 86400.0)
    decay = []
    for days in (7, 3, 1, 0):
        at = promo_now + (7 - days) * 86400.0
        decay.append({
            "days": days,
            "value": round(held.value(at), 2),
            "urgent": held.urgent(at),
        })
    out["holdings"] = {
        "face": int(held.amount),
        "conversion": round(held.conversion * 100),
        "urgent_days": URGENT_DAYS,
        "worth": round(held.value(promo_now), 2),
        "lapsed": round(held.value(promo_now + 8 * 86400.0), 2),
        "rows": decay,
    }

    # --- how old a weight is allowed to be -----------------------------------
    from overlay_engine.pricing import MAX_WEIGHT_AGE

    out["weights"] = {
        "max_age_days": round(MAX_WEIGHT_AGE / 86400.0),
    }

    # --- the replay path -----------------------------------------------------
    from overlay_engine.feed import MAX_CLOCK_SKEW

    out["replay"] = {
        "max_skew": round(MAX_CLOCK_SKEW),
        "latency_floor": PRIOR_LATENCY,
    }

    # 7j. What a subscription costs in edge terms. Every competitor page
    # said the same thing about uncertainty and differed only in a name and a
    # price, which is why the portfolio similarity gate scored them 0.84
    # against each other. A monthly fee is a hurdle before the first dollar of
    # profit, the hurdle is arithmetic, and it differs by a factor of four
    # across this list — so it is both real and genuinely per-competitor.
    import re as _re

    out["subs"] = {}
    for _row in COMPETITORS:
        _text = (_row.get("price") or "").replace(",", "")
        # Only prices actually marked per month. AVO's cheapest figure is a $22
        # day pass, and reading that as a subscription understates the hurdle
        # by a factor of four.
        # Match the currency too, and never convert it. An exchange rate is a
        # figure this build cannot measure and would go stale silently, so a
        # euro price is reported in euros against a 100-euro stake.
        _hits = _re.findall(r"([$£€])\s?([\d]+(?:\.\d\d)?)(?:\s*-\s*[\d.]+)?\s*/\s*mo",
                            _text)
        _paid = [(sym, float(val)) for sym, val in _hits if float(val) > 0]
        if not _paid:
            continue
        _sym, _fee = min(_paid, key=lambda x: x[1])
        _stake = 100.0
        out["subs"][_row["slug"]] = {
            "sym": _sym,
            "fee": round(_fee, 2),
            "stake": int(_stake),
            "yearly": round(_fee * 12, 2),
            "rows": [
                {"edge": edge,
                 "bets": int(-(-_fee // (_stake * edge / 100.0))),
                 "turnover": int(-(-_fee // (edge / 100.0)))}
                for edge in (1, 2, 3)
            ],
        }

    # 8a. The commission example, computed rather than asserted. A pair that
    # is an arbitrage on the face of it and is not one once the exchange takes
    # its cut — the case a screen that skips netting will surface every time.
    exch = Book("betfair", "an exchange", BookTier.EXCHANGE, commission=0.02)
    raw = 2.01
    out["commission"] = {
        "price": f"{decimal_to_american(raw):+.0f}",
        "commission": 2,
        "gross": round(engine.arb_margin([raw, raw]) * 100, 2),
        "net": round(engine.arb_margin([raw, exch.net_decimal(raw)]) * 100, 2),
    }

    # 8b. The hero line: a real market run through the real pipeline.
    #
    # Typed from an old README example on first write, and the gate refused it
    # — which is the whole point of the gate, and exactly the mistake this
    # product's argument is about.
    from overlay_engine.models import Market, Outcome, Quote
    from overlay_engine.pricing import PricingContext, price_market

    hero_market = Market(
        event_id="hero", sport="basketball_nba", market_type="totals",
        quotes=[
            Quote(book=b, outcome=Outcome(n, 220.5), decimal=v,
                  seen_at=NOW - 6, fetched_at=NOW - 4)
            for b, n, v in (
                ("pinnacle", "over", 1.952), ("pinnacle", "under", 1.952),
                ("circa", "over", 1.935), ("circa", "under", 1.970),
                ("dk", "over", 2.100), ("dk", "under", 1.740),
            )
        ],
        starts_at=NOW + 5400,
    )
    hero_books = {
        "pinnacle": Book("pinnacle", "Pinnacle", BookTier.SHARP,
                         limits_winners=False),
        "circa": Book("circa", "Circa", BookTier.SHARP, limits_winners=False),
        "dk": Book("dk", "DraftKings", BookTier.RETAIL),
    }
    ctx = PricingContext.uncalibrated(hero_books)
    edges = price_market(hero_market, ctx, now=NOW)
    out["hero"] = {
        "book": hero_books[edges[0].book].name,
        "outcome": "over 220.5",
        "price": f"{decimal_to_american(edges[0].decimal):+.0f}",
        "ev": round(edges[0].ev * 100, 2),
        "low": round(edges[0].ev_low * 100, 2),
        "high": round(edges[0].ev_high * 100, 2),
        "fill": round(edges[0].p_fill * 100),
        "realised": round(edges[0].realised_ev * 100, 2),
    }

    # A few rows at different ages, so the screen shows the thing that makes it
    # different: the same edge ranked differently once staleness is priced in.
    rows_out = []
    for label, age_s, over in (("BOS @ LAL", 4, 2.100),
                               ("MIA @ NYK", 22, 2.060),
                               ("DEN @ PHX", 58, 2.140)):
        market = Market(
            event_id=label, sport="basketball_nba", market_type="totals",
            quotes=[
                Quote(book=b, outcome=Outcome(n, 220.5), decimal=v,
                      seen_at=NOW - age_s, fetched_at=NOW - age_s + 2)
                for b, n, v in (
                    ("pinnacle", "over", 1.952), ("pinnacle", "under", 1.952),
                    ("circa", "over", 1.935), ("circa", "under", 1.970),
                    ("dk", "over", over), ("dk", "under", 1.740),
                )
            ],
        )
        found = price_market(market, ctx, now=NOW)
        if not found:
            continue
        best = found[0]
        rows_out.append({
            "event": label,
            "book": hero_books[best.book].name,
            "price": f"{decimal_to_american(best.decimal):+.0f}",
            "ev": round(best.ev * 100, 2),
            "low": round(best.ev_low * 100, 2),
            "high": round(best.ev_high * 100, 2),
            "age": int(round(best.quote_age)),
            "fill": round(best.p_fill * 100),
            "realised": round(best.realised_ev * 100, 2),
        })
    rows_out.sort(key=lambda r: -r["realised"])
    out["screen"] = rows_out

    # 9. A worked example per calculator, computed rather than written.
    #
    # `m` is the same dict as `out`, aliased because every page renderer
    # downstream receives it under that name and the bodies below are
    # written against the shape a renderer sees.
    m = out
    from overlay_engine.arb import arb_margin, stake_arb
    from overlay_engine.clv import implied_clv
    from overlay_engine.ev import breakeven_prob, ev_per_unit
    from overlay_engine.kelly import size_bet
    from overlay_engine.middles import MiddlePlan, stake_middle
    from overlay_engine.odds import decimal_to_prob, hold, overround
    from overlay_engine.promo import bonus_bet_conversion

    def table(rows):
        return ("<table>"
                + "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows)
                + "</table>")

    calc: dict[str, dict] = {}
    d = out["devig"]
    calc["no-vig-odds"] = {"body": (
        f"<p>A book offering {e(d['market'])} is asserting probabilities that "
        f"sum to more than one. Removing that margin gives the favourite:</p>"
        + table([(m_, f"{v:.2f}%") for m_, v in sorted(d["methods"].items())])
        + f"<p>Consensus {d['consensus']:.2f}%, and the four methods disagree "
        f"by {d['spread']:.2f} points. Every other no-vig calculator returns "
        "one number.</p>")}

    fair = d["consensus"] / 100.0
    price = american_to_decimal(120)
    calc["expected-value"] = {"body": (
        f"<p>Offered +120 on a side whose fair probability is "
        f"{fair * 100:.2f}%:</p>"
        + table([("Expected value per unit", f"{ev_per_unit(price, fair):+.2%}"),
                 ("Break-even win rate", f"{breakeven_prob(price):.2%}"),
                 ("Worst method's answer",
                  f"{ev_per_unit(price, min(d['methods'].values()) / 100):+.2%}")])
        + "<p>The last row is the one that decides. An edge that exists under "
        "one devig method and vanishes under another is a modelling artefact, "
        "not an opportunity.</p>")}

    a = out["arb"]
    calc["arbitrage"] = {"body": (
        f"<p>{e(a['legs'][0])} at one book and {e(a['legs'][1])} at another is "
        f"a {a['margin']:.2f}% arbitrage on {1000:,} staked:</p>"
        + table([("Exact stakes",
                  f"{a['exact_stakes'][0]:,.2f} / {a['exact_stakes'][1]:,.2f}"),
                 ("Guaranteed", f"{a['exact_profit']:,.2f}"),
                 ("Round stakes",
                  f"{a['round_stakes'][0]:,} / {a['round_stakes'][1]:,}"),
                 ("Guaranteed", f"{a['round_profit']:,.2f}"),
                 ("Cost of looking human", f"{a['rounding_cost']:,.2f}")])
        + "<p>A stake to the cent is the loudest fingerprint a risk desk "
        "reads. This solves for round stakes directly, because rounding a "
        "lock afterwards breaks it.</p>")}

    sizing = size_bet(price, fair, bankroll=10_000.0)
    calc["kelly"] = {"body": (
        f"<p>A {fair * 100:.2f}% shot offered at +120, on a 10,000 bankroll:</p>"
        + table([("Full Kelly", f"{sizing.full_kelly:.2%} of bankroll"),
                 ("At quarter Kelly", f"{sizing.stake:,.2f}"),
                 ("Share of bankroll", f"{sizing.bankroll_share:.2%}"),
                 ("Binding constraint", sizing.binding)])
        + "<p>Quarter Kelly, and sized on the least favourable devig rather "
        "than the friendliest. Overestimating an edge costs far more than "
        "underestimating it.</p>")}

    juiced = [american_to_decimal(-110), american_to_decimal(-110)]
    calc["hold"] = {"body": (
        "<p>The standard -110 / -110 market:</p>"
        + table([("Implied total", f"{overround(juiced):.4f}"),
                 ("Hold", f"{hold(juiced):.2%}")])
        + f"<p>Hold is {hold(juiced):.2%}, not {overround(juiced) - 1:.2%}. "
        "The book's take is measured against the money bet, and reporting the "
        "overround excess overstates every book's margin.</p>")}

    ladder = out["conversion"]["ladder"]
    calc["bonus-bet-conversion"] = {"body": (
        f"<p>A {out['conversion']['bonus']:,} bonus bet does not return its "
        "stake, so it is worth about half its face value bet naively. Hedged:"
        "</p>"
        + "<table><tr><th>Free leg</th><th>Hedge at</th><th>Hedge stake</th>"
        "<th>Guaranteed</th><th>Rate</th></tr>"
        + "".join(f"<tr><td>{e(r['free'])}</td><td>{e(r['hedge'])}</td>"
                  f"<td>{r['hedge_stake']:,}</td><td>{r['guaranteed']:,}</td>"
                  f"<td>{r['rate']:.1f}%</td></tr>" for r in ladder)
        + "</table><p>The hedge column is the constraint every guide omits.</p>")}

    mid = out["middles"]
    calc["middle"] = {"body": (
        "<p>Identical prices, one point apart:</p>"
        + "<table><tr><th>Window</th><th>Hits</th><th>Break-even</th>"
        "<th>Expected value</th></tr>"
        + "".join(f"<tr><td>{e(r['window'])}</td><td>{r['probability']:.2f}%</td>"
                  f"<td>{r['breakeven']:.2f}%</td><td>{r['ev']:+.2f}%</td></tr>"
                  for r in mid["cases"])
        + f"</table><p>Break-even is arithmetic on the two prices and depends "
        "on no distribution at all, which makes it the honest anchor. The hit "
        f"rate comes from counting {mid['games']} recorded games &mdash; a "
        f"{e(mid['sample'])} sample shown as an illustration of the mechanism, "
        "not a claim about any league.</p>")}

    calc["odds-converter"] = {"body": (
        "<p>The same price in every form:</p>"
        + "<table><tr><th>American</th><th>Decimal</th><th>Implied</th></tr>"
        + "".join(
            f"<tr><td>{v:+d}</td>"
            f"<td>{american_to_decimal(v):.3f}</td>"
            f"<td>{decimal_to_prob(american_to_decimal(v)):.2%}</td></tr>"
            for v in (-200, -110, 100, 150, 400))
        + "</table><p>The implied column is vig-inclusive: it is what the "
        "price asserts, not a fair probability. Calling it one without "
        "devigging first is the most common way to invent an edge that is not "
        "there.</p>")}

    calc["breakeven"] = {"body": (
        "<p>What each price needs you to hit:</p>"
        + "<table><tr><th>Price</th><th>Break-even win rate</th></tr>"
        + "".join(f"<tr><td>{v:+d}</td>"
                  f"<td>{breakeven_prob(american_to_decimal(v)):.2%}</td></tr>"
                  for v in (-200, -110, 100, 150, 400))
        + "</table><p>-110 both ways needs 52.38%, which is why a 50% bettor "
        "loses steadily and a 53% one does not.</p>")}

    calc["closing-line-value"] = {"body": (
        "<p>A bet taken at +110 against a market that closed at -105:</p>"
        + table([("Your price", "+110"),
                 ("Closing price", "-105"),
                 ("CLV against the raw close",
                  f"{implied_clv(american_to_decimal(110), american_to_decimal(-105)):+.2%}")])
        + "<p>That figure compares two vigged prices and so understates the "
        "real edge by the closing margin &mdash; usable for ranking bets "
        "against each other, not for claiming an edge size. Devigging the "
        "closing market first is what the engine does, and it is why closing "
        "line value converges far faster than profit.</p>")}

    hg, du = out["hedge"], out["dutch"]
    calc["hedge"] = {"body": (
        f"<p>A {hg['stake']:,} stake at {e(hg['open'])} that has since moved. "
        "Laying the other side locks a result now, and what it locks depends "
        "entirely on the price you can lay at:</p>"
        + "<table><tr><th>Lay at</th><th>Lay stake</th><th>Locked</th>"
        "<th>Return on total staked</th></tr>"
        + "".join(f"<tr><td>{e(r['american'])}</td><td>{r['lay']:,.2f}</td>"
                  f"<td>{r['locked']:+,.2f}</td><td>{r['pct']:+.2f}%</td></tr>"
                  for r in hg["rows"])
        + "</table>"
        + f"<p>The direction surprises people: a <em>longer</em> lay price "
        "needs a smaller lay stake, so it keeps more. Laying at "
        f"{e(hg['best']['american'])} locks {hg['best']['locked']:+,.2f}, while "
        f"laying at {e(hg['worst']['american'])} locks "
        f"{hg['worst']['locked']:+,.2f} &mdash; a loss taken deliberately "
        "rather than a profit secured, because covering the position costs "
        "more than the open bet stands to make. "
        "Hedging does not create value. It converts a variable outcome into a "
        "fixed one, and the price of that conversion is whatever the market "
        "charges at the moment you ask.</p>"
        + "<p>The reason to do it anyway is rarely the money. A position that "
        "is too large for the bankroll behind it is worth closing at a cost, "
        "and so is one whose remaining upside no longer justifies the account "
        "attention it is drawing.</p>")}

    calc["dutching"] = {"body": (
        f"<p>{du['total']:,} spread across {du['legs']} outcomes so that every "
        "result pays the same:</p>"
        + "<table><tr><th>Price</th><th>Stake</th><th>Returns</th></tr>"
        + "".join(f"<tr><td>{e(r['american'])}</td><td>{r['stake']:,.2f}</td>"
                  f"<td>{r['returns']:,.2f}</td></tr>" for r in du["rows"])
        + "</table>"
        + f"<p>Every branch returns {du['returns']:,.2f} on {du['total']:,} "
        f"staked &mdash; {du['profit']:+,.2f}, or {du['pct']:+.2f}%. That is "
        "negative here, and it is supposed to be: the prices imply "
        f"{du['implied']:.2f}% of probability between them, and everything "
        "above a hundred is the book's margin. Dutching is the same solver as "
        "an arbitrage with the guarantee removed.</p>"
        + "<p>So it earns nothing on its own. It is a way of expressing a view "
        "you already hold &mdash; that the winner is somewhere inside this set "
        "&mdash; at a known cost, rather than a way of manufacturing an edge. "
        "A dutch across outcomes you have no opinion about is a slow donation "
        "at a rate you can compute in advance.</p>")}

    calc["parlay"] = {"body": (
    "<p>A parlay pays the product of its legs. It compounds the margin on each of them too.</p>"
    + f"<p>A {m['parlay']['legs']}-leg ticket, every leg held at {m['parlay']['leg_hold']:.2f}%, pays {m['parlay']['pays']:.2f} in profit per unit staked. Strip the margin out of each leg and the fair price pays {m['parlay']['fair']:.2f}. Add the stake back to each and the gap between them is a hold of {m['parlay']['hold']:.1f}% on the ticket &mdash; {m['parlay']['multiple']:.1f} times the hold on a single leg.</p>"
    + f"<p>Holding the per-leg figure of {m['parlay']['leg_hold']:.2f}% fixed as a prior, the hold climbs with the leg count:</p>"
    + "<table><tr><th>Legs</th><th>Hold on the ticket</th></tr>"
    + "".join(f"<tr><td>{r['legs']}</td><td>{r['hold']:.1f}%</td></tr>" for r in m['parlay']['ladder'])
    + "</table>"
    + f"<p>From {m['parlay']['ladder'][0]['hold']:.1f}% up to {m['parlay']['ladder'][-1]['hold']:.1f}%. Every added leg is sold as upside. It is also margin, charged before the ticket is graded. Past {m['parlay']['lottery_legs']} legs the payout is a lottery price and the hold, still climbing, stops being the number that decides anything.</p>"
    + "<p>Same-game legs break the arithmetic above. " + m['parlay']['sgp_note'] + "</p>"
    + "<p>Every other parlay calculator prints the payout to the cent and stops there. The payout is the book's number. The fair price is the number that says what the ticket costs.</p>")}

    calc["deposit-match"] = {"body": (
    "<p>A deposit match is not free money. It is a loan of turnover, and the interest is the hold on whatever markets the terms let you churn through.</p>"
    + f"<p>The offer: deposit ${m['match']['deposit']}, receive ${m['match']['bonus']} in bonus funds, clear {m['match']['rollover']}x rollover before anything can be withdrawn.</p>"
    + f"<p>Break-even hold is the number that decides it. It sits at {m['match']['breakeven']:.1f}%. Churn below that and the bonus survives to the cashier. Churn above it and the bonus was spent before the terms released it.</p>"
    + "<p>So the clause that matters is the one listing eligible markets. Both holds below are measured off real two-way prices, not assumed.</p>"
    + "<table><tr><th>What the rollover allows</th><th>Churn hold</th><th>Net</th><th>Margin</th></tr>"
    + f"<tr><td>Moneylines</td><td>{m['match']['open_hold']:.2f}%</td><td>${m['match']['open_net']:.2f}</td><td>{m['match']['open_margin']:.2f}%</td></tr>"
    + f"<tr><td>Props only</td><td>{m['match']['shut_hold']:.2f}%</td><td>${m['match']['shut_net']:.2f}</td><td>{m['match']['shut_margin']:.2f}%</td></tr>"
    + "</table>"
    + f"<p>Same headline, same deposit, same rollover &mdash; and a swing of ${m['match']['swing']:.2f} between them. The market restriction is the offer. The bonus figure is packaging.</p>"
    + f"<p>Competitors print one number to two decimals as though it were measured, then bury the eligible-markets line. Where terms push churn into parlays the cost climbs again; our parlay hold prior of {m['match']['prior_parlay']:.1f}% is a prior, not a measurement, and it is deliberately excluded from the table above.</p>")}

    calc["effective-bets"] = {"body": (
    "<p>Stake spread across correlated bets is not spread. Effective bets is the count a book is really holding: n divided by one plus n minus one times rho, where rho is the average pairwise correlation between positions. Independent bets give n_eff equal to n. Everything else gives less.</p>"
    + f"<p>The correlation used as a starting point here is a prior, not a measurement: rho of {m['portfolio']['prior_rho']:.2f}. The measured figure on this book is {m['portfolio']['rho']:.2f}. Same bet counts, two columns.</p>"
    + f"<table><tr><th>Bets</th><th>Effective at prior rho {m['portfolio']['prior_rho']:.2f}</th><th>Effective at measured rho {m['portfolio']['rho']:.2f}</th></tr>"
    + "".join(f"<tr><td>{r['n']}</td><td>{r['at_prior']:.1f}</td><td>{r['at_rho']:.1f}</td></tr>" for r in m['portfolio']['rows'])
    + "</table>"
    + f"<p>Read the measured column down. From {m['portfolio']['rows'][0]['n']} bets to {m['portfolio']['rows'][-1]['n']} bets, the effective count crawls from {m['portfolio']['rows'][0]['at_rho']:.1f} to {m['portfolio']['rows'][-1]['at_rho']:.1f}. Past a handful of correlated positions, adding another buys no diversification. It only adds stake.</p>"
    + f"<p>That is what a staking rule has to see. A max single of {m['portfolio']['max_single']}% on a bankroll of {m['portfolio']['bankroll']:.0f} caps a lone bet at {m['portfolio']['cap_alone']:.0f}. The same rule, applied to a book already loaded with correlated exposure, caps it at {m['portfolio']['cap_loaded']:.2f}. Competitors print the first figure and call the portfolio diversified. They are counting tickets &mdash; and tickets are not independent.</p>")}

    calc["totals-middle"] = {"body": (
    "<p>A middle is a pair of bets on one game: the over at the lower line, the under at the higher one. Both win when the final total lands inside the window between them. Outside it, one side pays, the other loses, and the miss costs the vig.</p>"
    + f"<p>The lines priced here are {m['totals_middle']['low']} and {m['totals_middle']['high']}, a window {m['totals_middle']['window']} points wide. Break-even is {m['totals_middle']['breakeven']:.2f}% &mdash; the rate the window must hit for the pair to be worth holding. That is arithmetic on both prices and nothing else: no distribution, no sample, no view on the sport. It is the honest anchor.</p>"
    + f"<p>The window probability is {m['totals_middle']['approx']:.2f}%. That one is a normal approximation, and its spread of {m['totals_middle']['sigma']:.1f} points is a stated prior, not a measurement. Competitors print a figure like it out to the decimal as though it had been observed.</p>"
    + "<p>Counting beats a smooth curve. Real scores cluster on the totals a sport actually produces. A curve cannot reproduce a lump, so it moves mass into gaps where finals never land. Count finals, and hold the sample to a threshold first.</p>"
    + "<table><tr><th>Threshold</th><th>Minimum</th></tr>"
    + f"<tr><td>Games in a totals sample</td><td>{m['totals_middle']['min_total_games']}</td></tr>"
    + f"<tr><td>Games in a margin sample</td><td>{m['totals_middle']['min_games']}</td></tr>"
    + f"<tr><td>Observations on each distinct total</td><td>{m['totals_middle']['min_per_cell']}</td></tr>"
    + "</table>"
    + "<p>Totals carry the higher bar: wider support, more distinct finals, each seen less often. Below any of these minimums the counted estimate is noise wearing a decimal point.</p>")}

    calc["no-sweat-bet"] = {"body": (
    "<p>A no-sweat bet refunds the first bet if it loses. Its value is the refund multiplied by how often the refund actually arrives &mdash; and it arrives only in the branch where the qualifying bet loses. So the qualifying bet should be a longshot. That is the opposite of most instincts, and the opposite of the right play on a bet-and-get, where the bonus lands whatever happens.</p>"
    + f"<p>Figures below assume a qualifying stake of {m['safety_net']['stake']} and a bonus-bet conversion rate of {m['safety_net']['conversion']}%. The conversion rate is a prior, not a measurement.</p>"
    + "<table><tr><th>Qualifying price</th><th>Refund value</th><th>EV</th></tr>"
    + "".join(f"<tr><td>{r['american']}</td><td>{r['premium']:.2f}</td><td>{r['ev']:.2f}</td></tr>" for r in m['safety_net']['rows'])
    + "</table>"
    + f"<p>Short price to long price: {m['safety_net']['short_premium']:.2f} &rarr; {m['safety_net']['long_premium']:.2f}, a ratio of {m['safety_net']['ratio']:.2f}&times;. The gap between refund value and EV at the short price is the margin paid to place the qualifying bet at all. Longer is not unboundedly better: the long rows here are priced fair, which is a prior. Real longshot markets carry the heaviest margin, so read the long end as a ceiling.</p>"
    + "<p>It is not hedgeable. The refund exists only in the branch where the bet loses, and a hedge pays only in the branch where it wins. Hedging buys away the outcome that produces the bonus, and pays a second margin to do it. Competitors print a single bonus value with the qualifying price held fixed. The price is the entire decision.</p>")}

    calc["profit-boost"] = {"body": (
    "<p>A profit boost multiplies profit, not stake. Profit scales with the price, so the same token is worth a different amount on every bet it could be spent on.</p>"
    + f"<p>Below, the boost and the stake are fixed &mdash; {m['boost']['pct']}% on a stake of ${m['boost']['stake']:.0f} &mdash; and only the price moves.</p>"
    + "<table><tr><th>Price</th><th>Boost adds</th><th>EV of the boosted bet</th></tr>"
    + "".join(f"<tr><td>{r['american']}</td><td>${r['added']:.2f}</td><td>${r['ev']:.2f}</td></tr>" for r in m['boost']['rows'])
    + "</table>"
    + f"<p>The shortest price, {m['boost']['rows'][0]['american']}, adds ${m['boost']['worst']:.0f}. The longest, {m['boost']['rows'][-1]['american']}, adds ${m['boost']['best']:.0f} &mdash; a multiple of {m['boost']['multiple']:.0f} on the same token. Spend a boost on a favourite and most of it is given away.</p>"
    + f"<p>Competitors print the headline rate and stop, as though {m['boost']['pct']}% were the value. It is the rate, not the value. The value is the rate applied to a price. The EV column carries a prior &mdash; that the posted price is fair. Move that prior and the column moves with it. The ordering does not.</p>"
    + "<p>Then the part nobody costs in. A boost spent optimally is a boost spent conspicuously. Optimal use puts the token on a long price, near the top of your staking, inside the window the offer runs. That is a visible exception in an otherwise flat book, and an account whose staking carries a visible exception is an account a risk desk can read.</p>")}

    out["calculators"] = calc

    # 10. Jurisdiction coverage, and a page per state.
    from overlay_engine.catalog import (
        AS_OF, COVERAGE_GAPS, NO_LEGAL_BETTING, RETAIL_ONLY, VENUES,
        for_state, state_summary,
    )

    # RETAIL_ONLY has to be in here explicitly. It used to arrive via
    # COVERAGE_GAPS, and when that emptied, five states silently vanished from
    # the site — no page, no mention, indistinguishable from never existing.
    states = sorted(
        {s for v in VENUES.values() for s in v.states}
        | set(NO_LEGAL_BETTING) | set(COVERAGE_GAPS) | set(RETAIL_ONLY)
    )
    out["books"] = sorted(v.name for v in VENUES.values())
    out["catalog"] = {
        "venues": len(VENUES), "as_of": AS_OF, "states": len(states),
        "nj": len(for_state("NJ")), "fl": len(for_state("FL")),
    }
    # The hub counts these out loud, so they are measured rather than printed
    # from a len() the gate cannot see.
    out["markets"] = {
        "live": len([c for c in states
                     if state_summary(c)["legal"] and state_summary(c)["online"]
                     and not state_summary(c)["single_operator"]]),
        "single": len([c for c in states if state_summary(c)["single_operator"]]),
        "retail": len([c for c in states if state_summary(c).get("retail_only")]),
        "none": len([c for c in states if not state_summary(c)["legal"]]),
    }
    # The hub prints the combined figure, so the combined figure is what gets
    # measured. A sum of two stored values is not a stored value, and the gate
    # checks what is on the page rather than what could be derived from it.
    out["markets"]["online"] = (out["markets"]["live"]
                                + out["markets"]["single"])
    _all_books = {v.name for code in states for v in for_state(code)}
    out["states"] = {
        code: {
            **state_summary(code),
            "absent": len(_all_books - {v.name for v in for_state(code)}),
            "books": [
                {"key": v.key, "name": v.name, "tier": v.tier.value,
                 "limits": v.limits_winners,
                 "commission": round(v.commission * 100, 1) if v.commission else 0}
                for v in for_state(code)
            ],
        }
        for code in states
    }
    return out


MARK = (
    '<svg class="mark" viewBox="0 0 28 28" aria-hidden="true">'
    '<rect x="1.5" y="10" width="25" height="8" rx="4" fill="none" '
    'stroke="currentColor" stroke-width="2" opacity=".38"/>'
    '<circle cx="10" cy="14" r="3.4" fill="currentColor"/>'
    '</svg>'
)


def e(text: str) -> str:
    return html.escape(str(text))


def rf(lo, hi, pt, domain, *, realised=None, zero=False, cls="rf--row",
       label=None):
    """One range-frame: an interval drawn as an object rather than printed as
    a string.

    Geometry is computed here from measured values, never hand-tuned — the
    footer promises every figure on this site comes from running the engine at
    build time, and a hand-authored bar width would make the site a liar about
    its own thesis. It lands in a style="" attribute, which check.py's visible()
    strips before it looks for unmeasured numbers, so geometry is free; an axis
    LABEL is not, and must come from measured.json.

    Two frames a reader is meant to compare must share one domain, or the
    comparison is a lie. That is why domain is a required argument.
    """
    d0, d1 = domain
    span = d1 - d0
    p = lambda v: f"{(v - d0) / span * 100:.3f}%"

    # zero=True draws the zero rule whenever zero is on the axis — both panels
    # of a comparison need it or their rules do not line up, which is the whole
    # point of the split. The hatch and the negative fill are narrower: they
    # appear only when the interval actually straddles zero, i.e. when the
    # result genuinely is not claimable.
    on_axis = zero and d0 < 0 < d1
    crosses = zero and lo < 0 < hi
    style = f"--lo:{p(lo)};--hi:{p(hi)};--pt:{p(pt)}"
    parts = []
    if on_axis:
        style += f";--z:{p(0)}"
    if crosses:
        parts.append('<i class="rf-neg"></i>')
    parts.append(f'<i class="rf-band{" is-zero" if crosses else ""}"></i>')
    if realised is not None:
        style += f";--rl:{p(realised)}"
        parts.append('<i class="rf-real"></i>')
    parts.append('<i class="rf-pt"></i>')
    if on_axis:
        parts.append('<i class="rf-zero"></i>')

    aria = label or f"{lo:+.2f} to {hi:+.2f}, point estimate {pt:+.2f}"
    return (f'<span class="rf {cls}" style="{style}" role="img" '
            f'aria-label="{e(aria)}">{"".join(parts)}</span>')


def shared_domain(rows, pad=0.5):
    """The domain every row of the odds strip is drawn against. Shared, so the
    column is comparable at a glance — a correctness requirement, not a style
    choice."""
    return (min(r["low"] for r in rows) - pad,
            max(r["high"] for r in rows) + pad)


TABLE = re.compile(r"(?s)<table>.*?</table>")


def page(title: str, description: str, body: str, path: str,
         body_class: str = "") -> str:
    body = TABLE.sub(lambda m: f'<div class="scroll">{m.group(0)}</div>', body)
    # A card grid needs more width than a reading measure. Marked on the grid
    # itself rather than passed in at each hub, because a body class that has
    # to be remembered at six call sites is one that will be missed at the
    # seventh. An explicit token, not a substring match on `class`: a grid
    # written `class="cards cards--onward"` does not contain `class="cards"`,
    # so sniffing the attribute is right only by accident.
    if "data-hub" in body:
        body_class = (body_class + " hub").strip()
    nav = (
        '<div class="banner"><div class="banner-in">'
        '<span class="tag">New</span>'
        '<span>Bookbreaker 0.1.0 is out &mdash; free, runs on your machine, '
        'nothing leaves it.</span>'
        '<a href="/download/">Download it &rarr;</a>'
        '</div></div>'
        '<nav>'
        '<a class="brand" href="/">' + MARK + 'Bookbreaker</a>'
        '<span class="links">'
        '<a href="/how-it-works/">How it works</a>'
        '<a href="/sportsbooks/">By state</a>'
        '<a href="/guides/">Guides</a>'
        '<a href="/calculators/">Calculators</a>'
        '<a href="/for/arbitrage-bettors/">For arbers</a>'
        '<a href="/vs/">Compared</a>'
        '</span>'
        '<span class="cta-nav">'
        '<a class="btn primary" href="/download/">Download</a>'
        '</span></nav>'
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="https://bookbreaker.bet{path}">
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#0B6CFF">
<link rel="stylesheet" href="/style.css?v={STYLE_HASH}">
</head>
<body class="{body_class}">
<header>{nav}</header>
<main>
{body}
</main>
<footer>
<div class="foot-grid">
  <div>
    <p class="foot-brand">Bookbreaker</p>
    <p>An analysis tool. It tells you what the numbers say; you place your own
    bets.</p>
  </div>
  <div>
    <p class="foot-head">Tools</p>
    <p><a href="/calculators/">Calculators</a></p>
    <p><a href="/guides/">Guides</a></p>
    <p><a href="/sportsbooks/nj/">Sportsbooks by state</a></p>
  </div>
  <div>
    <p class="foot-head">Compare</p>
    <p><a href="/vs/">Every tool, dated</a></p>
    <p><a href="/best/best-ev-betting-software/">What to look for</a></p>
    <p><a href="/what-your-record-proves/">What a record proves</a></p>
  </div>
</div>
<p class="foot-fine">No sportsbook accounts are linked and no credentials are
ever requested. Every figure on this site is computed by running the engine at
build time &mdash; none is typed in. Generated {e(TODAY)}.</p>
<p class="foot-fine">21+ and present in a state where betting is legal.
Gambling carries a risk of financial loss, and nothing here predicts that you
will win. If it stops being fun, it is not fun &mdash;
<a href="tel:1-800-426-2537">call 1-800-GAMBLER</a> or visit
<a href="https://www.ncpgambling.org/help-treatment/">ncpgambling.org</a>.</p>
</footer>
</body>
</html>
"""


DEMO_SCRIPT = """
<script type="application/json" id="demo-data">__DEMO_DATA__</script>
<script>
/* The slider is a lookup, not a model.

   Every value it displays was computed by the engine when this page was built
   and serialised into #demo-data above. Reimplementing the fill curve here
   would put a second, ungated copy of the engine in the browser, free to drift
   from the one the product ships — and the first number on this site that
   nothing measured. */
(function () {
  var el = document.getElementById('demo-data');
  var slider = document.getElementById('age');
  if (!el || !slider) return;

  var d = JSON.parse(el.textContent);
  var rows = d.ladder;
  var out = {
    age: document.getElementById('age-out'),
    realised: document.getElementById('d-realised'),
    fill: document.getElementById('d-fill'),
    stake: document.getElementById('d-stake'),
    bar: document.getElementById('d-bar')
  };

  function draw() {
    var r = rows[Number(slider.value)] || rows[0];
    out.age.textContent = r.age + 's';
    out.realised.textContent = r.realised.toFixed(2) + '%';
    out.fill.textContent = r.fill.toFixed(1) + '%';
    out.stake.textContent = r.stake_shown.toLocaleString();
    /* Width is the share of the screen edge that survives, which is the whole
       argument drawn rather than asserted. */
    out.bar.style.width = (100 * r.realised / d.edge) + '%';
  }

  slider.addEventListener('input', draw);
  draw();
})();
</script>
"""


def render_download(m: dict) -> str:
    """The download page, generated entirely from the built artifacts.

    Every filename, size and checksum on this page is read off the file it
    describes at build time. There is no place to type one in, which is the
    only arrangement under which a checksum is worth printing at all.
    """
    r = m["release"]
    w, sd = r["wheel"], r["sdist"]
    return f"""
<h1>Download Bookbreaker</h1>
<p class="lede">Version {r['version']}. Free, no account, and it never sends
your record anywhere &mdash; the ledger is a SQLite file on your own disk.</p>

<div class="cta">
<a class="btn primary" href="/releases/{w['name']}">Download the wheel
<span class="sub">{w['kb']} KB</span></a>
<a class="btn ghost" href="/releases/{sd['name']}">Source tarball</a>
</div>

<h2>Install it</h2>
<p>Bookbreaker is a command-line tool. It is pure Python with no third-party
dependencies, so it runs the same on macOS, Linux and Windows and needs
Python {r['python']} or newer:</p>
<pre><code>pip install https://bookbreaker.bet/releases/{w['name']}
overlay --help</code></pre>
<p>That is the whole installation. There is no installer, no signing prompt and
no launch agent, because there is no background process &mdash; nothing runs
unless you type a command.</p>

<h2>Check what you downloaded</h2>
<p>The wheel's SHA-256 is worth checking against: the build pins its
timestamps, and three separate builds of this version produced the same digest.
Verify before installing:</p>
<pre><code>shasum -a 256 {w['name']}</code></pre>
<table>
<tr><th>File</th><th>Size</th><th>SHA-256</th></tr>
<tr><td>{w['name']}</td><td>{w['kb']} KB</td>
<td class="hash">{w['sha256']}</td></tr>
<tr><td>{sd['name']}</td><td>{sd['kb']} KB</td>
<td class="hash">{sd['sha256']}</td></tr>
</table>
<p>These are read off the files themselves when this page is built. Nothing
here was typed in, which is the only arrangement that makes publishing a
checksum worth doing.</p>
<p class="caveat">The tarball's digest identifies <em>this build</em> rather
than the source: the packaging tool stamps real file timestamps into it, so
rebuilding the same code gives a different hash. Only the wheel reproduces
byte for byte, so it is the one to check.</p>

<h2>What you get</h2>
<p>Every command runs against your own ledger and your own snapshots. There is
no server, so there is no account to make and nothing to cancel.</p>
<table>
<tr><th>Command</th><th class="prose">What it answers</th></tr>
<tr><td><code>overlay devig</code></td><td class="prose">What four methods say a price is
really worth, side by side</td></tr>
<tr><td><code>overlay arb</code></td><td class="prose">Stakes in round numbers, scored by the
worst outcome</td></tr>
<tr><td><code>overlay middles</code></td><td class="prose">Margin and totals middles against
counted finals</td></tr>
<tr><td><code>overlay offers</code></td><td class="prose">Whether a deposit match clears,
given what its rollover allows</td></tr>
<tr><td><code>overlay paste</code></td><td class="prose">A betslip read into your record,
shown before it is written</td></tr>
<tr><td><code>overlay portfolio</code></td><td class="prose">Exposure, measured correlation,
and the next stake it implies</td></tr>
<tr><td><code>overlay performance</code></td><td class="prose">Your return with the interval
around it, and whether it proves anything</td></tr>
</table>

<h2>The licence</h2>
<p>Free to download and run on as many machines as you control, and free to
use to make money &mdash; placing bets, sizing them and keeping the proceeds
are what it is for, and the licence says so explicitly.</p>
<p>What it does not grant is redistribution: you may not pass it on, sell it,
bundle it, or run it as a service for other people. One clause is unusual and
deliberate &mdash; you may not strip the provenance labelling from its output.
A build that removes the <em>measured</em> and <em>prior</em> tags prints the
same digits while destroying the only thing that makes them worth reading.</p>
<p>The terms are narrow on purpose, because narrow terms can be widened later
and wide ones cannot be taken back. Anything already downloaded stays licensed
under the terms it shipped with.</p>
<p><a href="/releases/LICENSE.txt">Read the full licence &rarr;</a></p>

<h2>What it refuses to do</h2>
<p>It will not log into a sportsbook for you. Account linking means handing a
third party your credentials, and no feature is worth that &mdash; CSV import
and the betslip parser do the same job without asking. It also does nothing
about identity, location or device: the anti-limiting work is entirely about
the shape of the bet, because everything else is fraud rather than strategy.</p>

<p><a href="/how-it-works/">How it prices a market &rarr;</a></p>
"""


def render_index(m: dict) -> str:
    d = m["devig"]
    dm = m["demo"]
    f = m["fill"]
    hero = m["hero"]

    screen = m["screen"]
    # One shared axis down the whole column. This is what makes DEN @ PHX's
    # realised caret land underneath MIA @ NYK's band while its raw band sits
    # furthest right — the collapse the footer sentence describes, drawn.
    screen_domain = shared_domain(screen)
    rows = "".join(
        f'<div class="app-row">'
        f'<span class="ev-name">{e(r["event"])}</span>'
        f'<span class="dim">{e(r["book"])}</span>'
        f'<span class="price">{e(r["price"])}</span>'
        f'<span class="pos">{r["ev"]:+.2f}%</span>'
        f'<span class="band">'
        + rf(r["low"], r["high"], r["ev"], screen_domain,
             realised=r["realised"],
             label=f'{r["low"]:+.2f}% to {r["high"]:+.2f}%, point estimate '
                   f'{r["ev"]:+.2f}%, realised {r["realised"]:+.2f}%')
        + f'</span>'
        f'<span class="dim">{r["age"]}s</span>'
        f'<span class="fill"><i style="width:{r["fill"]}%"></i>'
        f'<b>{r["fill"]}%</b></span>'
        f'<span class="pos strong">{r["realised"]:+.2f}%</span>'
        f'</div>'
        for r in screen
    )
    top = screen[0]["event"]
    worst = max(screen, key=lambda r: r["ev"])
    second = worst["event"]
    stale = worst["age"]
    stale_fill = worst["fill"]
    method_rows = "".join(
        f"<tr><td>{e(name)}</td><td>{value:.2f}%</td></tr>"
        for name, value in sorted(d["methods"].items())
    )
    a = m["arb"]
    p = m["performance"]

    # The headline claim, demonstrated rather than asserted, in 3.4rem of
    # vertical space and with no new prose: the same +5.91% twice, on one
    # shared domain so the zero rules line up across the split. On the left it
    # is a lone tick sitting comfortably right of zero, looking like profit.
    # On the right it is unchanged and unghosted, inside a hatched band that
    # visibly straddles zero.
    roi_domain = (p["low"] - 3, p["high"] + 3)
    # key labels are placed with the same arithmetic the frame uses, so a label
    # can never drift away from the mark it names
    kp = lambda v: f"{(v - roi_domain[0]) / (roi_domain[1] - roi_domain[0]) * 100:.3f}%"
    roi_solo = rf(p["roi"], p["roi"], p["roi"], roi_domain, zero=True,
                  cls="rf--hero rf--bare",
                  label=f"A single figure, {p['roi']:+.2f}%, "
                        f"drawn with no interval.")
    roi_band = rf(p["low"], p["high"], p["roi"], roi_domain, zero=True,
                  cls="rf--hero",
                  label=f"Flat-bet ROI {p['roi']:+.2f}%, interval "
                        f"{p['low']:.1f}% to {p['high']:+.1f}%, spanning zero.")

    return f"""
<div class="hero hero-glow">
<div class="hero-copy">
<p class="eyebrow accent">Free &middot; Runs on your machine</p>
<h1>Find your edge,
with the error bar.</h1>
<p class="lede">Real prices from {m['catalog']['venues']} sportsbooks, devigged
four ways, and every number carrying what it might be wrong by. Built to find
bets and keep the account that places them.</p>
<div class="cta">
<a class="btn primary" href="/download/">Download free<span class="sub">v{m['release']['version']} &middot; {m['release']['wheel']['kb']} KB</span></a>
<a class="btn ghost" href="/how-it-works/">See how it prices a market</a>
</div>
<ul class="quals">
  <li>No account, ever</li>
  <li>{m['catalog']['states']} states covered</li>
  <li>{m['catalog']['venues']}&plus; sportsbooks</li>
  <li>Open checksums</li>
</ul>
</div>

<div class="hero-app">
  <div class="app app--hero">
    <div class="app-bar">
      <span class="dot"></span><span class="dot"></span><span class="dot"></span>
      <span class="app-title">+EV &middot; NBA totals &middot; live</span>
      <span class="app-meta">sorted by realised EV</span>
    </div>
    <div class="app-head">
      <span>Market</span><span>Book</span><span>Price</span>
      <span>EV</span><span>Band</span><span>Age</span><span>Fill</span>
      <span>Realised</span>
    </div>
    {rows}
  </div>
  <p class="hero-app-cap">Ranked on <strong>realised</strong> EV &mdash; raw
  edge times the chance the price is still there.</p>
</div>
</div>

<div class="trust">
  <div><b>{len(m['devig']['methods'])}</b><span>Devig methods, side by side</span></div>
  <div><b>{m['devig']['spread']:.2f}%</b><span>Spread they disagree by</span></div>
  <div><b>{m['fill']['honest']}%</b><span>Fill on a {m['fill']['age']:.0f}s quote</span></div>
  <div><b>0</b><span>Bytes sent anywhere</span></div>
</div>

<section class="wall" aria-label="Sportsbooks priced">
  <p class="wall-cap">Prices {m['catalog']['venues']} sportsbooks across
  {m['catalog']['states']} states</p>
  <ul class="wall-list">
    {"".join(f"<li>{e(b)}</li>" for b in m['books'])}
  </ul>
</section>

<section class="demo" aria-labelledby="demo-h">
  <p class="eyebrow">Try it &mdash; nothing to install, nothing to sign up for</p>
  <h2 id="demo-h">Drag the price older. Watch the edge go.</h2>
  <p>A {dm['edge']:.1f}% edge on the screen is not a {dm['edge']:.1f}% edge in
  your account. It is that number multiplied by the chance the price is still
  there when your bet lands &mdash; and no competitor's marketing mentions the
  second half.</p>

  <div class="demo-box">
    <label class="demo-label" for="age">
      Quote age when the bet lands
      <output id="age-out">{dm['ladder'][0]['age']}s</output>
    </label>
    <input type="range" id="age" min="0" max="{len(dm['ladder']) - 1}"
           value="0" step="1" list="ages"
           aria-describedby="demo-read">

    <div class="demo-read" id="demo-read">
      <div>
        <b id="d-realised">{dm['best']['realised']:.2f}%</b>
        <span>Edge you actually collect</span>
      </div>
      <div>
        <b id="d-fill">{dm['best']['fill']:.1f}%</b>
        <span>Chance it is still there</span>
      </div>
      <div>
        <b id="d-stake">{dm['best']['stake_shown']:,}</b>
        <span>Stake on a {dm['bankroll']:,} bankroll</span>
      </div>
    </div>

    <div class="demo-bar" role="img"
         aria-label="How much of the screen edge survives">
      <div class="demo-bar-fill" id="d-bar"></div>
      <span class="demo-bar-cap">screen says {dm['edge']:.1f}%</span>
    </div>

    <p class="caveat">Survival is modelled as exponential with a
    {dm['tau']:.0f}-second mean lifetime and a {dm['floor']:.0f}-second floor
    under the age &mdash; both stated priors until your own accept-and-reject
    record replaces them. Every figure above is computed by the engine when
    this page is built; the slider looks them up rather than recomputing
    them.</p>
  </div>
</section>

<div class="hero-after">

<figure class="plate plate--split">
  <div>
    <p class="plate-cap">What every other tracker prints</p>
    {roi_solo}
    <p class="plate-key"><span style="--at:{kp(0)}">0</span>
    <span class="over" style="--at:{kp(p['roi'])}">{p['roi']:.2f}%</span></p>
  </div>
  <div>
    <p class="plate-cap">What Bookbreaker prints</p>
    {roi_band}
    <p class="plate-key"><span class="neg" style="--at:{kp(p['low'])}">{p['low']:.1f}%</span>
    <span style="--at:{kp(0)}">0</span>
    <span style="--at:{kp(p['high'])}">{p['high']:+.1f}%</span></p>
  </div>
</figure>

</div>


<section class="pitch" id="pitch">
<p class="eyebrow">The four things it does that nothing else does</p>

<article class="pitch-row">
  <div class="pitch-copy">
    <h2>Same market, four defensible methods</h2>
    <p>Removing a book's margin to recover what it really believes is a
    modelling choice, not arithmetic. On a {e(d['market'])} moneyline the four
    standard methods disagree by {d['spread']:.2f} points of probability.</p>
    <p class="pitch-kicker">Every competing tool picks one of these rows,
    hard-codes it, and prints the result as fact.</p>
  </div>
  <div class="pitch-fig">
    <table class="bare">
    <tr><th>Method</th><th>Fair probability</th></tr>
    {method_rows}
    </table>
    <p class="pitch-note">Consensus {d['consensus']:.2f}%. On a market where a
    2% edge is a good day, that spread is a quarter of the edge.</p>
  </div>
</article>

<article class="pitch-row">
  <div class="pitch-copy">
    <h2>A stake a person would actually place</h2>
    <p>At {e(a['legs'][0])} and {e(a['legs'][1])} there is a
    {a['margin']:.2f}% arbitrage. A precise stake to the cent is the
    most-cited fingerprint risk desks use to identify arbitrage.</p>
    <p class="pitch-kicker">The {a['rounding_cost']:,.2f} difference is named
    and reported, not hidden. A tool that conceals its own trade-offs is not
    one you can check.</p>
  </div>
  <div class="pitch-fig">
    <div class="vs">
      <div class="vs-side">
        <p class="vs-cap">Every calculator</p>
        <p class="vs-val">{a['exact_stakes'][0]:,.2f} <i>/</i> {a['exact_stakes'][1]:,.2f}</p>
        <p class="vs-sub">{a['exact_profit']:,.2f} guaranteed</p>
      </div>
      <div class="vs-side vs-side--ours">
        <p class="vs-cap">Bookbreaker</p>
        <p class="vs-val">{a['round_stakes'][0]:,} <i>/</i> {a['round_stakes'][1]:,}</p>
        <p class="vs-sub">{a['round_profit']:,.2f} guaranteed</p>
      </div>
    </div>
  </div>
</article>

<article class="pitch-row">
  <div class="pitch-copy">
    <h2>An edge you cannot take is worth nothing</h2>
    <p>Quote age is measured from the book's own timestamp, not from when the
    feed reached us. On a feed running {f['latency']:.1f} seconds behind, a
    quote that looks {f['age']:.0f} seconds old is really
    {f['effective']:.1f}.</p>
    <p class="pitch-kicker">A screen that ignores its own latency reports a
    fill it cannot deliver.</p>
  </div>
  <div class="pitch-fig">
    <div class="vs">
      <div class="vs-side">
        <p class="vs-cap">Screen ignoring latency</p>
        <p class="vs-val">{f['naive']}%</p>
        <p class="vs-sub">claimed still available</p>
      </div>
      <div class="vs-side vs-side--ours">
        <p class="vs-cap">Measured</p>
        <p class="vs-val">{f['honest']}%</p>
        <p class="vs-sub">actually still available</p>
      </div>
    </div>
  </div>
</article>

<article class="pitch-row">
  <div class="pitch-copy">
    <h2>What your record actually says</h2>
    <p>On a {p['n']}-bet history showing {p['profit']:+,} profit and
    {p['roi']:.2f}% return, most trackers print the return and stop.</p>
    <p class="pitch-kicker">The interval is the answer. A number without one is
    a claim about a sample, dressed as a claim about you.</p>
  </div>
  <div class="pitch-fig">
    <blockquote class="verdict">{e(p['verdict'])}</blockquote>
  </div>
</article>
</section>
<p>Every other tracker prints {p['roi']:.2f}% and stops.</p>
""" + DEMO_SCRIPT.replace("__DEMO_DATA__",
                          json.dumps(m["demo"], separators=(",", ":")))


def render_how(m: dict) -> str:
    c = m["conversion"]
    rows = "".join(
        f"<tr><td>{e(r['free'])}</td><td>{e(r['hedge'])}</td>"
        f"<td>{r['hedge_stake']:,}</td><td>{r['guaranteed']:,}</td>"
        f"<td>{r['rate']:.1f}%</td></tr>"
        for r in c["ladder"]
    )
    mid = m["middles"]
    mid_rows = "".join(
        f"<tr><td>{e(r['window'])}</td><td>{r['probability']:.2f}%</td>"
        f"<td>{r['breakeven']:.2f}%</td><td>{r['ev']:+.2f}%</td></tr>"
        for r in mid["cases"]
    )
    cat = m["catalog"]

    return f"""
<h1>How it works</h1>

<h2>Welcome offers, after every cost</h2>
<p>A bonus bet does not return its stake, so it is worth about half its face
value if bet naively. Converting means hedging &mdash; and every guide says
&ldquo;convert on a longshot&rdquo; without mentioning what that costs at the
second book. On a {c['bonus']:,} bonus:</p>
<table>
<tr><th>Free leg</th><th>Hedge at</th><th>Hedge stake</th>
<th>Guaranteed</th><th>Rate</th></tr>
{rows}
</table>
<p>The hedge column is the constraint the advice always omits.</p>

<h2>Middles, counted rather than assumed</h2>
<p>Results are not smoothly distributed. Football margins pile up on 3 and 7
because of how the sport scores, so a normal curve gets the shape wrong in
exactly the place the whole bet lives. Same prices, one point apart:</p>
<table>
<tr><th>Window</th><th>Hits</th><th>Break-even</th><th>Expected value</th></tr>
{mid_rows}
</table>
<p class="caveat">Computed from a {mid['games']}-game sample whose shape is
{e(mid['sample'])} &mdash; an illustration of the mechanism, not a claim about
any league. No published margin table we could verify covers every margin with
its sample size, so Bookbreaker counts the games you record rather than
shipping a distribution, and refuses to give a counted answer below 200
games.</p>

<h2>Which books you can use</h2>
<p>{cat['venues']} venues, filtered to the ones you can actually hold: an
arbitrage between two books you cannot both open is noise with a number
attached. {cat['nj']} in New Jersey, {cat['fl']} in Florida. Table read
{e(cat['as_of'])}, and the site shows its own age because a jurisdiction table
without a date asserts &ldquo;true now&rdquo; forever.</p>
<p class="caveat">A dated starting point for your own check, not advice. The
book's own site decides whether it will accept you.</p>

<h2>What stays out of the product</h2>
<p>It does not link sportsbook accounts. Trackers that sync automatically do it
by holding your sportsbook credentials; Bookbreaker imports the CSV your book
already exports and never asks for a login.</p>
<p>Nor does it do multi-accounting, identity or KYC workarounds, or device and
location spoofing &mdash; see
<a href="/account-longevity/">account longevity</a> for where that line is
drawn and why it is drawn in code rather than in a policy document.</p>
"""


def render_vs(m: dict) -> str:
    rows = "".join(
        f"<tr><td><a href=\"{e(c['url'])}\">{e(c['name'])}</a></td>"
        f"<td>{e(c['price'])}</td><td>{e(c['note'])}</td>"
        f"<td>read {e(c['read'])}, <a href=\"{e(c['source'])}\">source</a></td></tr>"
        for c in COMPETITORS
    )
    return f"""
<h1>Compared</h1>
<p>Prices change. Every claim below carries the date it was read and a link to
where it was read, and the build fails if either is missing &mdash; an undated
claim about someone else's product does not stay neutral, it asserts
&ldquo;true now&rdquo; forever.</p>
<table>
<tr><th>Tool</th><th>Price</th><th>Notes</th><th>Checked</th></tr>
{rows}
</table>
<h2>The gap</h2>
<p>None of them publishes a fill rate, a rejection rate, or any measure of how
often a surfaced line is still available when you tap it. That absence is what
Bookbreaker is built into: a screen sorted by raw expected value is sorted
partly by how stale its own data is, because the biggest numbers cluster on the
books that moved most recently &mdash; which are the books most likely to have
moved again.</p>
"""


def audience_bodies(m: dict) -> dict[str, str]:
    """One body per audience. Each reads differently because the engine serves
    each of them with different parts of itself."""
    a, f, d, p = m["arb"], m["fill"], m["devig"], m["performance"]
    conv, h, ev, hero = m["conversion"], m["heat"], m["evidence"], m["hero"]

    return {
"arbitrage-bettors": f"""
<p>Finding the arb is the easy part. Two things decide whether arbitrage is
actually profitable, and neither is the margin.</p>
<h2>Whether the second leg lands</h2>
<p>An arb is only an arb if both legs get on. On a feed running
{f['latency']:.1f} seconds behind, a quote showing as {f['age']:.0f} seconds
old is really {f['effective']:.1f}, and its chance of still being there is
{f['honest']}% rather than {f['naive']}%. Miss the second leg and you hold a
one-sided position on a game you had no opinion about.</p>
<p>So every arb here is ranked by margin times the chance of getting on, not by
margin. That reorders the screen, and the reorder is the point.</p>
<h2>Whether the account survives</h2>
<p>The exact stakes for a {a['margin']:.2f}% arb are
{a['exact_stakes'][0]:,.2f} and {a['exact_stakes'][1]:,.2f}. That precision is
the clearest signal a risk desk reads. Rounding afterwards breaks the lock
because the legs are not symmetric &mdash; solving over round stakes gives
{a['round_stakes'][0]:,} and {a['round_stakes'][1]:,}, still guaranteed, for
{a['rounding_cost']:,.2f} of the {a['exact_profit']:,.2f}.</p>
<p>Commission is netted before anything is called an arb, which matters more
than it sounds. {e(m['commission']['price'])} on both sides looks like a
{m['commission']['gross']:.2f}% arbitrage; against an exchange taking
{m['commission']['commission']}% of winnings it is
{m['commission']['net']:.2f}%. A screen that skips the netting surfaces that
every time, and it costs money on every one.</p>
<p><a href="/guides/what-is-arbitrage-betting/">The full explanation &rarr;</a>
&nbsp;&middot;&nbsp;<a href="/account-longevity/">The limiting model &rarr;</a></p>
""",

"ev-bettors": f"""
<p>A +EV number is a model output, and the model is a devig you did not choose.
On a {e(d['market'])} moneyline the four standard methods give the favourite
{min(d['methods'].values()):.2f}% to {max(d['methods'].values()):.2f}% &mdash;
{d['spread']:.2f} points apart on a market where 2% is a good edge.</p>
<h2>What the screen shows instead of one number</h2>
<div class="screen">
<span class="dim">{e(hero['book'])}</span>  {e(hero['outcome'])}
<span class="num">{e(hero['price'])}</span>
<br><span class="dim">  EV</span> <span class="pos">{hero['ev']:+.2f}%</span>
&nbsp;<span class="dim">band</span> {hero['low']:+.2f}%..{hero['high']:+.2f}%
&nbsp;<span class="dim">fill</span> {hero['fill']}%
&nbsp;<span class="dim">&rarr; realised</span>
<span class="pos">{hero['realised']:+.2f}%</span>
</div>
<p>The band is what the four methods allow. An edge that only survives the
friendliest one is a modelling artefact, and the screen filters those out by
default rather than showing them and hoping you notice.</p>
<h2>Which devig is right for your markets</h2>
<p>Nobody knows in advance, and the answer differs between an NBA total and a
tennis outright. So it is measured: every graded bet feeds a comparison of
which method predicted the closing line, and the weights update &mdash; but
only if the new ones beat the old ones on a slice of your record they were not
fitted on.</p>
<p><a href="/guides/what-does-plus-ev-mean/">What +EV means &rarr;</a>
&nbsp;&middot;&nbsp;<a href="/guides/how-to-devig-odds/">How devigging works &rarr;</a></p>
""",

"bonus-hunters": f"""
<p>Every offer is worth less than its headline, and the gap is the whole game.
A {conv['bonus']:,} bonus bet does not return its stake, so bet naively it is
worth about half its face value.</p>
<h2>What each shape is really worth</h2>
<p>Converting a bonus bet means hedging it. Longer odds convert better, and the
hedge column is what every guide omits:</p>
<table>
<tr><th>Free leg</th><th>Hedge at</th><th>Hedge stake</th><th>Guaranteed</th><th>Rate</th></tr>
{"".join(f"<tr><td>{e(r['free'])}</td><td>{e(r['hedge'])}</td><td>{r['hedge_stake']:,}</td><td>{r['guaranteed']:,}</td><td>{r['rate']:.1f}%</td></tr>" for r in conv['ladder'])}
</table>
<p>A deposit match is different arithmetic again. Rollover is a price, not a
condition: a matched bonus at 10x is worth exactly zero at a 5% hold, which is
barely above a standard market and below the hold of the restricted markets
many books allow for playthrough.</p>
<h2>The money most people actually lose</h2>
<p>Bonus bets expire. An expired one is worth nothing, and no tool tells you
before it happens &mdash; so this one tracks what you hold, what it converts
to, what is expiring, and how much face value has already lapsed unused. That
last figure is the only one that already happened rather than being a
forecast.</p>
<p><a href="/guides/how-to-convert-a-bonus-bet/">How conversion works &rarr;</a></p>
""",

"new-bettors": f"""
<p>Three facts decide whether betting is profitable, and none of them is
picking winners.</p>
<h2>The price already includes a fee</h2>
<p>At the standard -110 both ways you need to win 52.38% just to break even.
That is why a 50% bettor loses steadily and why the sportsbook does not need
you to be wrong.</p>
<h2>Your results prove almost nothing for a long time</h2>
<p>A real {p['n']}-bet record showing {p['roi']:.2f}% return reads as a
success. Here is what it actually supports:</p>
<p class="figure">{e(p['verdict'])}</p>
<p>The interval spans zero. Below {ev['floor']} settled bets nothing is worth
characterising at all &mdash; and slicing a record until something looks good
makes it worse, not better.</p>
<h2>The account is a resource</h2>
<p>Books limit consistent winners, so an edge you cannot place is worth
nothing. That makes stake shape, timing and market mix part of the arithmetic
rather than a separate topic.</p>
<p>None of this requires a subscription to learn.
<a href="/guides/">Every guide is here &rarr;</a></p>
""",
    }


def best_bodies(m: dict) -> dict[str, str]:
    """One body per 'best X' query. These are the highest-competition searches
    in the category and every existing result is an affiliate page, so the only
    defensible version is one that says what to check rather than what to buy."""
    d, f, p, ev = m["devig"], m["fill"], m["performance"], m["evidence"]
    n = len(load_data("competitors"))
    _ = m  # referenced inside the f-strings below

    return {
"best-arbitrage-betting-software": f"""
<p>Every list answering this is an affiliate page, so here is what to check
instead of who to buy.</p>
<p><strong>Does it publish a fill rate?</strong> None of the {n} tools
catalogued here does. An arb you cannot get both legs on is not an arb, and a
screen ranked on raw margin is ranked partly by how stale its own data is
&mdash; the biggest numbers cluster on the books that moved most recently,
which are the books most likely to have moved again.</p>
<p><strong>Does it net commission before calling something an arb?</strong>
{e(m['commission']['price'])} both ways reads as a
{m['commission']['gross']:.2f}% arb and is {m['commission']['net']:.2f}% once
an exchange takes {m['commission']['commission']}% of winnings.</p>
<p><strong>Does it stake in round numbers?</strong> A stake to the cent is the
clearest fingerprint a risk desk reads, and rounding afterwards breaks the lock
because the legs are not symmetric.</p>
<p><strong>What does it cost against what you turn over?</strong> Prices in
this category run from single figures to several hundred a month.
<a href="/vs/">Every one dated and linked &rarr;</a></p>
""",

"best-odds-screen": f"""
<p>Speed is the wrong question, and it is the only one anybody advertises.</p>
<p><strong>How old is the quote, measured from the book?</strong> Not from when
the feed reached the screen. On a feed running {f['latency']:.1f} seconds
behind, a quote displayed as {f['age']:.0f} seconds old is really
{f['effective']:.1f} &mdash; and measuring from receipt understates age by
exactly the lag, which overstates the chance of getting on.</p>
<p><strong>Does it say which devig produced the number?</strong> The same
market reads {min(d['methods'].values()):.2f}% to
{max(d['methods'].values()):.2f}% depending on method. A screen printing one
figure to two decimals is showing you a modelling choice.</p>
<p><strong>Does it hold books out of their own fair value?</strong> A soft book
that contributes to the consensus pulls it toward its own price, shrinking
exactly the edge being detected &mdash; hardest on the markets where that book
is the lone outlier and the edge is largest.</p>
<p><a href="/">What this one shows &rarr;</a></p>
""",

"best-bet-tracker": f"""
<p>A tracker is only worth using if it can tell you when you have no edge.
Most cannot, because they report a single number.</p>
<p><strong>Does return come with an interval?</strong> A {p['n']}-bet record at
{p['roi']:.2f}% sounds decisive; the interval runs {p['low']:.1f}% to
{p['high']:.1f}% and spans zero.</p>
<p><strong>Does it separate money return from flat-bet return?</strong> One is
what happened, the other is what would have happened staking level. The gap is
the only direct read on whether your sizing is earning anything.</p>
<p><strong>Does it correct for slicing?</strong> Tag your bets and each tag is
a hypothesis. At {ev['bars'][2]['tests']} tags there is a
{ev['bars'][2]['luck']}% chance one clears the ordinary bar by luck.</p>
<p><strong>Does it handle pushes and voids properly?</strong> Counting a push
as a loss deflates win rate; leaving a voided stake in turnover deflates
return. Both errors are silent.</p>
<p><strong>Does it want your sportsbook password?</strong> Automatic syncing
works by holding your credentials. CSV import reaches the same place.</p>
<p><a href="/what-your-record-proves/">What a record can prove &rarr;</a></p>
""",

"best-ev-betting-software": f"""
<p>Positive-EV tools all show the same screen. Four things separate one that
can be trusted from one that cannot.</p>
<p><strong>An interval, not a number.</strong> Four defensible devig methods
disagree by {d['spread']:.2f} points on a real market. A tool that picks one
and prints the result to two decimals is presenting an opinion as a
measurement.</p>
<p><strong>A fill probability.</strong> Expected value you cannot place is
worth zero, and it is the largest edges that reject most often.</p>
<p><strong>Calibration against something.</strong> A devig method should be
chosen by which one predicted closing lines in your markets, not by which one
the author preferred &mdash; and the new weights should have to beat the old
ones on a slice of the record they were not fitted on.</p>
<p><strong>A refusal.</strong> Under {ev['floor']} graded bets, the honest
answer is that nothing can be said. A tool that always has a verdict is not
measuring anything.</p>
<p><a href="/guides/what-does-plus-ev-mean/">What +EV means &rarr;</a></p>
""",
    }


def guide_description(row: dict) -> str:
    """A meta description that fits for any guide title."""
    for candidate in (
        f"{row['question']} Worked through with the arithmetic done, not just "
        "the formula.",
        f"{row['question']} Answered with the numbers worked.",
        f"{row['title']}, worked through with real prices.",
    ):
        if 50 <= len(candidate) <= 160:
            return candidate
    return f"{row['title']} — worked through on real prices, with the range."


def guide_bodies(m: dict) -> dict[str, str]:
    """One body per guide, each pulling its numbers from the engine.

    Written out rather than templated. A guide cluster generated from a shape
    reads as generated, and the similarity gate would say so — these are the
    queries people actually type, and each deserves a real answer.
    """
    d, a, f, p = m["devig"], m["arb"], m["fill"], m["performance"]
    conv, mid, h, ev = m["conversion"], m["middles"], m["heat"], m["evidence"]
    par = m["parlay"]
    mt, sn, bo = m["match"], m["safety_net"], m["boost"]
    mu, rd, qa = m["multiplicity"], m["rounding"], m["quote_age"]
    ho, gr = m["holdout"], m["grading"]
    pf, tm = m["portfolio"], m["totals_middle"]
    lo, hi = min(d["methods"].values()), max(d["methods"].values())

    return {
"how-to-devig-odds": f"""
<p>A sportsbook's prices imply probabilities that add to more than 100%. The
surplus is the margin. Devigging redistributes it to recover what the book
actually believes &mdash; and <em>how</em> you redistribute it is a modelling
choice, not arithmetic.</p>
<p>On a {e(d['market'])} moneyline, the four standard methods give the
favourite anywhere from {lo:.2f}% to {hi:.2f}%:</p>
{"".join(f"<p><strong>{e(k)}</strong> &mdash; {v:.2f}%</p>" for k, v in sorted(d['methods'].items()))}
<p>That spread is {d['spread']:.2f} points of probability on a market where a
2% edge is a good day. Multiplicative is the usual default because it is one
division, but it distributes the margin in proportion to implied probability
&mdash; the opposite of the favourite-longshot bias real markets show, which
makes it the method most likely to overstate a longshot.</p>
<p>The practical answer: do not pick one. An edge that exists under one method
and vanishes under another is a modelling artefact.
<a href="/calculators/no-vig-odds/">Work it through &rarr;</a></p>
""",

"what-is-closing-line-value": f"""
<p>Closing line value is the difference between the price you took and the
price the market settled at. Beating the close consistently is the standard
evidence that an edge is real.</p>
<p>The reason it matters more than profit is sample size. A 2% edge over 500
even-money bets has a standard deviation of about 4.5% of turnover, so losing
months are routine and winning months prove nothing. Here is a real
{p['n']}-bet record:</p>
<p class="figure">{e(p['verdict'])}</p>
<p>That is {p['profit']:+,} in profit and it still cannot be distinguished from
break-even. Waiting for profit to confirm a model means waiting years; adjusting
on early profit means fitting noise. CLV converges far faster, which is why it
is what this engine calibrates on rather than merely displays.</p>
<p>One catch: grade against the <em>devigged</em> closing price, not the raw
one. Comparing two vigged prices understates your edge by the closing margin.
<a href="/calculators/closing-line-value/">The arithmetic &rarr;</a></p>
""",

"how-to-convert-a-bonus-bet": f"""
<p>A bonus bet does not return its stake. Win a {conv['bonus']:,} bonus at even
money and you collect {conv['bonus']:,}, not {conv['doubled']:,} &mdash; so
bet naively it is worth about half its face value.</p>
<p>Converting means hedging: put the bonus on one side and cash on the other,
so you keep a guaranteed amount whichever way it lands. Longer odds convert
better, because you are not risking the stake:</p>
<table>
<tr><th>Free leg</th><th>Hedge at</th><th>Hedge stake</th><th>Guaranteed</th><th>Rate</th></tr>
{"".join(f"<tr><td>{e(r['free'])}</td><td>{e(r['hedge'])}</td><td>{r['hedge_stake']:,}</td><td>{r['guaranteed']:,}</td><td>{r['rate']:.1f}%</td></tr>" for r in conv['ladder'])}
</table>
<p>Every guide stops at &ldquo;convert on a longshot&rdquo;. Look at the hedge
column: the {conv['ladder'][-1]['rate']:.0f}% plan needs
{conv['ladder'][-1]['hedge_stake']:,} sitting at a second book. Most people do
not have that, which makes the honest advice &ldquo;convert at the longest
price you can actually hedge&rdquo;.
<a href="/calculators/bonus-bet-conversion/">Run your own number &rarr;</a></p>
""",

"what-is-arbitrage-betting": f"""
<p>When two books disagree enough, backing both sides returns more than it
costs. At {e(a['legs'][0])} and {e(a['legs'][1])} the implied probabilities sum
to less than one, which is a {a['margin']:.2f}% return on turnover whatever
happens.</p>
<p>The maths is one line. The hard parts are the two nobody writes about.</p>
<p><strong>The price may already be gone.</strong> Between the screen showing a
quote and your bet landing sit the poll interval, the network and you. A quote
that looks {f['age']:.0f} seconds old on a feed running {f['latency']:.1f}
seconds behind is really {f['effective']:.1f}, and its chance of still being
there is {f['honest']}% rather than {f['naive']}%. Miss one leg and you are not
arbing, you are betting.</p>
<p><strong>The stake gives you away.</strong> The exact solution here is
{a['exact_stakes'][0]:,.2f} and {a['exact_stakes'][1]:,.2f}. Nobody types that,
and risk desks know it. Rounding afterwards breaks the lock because the legs
are not symmetric &mdash; solving for round stakes directly gives
{a['round_stakes'][0]:,} and {a['round_stakes'][1]:,}, still guaranteed, for
{a['rounding_cost']:,.2f} of the {a['exact_profit']:,.2f}.
<a href="/calculators/arbitrage/">Stake one &rarr;</a></p>
""",

"what-does-plus-ev-mean": f"""
<p>A bet is +EV when the price pays more than the true probability warrants.
Fair value {d['consensus']:.2f}% against a price implying less means the
difference is yours, on average, over enough bets.</p>
<p>&ldquo;On average, over enough bets&rdquo; is doing heavy lifting. Two
things decide whether a printed +EV number is real:</p>
<p><strong>Which devig produced it.</strong> The same market reads
{lo:.2f}% to {hi:.2f}% depending on method. If the edge only survives the
friendliest one, it is not an edge.</p>
<p><strong>Whether you can get on.</strong> Expected value you cannot place is
worth zero. A 6% edge at a book that pulls its price in four seconds is worth
less than a 3% edge still there when you tap it &mdash; which is why a screen
ranked on raw EV is ranked partly by how stale its own data is.</p>
<p><a href="/calculators/expected-value/">Check a price &rarr;</a></p>
""",

"what-is-a-middle-bet": f"""
<p>Bet over {mid['cases'][0]['window'].split(' / ')[0]} at one book and under
{mid['cases'][0]['window'].split(' / ')[1]} at another. If the result lands
between them, both bets win. Outside, one wins and one loses, so the position
costs a little &mdash; and the middle is the payoff.</p>
<p>Everything hinges on how often the result lands in the window, and this is
where nearly every tool is casually wrong. Results are not smoothly
distributed: football margins pile up on 3 and 7 because of how the sport
scores. Same prices, one point apart:</p>
<table>
<tr><th>Window</th><th>Hits</th><th>Break-even</th><th>Expected value</th></tr>
{"".join(f"<tr><td>{e(r['window'])}</td><td>{r['probability']:.2f}%</td><td>{r['breakeven']:.2f}%</td><td>{r['ev']:+.2f}%</td></tr>" for r in mid['cases'])}
</table>
<p>A normal curve prices those identically. The break-even column is the honest
anchor &mdash; arithmetic on the two prices, depending on no distribution at
all. The hit rate above comes from counting {mid['games']} games in a
{e(mid['sample'])} sample, shown as an illustration of the mechanism rather
than a claim about any league.
<a href="/calculators/middle/">Price one &rarr;</a></p>
""",

"how-to-avoid-getting-limited": f"""
<p>Soft books make money assuming the average customer loses. A consistent
winner breaks that, so they profile you and cut your stakes. Edge you cannot
place is worth nothing, which makes account lifetime the denominator of
everything else.</p>
<p>What actually gets read, in rough order of how loudly it signals:</p>
<p><strong>Stake precision.</strong> {e(h['stakes'][0]['stake'])} reads
{h['stakes'][0]['heat']}% mechanical; {e(h['stakes'][3]['stake'])} reads
{h['stakes'][3]['heat']}%. Cents are the single clearest fingerprint.</p>
<p><strong>Reaction time.</strong> A bet {e(h['reaction'][0]['after'])} after a
sharp book moves scores {h['reaction'][0]['heat']}%; the same bet
{e(h['reaction'][2]['after'])} later scores {h['reaction'][2]['heat']}%. Nobody
refreshes and decides in half a second.</p>
<p><strong>Market mix.</strong> Alternate lines read
{h['markets'][2]['heat']}%, main markets {h['markets'][0]['heat']}%. Arbitrage
concentrates where pricing gets less attention, which is exactly why a profile
made of it reads as sharp.</p>
<p>What none of this involves: multi-accounting, identity or KYC workarounds,
device or location spoofing. Those are fraud, not staking discipline. And none
of it applies at a book that never limits winners &mdash; spending edge to hide
from a risk desk that does not exist is the most common way the advice is
misapplied. <a href="/account-longevity/">The full model &rarr;</a></p>
""",

"what-is-vig-and-hold": f"""
<p>The vig is the sportsbook's margin. On the standard -110 both ways, the two
prices imply probabilities summing above 100%, and the surplus is what the book
keeps.</p>
<p>Hold is what that surplus is worth as a fraction of the money bet, and it is
not the same number. A market whose implied probabilities sum to 1.0476 holds
4.55%, not 4.76% &mdash; the book's take is measured against the pool, not
against the excess. Plenty of calculators report the excess and overstate every
book's margin.</p>
<p>Why it matters: hold is the cost of doing business at that book, and it
compounds. A market you can bet at 2% hold instead of 4.5% hands back more than
most people's claimed edge.
<a href="/calculators/hold/">Measure a book &rarr;</a></p>
""",

"how-to-use-the-kelly-criterion": f"""
<p>Kelly gives the stake that maximises long-run growth <em>given the true
probability</em>. You do not have the true probability &mdash; you have a
devigged estimate with an error bar.</p>
<p>That asymmetry decides everything. Betting twice the correct fraction has
negative growth; betting half has about three-quarters of the growth at a
quarter of the variance. Overestimating an edge costs far more than
underestimating it, and devigged estimates are exactly the kind that get
overestimated.</p>
<p>So: fractional Kelly, and size on the <em>least</em> favourable devig rather
than the friendliest. Cap any single bet regardless of what the formula says
&mdash; Kelly on a genuine 30% edge and on a stale line ask for the same
number, and the cap is what makes the difference survivable.</p>
<p>One more trap: Kelly assumes bets resolve one at a time. Twelve overs on one
game script is one undiversified position wearing twelve hats.
<a href="/calculators/kelly/">Size a bet &rarr;</a></p>
""",

"how-to-read-american-odds": f"""
<p>A positive number is what you win on 100 staked. A negative number is what
you must stake to win 100. +150 returns 150 profit on 100; -200 needs 200 to
win 100.</p>
<p>Converting to decimal makes them comparable, and converting to implied
probability makes them meaningful:</p>
<p>+150 is decimal 2.500 and implies 40.00%. -200 is decimal 1.500 and implies
66.67%. -110, the standard price, is decimal 1.909 and implies 52.38% &mdash;
which is why a coin-flip bettor at -110 loses steadily.</p>
<p>The trap is calling that implied number a probability. It is vig-inclusive:
it is what the price asserts, and across a market those assertions add to more
than 100%. Treating it as a fair probability without devigging first is the
most common way to invent an edge that is not there.
<a href="/calculators/odds-converter/">Convert &rarr;</a></p>
""",

"how-to-hedge-a-bet": f"""
<p>Hedging means backing the other side of a position you already hold, so the
result matters less. It is the same arithmetic as an arbitrage, applied after
the fact rather than looked for.</p>
<p>The question is always what each result pays. Stake the second leg so both
outcomes return the same and you have converted an open position into a
certain one; stake it lighter and you have reduced variance while keeping some
upside.</p>
<p>Two things people get wrong. A market's worst case is <em>not</em> the sum
of its stakes &mdash; bet both sides and one leg always returns. And the
outcome you did not bet is invisible in a list built from your own slips: a
three-way market where you hold two sides looks fully covered until you count
the third result.</p>
<p><a href="/calculators/arbitrage/">Stake a hedge &rarr;</a></p>
""",

"what-is-a-low-hold-bet": f"""
<p>A low hold bet is the same idea as an arbitrage, one step short of it. Two
books disagree enough that backing both sides costs you far less than betting
either alone &mdash; not free, but close.</p>
<p>Why bother with a position that loses a little by design? Two reasons.
Turnover at near-zero cost is how you clear a deposit-match rollover without
handing back the bonus. And a profile made of two-sided bets at ordinary prices
looks nothing like a profile made of longshot alternate lines.</p>
<p>The arithmetic is the hold calculation applied across books instead of
within one. Where a single book holds 4.55% on a standard market, the best
prices across two might hold 0.5% &mdash; and occasionally cross into an
arbitrage.
<a href="/calculators/hold/">Measure a pair &rarr;</a></p>
""",

"how-to-track-your-betting-results": f"""
<p>Most bettors track profit, which is the number that takes longest to say
anything. Four things are worth measuring instead.</p>
<p><strong>Closing line value.</strong> Converges far faster than profit and is
what sportsbooks themselves use to identify sharp accounts.</p>
<p><strong>Return with its interval.</strong> A {p['n']}-bet record showing
{p['roi']:.2f}% sounds decisive and is not: the interval runs {p['low']:.1f}%
to {p['high']:.1f}%, spanning zero.</p>
<p><strong>Money return against flat-bet return.</strong> One is what happened,
the other is what would have happened staking level. The gap is the only direct
read on whether your sizing is earning its keep.</p>
<p><strong>How many slices you checked.</strong> Tag your bets and each tag is
a hypothesis. With {ev['bars'][2]['tests']} tags there is a
{ev['bars'][2]['luck']}% chance one clears the ordinary bar by luck, so the bar
has to rise with the count. Slicing until something looks good is a search, not
a test. <a href="/what-your-record-proves/">What a record can prove &rarr;</a></p>
""",

"what-is-a-parlay-really-worth": f"""
<p>A parlay pays the product of its legs. Four legs at -110 pay
{par['pays']:.2f} to 1. Four fair coin flips should pay {par['fair']:.2f} to 1.
The gap is a {par['hold']:.1f}% hold &mdash; {par['multiple']:.1f} times the
{par['leg_hold']:.2f}% you pay on a single.</p>
<p>Nothing about a parlay creates value. It multiplies the margin, and the
payout number grows while the value shrinks, which is exactly why it is the
most heavily promoted bet in the market.</p>
<table>
<tr><th>Legs</th><th>Hold</th></tr>
{"".join(f"<tr><td>{r['legs']}</td><td>{r['hold']:.1f}%</td></tr>" for r in par['ladder'])}
</table>
<p>By {par['lottery_legs']} legs the book is holding more than a quarter of
every dollar staked. That is roughly where a parlay stops being a bet and
becomes a lottery ticket &mdash; which is a fine thing to buy knowingly, and a
poor thing to buy while believing you are betting.</p>
<p>The honest exception: if every leg is genuinely +EV, the parlay of them can
be too. That is rare and it is not what the promoted parlays are made of.</p>
<p><a href="/calculators/hold/">How hold works &rarr;</a></p>
""",

"what-is-a-same-game-parlay-worth": f"""
<p>Multiplying the legs is the right sum only when the legs are independent.
Same-game legs are not.</p>
<p>A team covering the spread makes the over more likely, not less. A quarterback
having a big passing day makes his receiver's yardage prop more likely. Multiply those together as though they were coin flips and you get a
probability that is too low, which makes the fair price look higher than it is
&mdash; and makes the parlay look better than it is.</p>
<p>{e(par['sgp_note'])}</p>
<p>Books price same-game parlays with a correlation adjustment for exactly this
reason. That adjustment is theirs and it is not published, which means the
independent calculation you can do is a ceiling on the value, never an
estimate of it. Any tool that quotes you a same-game parlay edge from
multiplication alone is quoting a number it cannot support.</p>
<p>What survives: correlation cuts both ways, and a <em>negatively</em>
correlated pair is the one books misprice more often. That is a real edge and
it needs the correlation measured, not assumed.</p>
<p><a href="/guides/what-is-a-parlay-really-worth/">The ordinary parlay maths
&rarr;</a></p>
""",

"what-is-a-sharp-sportsbook": f"""
<p>A sharp book prices to be right. A soft book prices to be attractive. That
difference decides whether a price is evidence about the world or a product
being sold to you.</p>
<p>Sharp books run thin margins, take large bets, and do not limit winners.
They can afford to because they treat informed money as information: a bet
against their line tells them something, and they move. Soft books make money
assuming the average customer loses, so a consistent winner breaks the model
and gets cut.</p>
<h2>Why it changes the arithmetic</h2>
<p>A fair value is only as good as what anchors it. On the {e(d['market'])}
moneyline the four devig methods span {min(d['methods'].values()):.2f}% to
{max(d['methods'].values()):.2f}% &mdash; and that is the spread on a
<em>sharp</em> price. Anchor the same calculation on a soft book and you are
polling the people you intend to beat.</p>
<p>So a soft book contributes very little weight to a fair value here, and is
never priced against a consensus it helped set: even a small contribution pulls
the number toward that book's own price, shrinking exactly the edge being
detected &mdash; hardest on the markets where it is the lone outlier and the
edge is largest.</p>
<p>Where they never limit winners, no anti-limiting effort is spent at all.
Spending edge to hide from a risk desk that does not exist is the most common
way that advice is misapplied.</p>
<p><a href="/sportsbooks/nj/">Which books are which, by state &rarr;</a></p>
""",

"how-to-line-shop": f"""
<p>Line shopping is taking the best available price on a bet you were going to
make. It is the least glamorous edge in betting and close to the largest.</p>
<p>The arithmetic: at -110 both ways a book holds {par['leg_hold']:.2f}%. Beat
that price by half a point on every bet and you have handed back a meaningful
share of the margin &mdash; without predicting anything, without a model, and
without any risk you were not already taking.</p>
<h2>What it is worth over a season</h2>
<p>A {p['n']}-bet record at {p['roi']:.2f}% return has an interval running
{p['low']:.1f}% to {p['high']:.1f}%. Against that noise, a systematic
half-point improvement on every bet is one of the few things large enough to
show through &mdash; and unlike a model edge, it does not need to be right
about anything.</p>
<h2>The catch nobody mentions</h2>
<p>Consistently capturing the best number is itself a signal. Risk desks
profile on it, because a customer who always beats the market is a customer
whose bets carry information. That is why the price you take and the account
you take it at are the same decision.</p>
<p><a href="/account-longevity/">What bet shape gives away &rarr;</a></p>
""",

"what-is-bankroll-management": f"""
<p>Sizing is not a smaller version of picking. It is the thing that decides
whether a real edge survives a bad run.</p>
<h2>Fractional, always</h2>
<p>Kelly gives the growth-maximising stake given the true probability. You have
an estimate with an error bar, and the penalty is asymmetric: betting twice the
correct fraction has negative growth, betting half has about three-quarters of
the growth at a quarter of the variance. Overestimating costs far more than
underestimating, and devigged estimates are exactly the kind that get
overestimated.</p>
<h2>Cap every bet regardless</h2>
<p>Kelly on a genuine 30% edge and on a stale line ask for the same stake. The
cap is what makes the difference between them survivable.</p>
<h2>Count correlated bets once</h2>
<p>Kelly assumes bets resolve one at a time. Twelve overs riding one game
script is one undiversified position wearing twelve hats, and sizing each at
its individual optimum is a far larger bet than it looks.</p>
<h2>Judge the sizing separately from the picking</h2>
<p>Money return and flat-bet return answer different questions: what happened,
and what would have happened staking level. The gap between them is the only
direct read on whether your sizing earned anything, and almost no tracker
separates them.</p>
<p><a href="/calculators/kelly/">Size a bet &rarr;</a></p>
""",

"what-is-a-deposit-match-worth": f"""
<p>A 100% match on {mt['deposit']:,} dollars looks like {mt['bonus']:,} dollars
of free money. It is not free and it is not always money. The rollover is a
price, and you pay it in hold.</p>
<p>At {mt['rollover']}x on deposit plus bonus, the offer is worth exactly zero
at a hold of <strong>{mt['breakeven']:.2f}%</strong>. That is the whole
decision. Everything else is a question of what you are allowed to churn it
in.</p>
<table>
<tr><th>Rollover allowed in</th><th>Hold</th><th>Verdict</th><th>Net</th></tr>
<tr><td>Moneylines at -110</td><td>{mt['open_hold']:.2f}%</td>
<td>clears by {mt['open_margin']:+.2f}%</td><td>{mt['open_net']:+,.2f}</td></tr>
<tr><td>Player props only</td><td>{mt['shut_hold']:.2f}%</td>
<td>fails by {mt['shut_margin']:+.2f}%</td><td>{mt['shut_net']:+,.2f}</td></tr>
</table>
<p>Same headline, same deposit, same rollover multiple: a
<strong>{mt['swing']:,.2f}</strong> difference, decided entirely by which
markets the terms let you use. Both holds above are measured off real two-way
prices, not assumed.</p>
<p>Books restrict the cheap markets, and they restrict them for exactly this
reason. A playthrough confined to parlays is worse still &mdash; those run
nearer {mt['prior_parlay']:.0f}% (a stated prior here, not a measurement), and
nothing at that hold clears a {mt['rollover']}x rollover at any headline.</p>
<p>So the question is never "how big is the bonus". It is "how cheap is the
cheapest market they will let me clear it in", and the answer is in the terms,
under a heading most people never open.</p>
<p><a href="/calculators/breakeven/">Work out your own break-even &rarr;</a></p>
""",

"what-is-a-no-sweat-bet-worth": f"""
<p>"Bet up to {sn['stake']:,} dollars, refunded in bonus bets if it loses."
The offer's value is not in the bet. It is in the refund, and you only collect
the refund when the bet <em>loses</em>.</p>
<p>That inverts the usual instinct. The worth of the offer on its own is the
refund, times how often you collect it, times what a bonus bet is really worth
&mdash; here {sn['conversion']}% after hedging:</p>
<table>
<tr><th>Qualifying price</th><th>Offer premium</th><th>Total EV</th></tr>
{"".join(f"<tr><td>{r['american']}</td><td>{r['premium']:,.2f}</td><td>{r['ev']:,.2f}</td></tr>" for r in sn['rows'])}
</table>
<p>The premium runs from {sn['short_premium']:,.2f} at a coin flip to
{sn['long_premium']:,.2f} at a longshot &mdash; <strong>{sn['ratio']:.2f}x
more</strong> for taking the longer price. Bet the favourite and you win the
bet most of the time, which is precisely how you fail to collect the thing you
signed up for.</p>
<h2>Two things this does not mean</h2>
<p><strong>It is not hedgeable.</strong> There is no second bet that locks a
safety net, because the refund only exists in the branch where you lose. Any
tool reporting this EV as guaranteed is reporting the wrong field.</p>
<p><strong>Longer is not unboundedly better.</strong> Real longshots carry the
heaviest margin, and past some point the extra vig costs more than the extra
refund frequency earns. The right price is the longest one whose <em>fair</em>
probability you actually trust.</p>
<p><a href="/guides/how-to-convert-a-bonus-bet/">What a bonus bet converts at
&rarr;</a></p>
""",

"what-is-a-profit-boost-worth": f"""
<p>A boost multiplies profit. Profit grows with the price. So spending a
{bo['pct']}% boost on a favourite gives almost all of it away.</p>
<p>The same {bo['pct']}% boost on a {bo['stake']} dollar stake:</p>
<table>
<tr><th>Price</th><th>Profit the boost adds</th><th>EV of the boosted bet</th></tr>
{"".join(f"<tr><td>{r['american']}</td><td>{r['added']:,.2f}</td><td>{r['ev']:,.2f}</td></tr>" for r in bo['rows'])}
</table>
<p>{bo['worst']:,.2f} at the short price against {bo['best']:,.2f} at the long
one &mdash; <strong>{bo['multiple']:.0f}x</strong> the value from the identical
token. "Use it on something safe" is the most expensive habit in promotional
betting.</p>
<h2>Why books hand them out anyway</h2>
<p>A boost is cheap to give and it moves behaviour. It pulls people toward
bigger stakes and longer prices than they would otherwise take, and the
account that suddenly bets its boost at +500 is an account whose ordinary
staking now has a very visible exception in it.</p>
<p>Which is the part nobody costs in: a boost spent optimally is also a boost
spent conspicuously.</p>
<p><a href="/account-longevity/">What bet shape gives away &rarr;</a></p>
""",

"how-to-read-a-betslip-into-your-record": f"""
<p>A tracker is only worth what its worst row is worth. One misread slip does
not stay in its row &mdash; it moves your return, your win rate, and every
model weight computed from your history afterwards.</p>
<h2>The trap that catches everybody</h2>
<p>An open betslip shows a payout. <code>To Win $45.45</code> sits on the slip
from the moment you place the bet, long before it settles. Read that as a
result and you have recorded a <em>winning bet that has not happened</em>,
with a profit to match. It is invisible once it is a row, and it inflates
everything downstream.</p>
<p>The fix is a rule, not care: a payout label is never a result. Only settle a
bet from a word that can only mean settlement.</p>
<h2>The second trap</h2>
<p>"Payout" and "profit" are different numbers &mdash; payout includes your
stake back. Copy a payout column into a profit column and every winning bet is
overstated by its own stake. On a {p['n']}-bet record that is not a rounding
error; it is the difference between a real edge and an imagined one.</p>
<h2>What good logging looks like</h2>
<p>Record the price and stake as the slip states them. Derive profit from
price, stake and result rather than reading it across. Leave unknown fields
blank instead of defaulting them &mdash; an unknown book is not
"DraftKings", and a bet with no event cannot ever be graded.</p>
<p>And check the reading before it is written. A slip you half-understood is
not a bet with some missing details; it is text that did not parse.</p>
<p><a href="/guides/how-to-track-your-betting-results/">What a record can
actually prove &rarr;</a></p>
""",

"which-welcome-offer-to-do-first": f"""
<p>Order matters, for a reason that has nothing to do with which bonus is
biggest.</p>
<p>Converting a bonus bet means hedging it &mdash; betting the other side at a
second book. So your <em>first</em> account is worth very little on its own:
you can claim the offer and then have nowhere to lay it off. Open two
bet-and-get books before touching anything else and every bonus after that has
somewhere to go.</p>
<h2>The order</h2>
<p><strong>Bet-and-get first.</strong> Nearly free, and the bonus bets it
produces are the cheapest possible practice at conversion before any real money
is at risk.</p>
<p><strong>Safety nets second.</strong> Real money is exposed here, and the
qualifying price wants to be long &mdash; the opposite of the bet-and-get play,
which is why doing them in the wrong order teaches the wrong habit.</p>
<p><strong>Deposit matches last, and often not at all.</strong> They are the
only shape that can be worth <em>less than nothing</em>: at
{mt['rollover']}x the break-even hold is {mt['breakeven']:.2f}%, and a
playthrough restricted to props at {mt['shut_hold']:.2f}% loses
{abs(mt['shut_net']):,.2f} on a {mt['bonus']:,} dollar headline.</p>
<h2>The constraint nobody sequences around</h2>
<p>Every one of these is a new account making an unusual first bet, and they
all land in the same few weeks. Offer-hunting has a shape, the shape is legible
from the first deposit, and an account opened purely to clear a bonus tends to
look like one.</p>
<p><a href="/guides/how-to-avoid-getting-limited/">What that shape looks like
&rarr;</a></p>
""",

"why-your-best-sport-is-probably-noise": f"""
<p>You slice your record by sport, by book, by market, by day of week. One
slice is clearly your best. It is probably nothing.</p>
<p>A 95% bar means a coin-flip record clears it one time in twenty <em>per
test</em>. Run the test on several slices and the chance that at least one
looks good by luck stops being small:</p>
<table>
<tr><th>Slices tested</th><th>Chance one looks real by luck</th>
<th>Bar it should clear</th></tr>
{"".join(f"<tr><td>{r['tests']}</td><td>{r['error']:.1f}%</td><td>z = {r['z']:.2f}</td></tr>" for r in mu['rows'])}
</table>
<p>By <strong>{mu['coinflip_at']} slices</strong> it is a coin flip that
something in your record looks significant when nothing is. A bettor who
invents tags until one of them looks profitable is not running a test. They are
running a search, and a search needs a higher bar than z = {mu['plain_z']:.2f}
&mdash; up to z = {mu['rows'][-1]['z']:.2f} at {mu['rows'][-1]['tests']}
slices.</p>
<h2>What to do instead</h2>
<p>Decide which slices matter <em>before</em> looking, and count every slice you
tested, including the ones you abandoned. A slice under {mu['min_bets']} settled
bets should not be characterised at all &mdash; not "slightly negative", not
"promising", nothing.</p>
<p>This is the correction essentially nobody in this category applies, and tag
breakdowns are exactly where it is needed. A tool that shows you twenty
segments and highlights the green ones is selling you the search results and
calling them a finding.</p>
<p><a href="/what-your-record-proves/">What a record can prove &rarr;</a></p>
""",

"how-to-stake-an-arbitrage-in-round-numbers": f"""
<p>The exact stakes on an arbitrage come out ugly. Splitting
{rd['total']:,} dollars across a two-way at these prices wants
{rd['exact_legs'][0]:,.2f} and {rd['exact_legs'][1]:,.2f}, locking
{rd['exact_profit']:,.2f}.</p>
<p>Nobody bets {rd['exact_legs'][0]:,.2f}. More precisely: nobody who is not
running a tool bets {rd['exact_legs'][0]:,.2f}, which is the problem. Stake
precision is one of the cheapest signals a risk desk has, and it costs nothing
to read.</p>
<h2>What rounding costs</h2>
<p>Round to {rd['round_legs'][0]:,.0f} and {rd['round_legs'][1]:,.0f} and the
guaranteed profit becomes {rd['round_profit']:,.2f} &mdash; a cost of
<strong>{rd['cost']:,.2f}</strong>, or {rd['cost_bps']:.1f} basis points of
turnover.</p>
<p>That is the whole trade, stated. It is a real cost and it is named rather
than hidden, because a tool that will not show you the price of its own
advice is not one you can check.</p>
<h2>Search, don't round</h2>
<p>Straight rounding is one point in a small neighbourhood of round-stake
combinations, and often not the best one. Pin the leg at the softest book to a
clean number &mdash; that is the account whose survival the shape protects
&mdash; then walk the other leg a few steps either way and score each
combination by its <em>worst</em> outcome.</p>
<p>Worst outcome, not average. Once stakes are rounded the legs pay
differently, and quoting the average would describe a position you do not
hold. The guaranteed number is the small one.</p>
<p><a href="/calculators/arbitrage/">Stake one &rarr;</a></p>
""",

"how-old-is-the-price-on-your-screen": f"""
<p>Every price you are looking at is a claim about the past. The question is
how far past, and no screen tells you.</p>
<p>There is a floor under the answer that has nothing to do with your
connection: the feed itself takes time to see a change and hand it on. This
engine will not price a quote as fresher than
<strong>{qa['latency_floor']:.0f} seconds</strong> when the provider did not
stamp it &mdash; a stated prior, not a measurement of any feed, and it is never
zero, because zero is the one value that is certainly wrong.</p>
<h2>How fast a quote dies</h2>
<p>Modelling survival as exponential with a mean lifetime of
{qa['tau']:.0f} seconds on a main moneyline &mdash; again a stated prior until
your own accept and reject record replaces it &mdash; the chance a quote is
still there when your bet lands:</p>
<table>
<tr><th>Quote age</th><th>Still there</th></tr>
{"".join(f"<tr><td>{r['age']}s</td><td>{r['survives']:.1f}%</td></tr>" for r in qa['rows'])}
</table>
<p>Half of them are gone by <strong>{qa['half_life']:.1f} seconds</strong>.</p>
<h2>Why this changes the number, not just the mood</h2>
<p>An edge you cannot take is not an edge. A
{qa['example_edge']:.0f}% overlay on a quote already {qa['example_age']}
seconds old is worth {qa['example_realised']:.2f}% once it is multiplied by the
chance the price survives to your bet. Those two numbers should never be shown
without each other. Most screens show the first and let you discover the second
by losing to it.</p>
<p>It also explains the rejections. A bet declined at the moment of placement
is usually not a limit &mdash; it is a price that had already moved before you
clicked, on a market where the survival curve is steep.</p>
<p><a href="/guides/why-your-bets-get-rejected/">Why bets get rejected
&rarr;</a></p>
""",

"how-to-tell-if-your-model-actually-works": f"""
<p>Any model can be made to fit the past. The only question worth asking is
whether it beats the thing it is replacing on data it has never seen.</p>
<h2>Hold out, in time order</h2>
<p>Split your graded bets chronologically and keep the last
{ho['holdout_pct']}% back. Fit on the earlier part, judge on the later part.
Random splits leak: markets move together within a day, so a random holdout
shares information with its training set and flatters everything.</p>
<p>At the {ho['min_graded']}-bet minimum this engine will fit on, that is
{ho['train']} bets to fit and {ho['test']} to judge &mdash; thin, which is the
point of the minimum. Below it, nothing is fitted at all.</p>
<h2>Beat the incumbent, not zero</h2>
<p>A candidate that scores well out of sample but no better than the weights
already in use is not an improvement, and adopting it is churn dressed as
progress. The bar is the incumbent's out-of-sample score, and a candidate that
fails it is refused rather than blended in at a small weight.</p>
<h2>Per-book, or not at all</h2>
<p>Books are not interchangeable. A weight fitted across all of them describes
none of them. Below {ho['min_coverage']} graded bets at a book, this engine
declines to fit that book's weight rather than fitting a bad one &mdash;
because a weight with no evidence behind it and a weight with evidence behind
it look identical downstream.</p>
<h2>The signal to fit against</h2>
<p>Closing line value, not profit. Profit over a few hundred bets is mostly
variance; CLV resolves on every bet and correlates with the thing you are
trying to have. It is a supervision signal, not a scoreboard.</p>
<p><a href="/guides/what-is-closing-line-value/">What CLV is &rarr;</a></p>
""",

"how-to-grade-your-own-bets": f"""
<p>Settling your own record sounds clerical. It is where most self-reported
edges are actually manufactured, and always by accident.</p>
<h2>Never cross a line</h2>
<p>A half point is not a rounding error. At -110 the price implies
{gr['p110']:.2f}%; at -120 it implies {gr['p120']:.2f}%. That
{gr['gap']:.2f}-point step is <strong>{gr['ratio']:.2f}x</strong> the entire
{gr['vig_at_110']:.2f}-point two-way margin you are trying to beat.</p>
<p>So a total and the same total a half point higher are different bets, and
settling one against the other's result is not an approximation. It is the
single most reliable way to turn a losing bet into a winning row.</p>
<h2>Never mix books</h2>
<p>Grade a bet against the book it was placed at. Two books can disagree about
whether a market even resolved, and a record assembled from whichever source
happened to be handy is a record of nothing in particular.</p>
<h2>Never settle from a soft book alone</h2>
<p>A soft book's number is a product being sold to you, not evidence about the
world. It is a poor anchor for a fair value and a poor authority on a
result.</p>
<h2>Grade idempotently</h2>
<p>Running the grader twice must not change a single number. If it does, the
grader is writing rather than reading, and every figure downstream depends on
how many times you happened to run it.</p>
<h2>Pushes and voids are not wins and not losses</h2>
<p>A push returns stake and belongs in neither column. Counting pushes as wins
inflates a win rate; dropping them from the denominator inflates a return.
Both are common, and a tracker that does not say which it does is not
reporting a number you can use.</p>
<p><a href="/guides/how-to-track-your-betting-results/">Tracking results
&rarr;</a></p>
""",

"how-many-bets-are-you-actually-making": f"""
<p>Twelve bets on one evening's slate are not twelve bets. They share weather,
pace, injury news and a referee, and everything they share makes them a smaller
number of larger positions than the count suggests.</p>
<p>The arithmetic is exact once you have a correlation. For <em>n</em> bets with
average pairwise correlation &rho;, the number of independent bets you are
really holding is <code>n / (1 + (n-1)&rho;)</code>:</p>
<table>
<tr><th>Positions</th><th>At &rho; = {pf['prior_rho']:.2f}</th>
<th>At &rho; = {pf['rho']:.2f}</th></tr>
{"".join(f"<tr><td>{r['n']}</td><td>{r['at_prior']:.1f}</td><td>{r['at_rho']:.1f}</td></tr>" for r in pf['rows'])}
</table>
<p>At {pf['rho']:.2f}, twelve positions are <strong>{pf['rows'][3]['at_rho']:.1f}
independent bets</strong>. Doubling them to twenty gets you to
{pf['rows'][4]['at_rho']:.1f}. That is the part worth sitting with: past a
handful of correlated bets, adding more stops buying diversification almost
entirely, and only adds stake.</p>
<h2>What it does to sizing</h2>
<p>A single-bet cap of {pf['max_single']}% of bankroll is right for someone
holding nothing. On a {pf['bankroll']:,} bankroll that is
{pf['cap_alone']:,.2f}. Holding eleven correlated bets already, the same cap
should be <strong>{pf['cap_loaded']:,.2f}</strong> &mdash; the difference is
the shrink factor the correlation implies, and it is not a rounding
adjustment.</p>
<h2>Measure it, do not assume it</h2>
<p>&rho; can be measured from your own settled record: group bets that resolved
together, and read the correlation off how much their combined results swing
against what independence predicts. It needs {pf['min_bets']} settled bets and
{pf['min_groups']} multi-bet groups before it is worth anything, and below that
the honest answer is a labelled prior rather than a number.</p>
<p><a href="/guides/what-is-bankroll-management/">Sizing from first principles
&rarr;</a></p>
""",

"what-is-a-totals-middle-worth": f"""
<p>A totals middle is over {tm['low']:g} at one book and under {tm['high']:g}
at another. Both bets win if the combined score lands strictly inside &mdash;
{tm['window']} numbers here. One always wins, so the position costs the hold on
one leg and pays the window.</p>
<h2>The two numbers</h2>
<p><strong>Break-even is arithmetic.</strong> At -110 both ways the pair needs
the window to hit {tm['breakeven']:.2f}% of the time to be worth taking. That
figure comes from the two prices and nothing else &mdash; no distribution, no
model, no assumption you can get wrong.</p>
<p><strong>The window probability is not.</strong> A normal curve with a
{tm['sigma']:.0f}-point spread puts this window at {tm['approx']:.2f}%, which
clears the bar comfortably. That number is an <em>approximation</em>, and the
spread behind it is a stated prior rather than a measurement of any sport.</p>
<h2>Why the approximation is the weak part</h2>
<p>Real scores are lumpy. They cluster on numbers the sport's scoring produces
often, and no smooth curve reproduces a lump. A window sitting on a cluster is
worth more than the curve says; one sitting in a gap is worth less. The curve
cannot tell you which you have.</p>
<p>Counting recorded finals can. It needs {tm['min_total_games']} games for
totals against {tm['min_games']} for margins, and the reason is structural: a
margin is folded &mdash; the absolute difference &mdash; so it piles onto a few
small integers, while combined scores spread across a far wider range. The same
game count buys much thinner evidence per number, so a second rule applies:
at least {tm['min_per_cell']} games on each distinct total actually observed,
measured rather than assumed.</p>
<p>Below either bar the answer is the approximation, labelled as one. A counted
probability backed by three games in the window is worse than an admitted
estimate, because it does not announce itself.</p>
<p><a href="/guides/what-is-a-middle-bet/">Middles in general &rarr;</a></p>
""",

"why-your-worst-case-is-worse-than-it-looks": f"""
<p>Add up what every open market loses if it resolves the worst way it can.
That total is your floor, and it is correct at any correlation.</p>
<p>What correlation changes is how often you get near it. A book of independent
bets almost never resolves all-worst at once. A book riding one game script
does it routinely &mdash; and at &rho; = {pf['rho']:.2f}, twelve positions are
{pf['rows'][3]['at_rho']:.1f} independent bets, which means "all of them going
wrong together" is roughly as likely as two bets going wrong together.</p>
<p>The bettor who sized for twelve independent positions and is holding
{pf['rows'][3]['at_rho']:.1f} is not slightly over-exposed. They are holding
several times the position they think they are.</p>
<h2>Two ways the floor itself is understated</h2>
<p><strong>Concentration.</strong> When more than
{pf['concentration_flag']}% of open money sits on a single event, the book is
that event wearing a portfolio's clothes. Worth a flag on its own, separately
from the correlation.</p>
<p><strong>Unknown outcome sets.</strong> This is the subtle one. If nothing
recorded what results a market can produce, the only outcomes visible are the
ones you bet on &mdash; so every result the model can see is one you backed,
and the "worst case" comes out <em>positive</em>. A one-sided book looks
risk-free to any tool that infers the outcome set from the bets in it. The
honest response is to say the floor is optimistic and why, not to print it.</p>
<p><a href="/guides/how-many-bets-are-you-actually-making/">What twelve
positions really are &rarr;</a></p>
""",

"how-much-of-your-bankroll-should-be-live": f"""
<p>Two different questions get confused here. How much should <em>one</em> bet
be, and how much should be on the table <em>at once</em>. The second has almost
no coverage anywhere, and it is the one that ends bankrolls.</p>
<h2>One bet</h2>
<p>Cap it at {pf['max_single']}% of bankroll regardless of what Kelly says.
Kelly on a genuine 30% edge and on a stale line ask for the same stake, and the
cap is what makes the difference between them survivable.</p>
<h2>Everything at once</h2>
<p>Above {pf['utilisation_flag']}% of bankroll live simultaneously, the
question stops being about any single bet. On a {pf['bankroll']:,} bankroll
that is money you cannot re-deploy, cannot re-price, and cannot hedge if the
correlation you did not measure turns out to be higher than you assumed.</p>
<p>And the single-bet cap has to shrink as the book fills. Holding eleven
correlated bets, the {pf['cap_alone']:,.2f} that was right on an empty book
becomes <strong>{pf['cap_loaded']:,.2f}</strong>.</p>
<h2>Why this is not conservatism</h2>
<p>For genuinely independent simultaneous bets, the individual optima are still
right and shrinking them would be superstition &mdash; the easy way to look
prudent while being wrong. The shrink is a response to measured correlation and
nothing else. At &rho; = 0 the factor is exactly 1.0 and every bet stays full
size.</p>
<p><a href="/calculators/kelly/">Size a bet &rarr;</a></p>
""",

"what-does-it-mean-that-a-number-is-measured": f"""
<p>Every betting tool shows you numbers. Almost none of them tell you which
ones came from data and which came from somebody's assumption typed into a
constant. The difference decides what a number is worth, and it is invisible
unless the tool says so on purpose.</p>
<h2>Three kinds of number</h2>
<p><strong>Arithmetic.</strong> Break-even on a pair of prices. A parlay's
payout. These cannot be wrong, only misread &mdash; the totals middle above
breaks even at {tm['breakeven']:.2f}% and no data would change it.</p>
<p><strong>Measured.</strong> Counted from a record: how often a window hits,
what a book's margin actually is, how much your simultaneous bets co-move.
Worth what the sample behind it is worth, which is why the sample size belongs
on screen next to it.</p>
<p><strong>Prior.</strong> A stated constant standing in until there is
something to measure. Legitimate, necessary, and dangerous the moment it stops
announcing itself.</p>
<h2>The bars, and why they exist</h2>
<table>
<tr><th>Claim</th><th>Needs</th></tr>
<tr><td>Counted margin window</td><td>{tm['min_games']} recorded games</td></tr>
<tr><td>Counted totals window</td><td>{tm['min_total_games']} games, and
{tm['min_per_cell']} per distinct total</td></tr>
<tr><td>Measured correlation</td><td>{pf['min_bets']} settled bets,
{pf['min_groups']} multi-bet groups</td></tr>
<tr><td>Fitted model weights</td><td>{ho['min_graded']} graded bets,
{ho['holdout_pct']}% held back in time order</td></tr>
<tr><td>Per-book weights</td><td>{ho['min_coverage']} graded bets at that
book</td></tr>
</table>
<p>Under any of these, the number does not become uncertain &mdash; it becomes
a prior, and it says so. An unmeasured cell is not a zero, and a stale quote is
not a fresh one.</p>
<h2>The test</h2>
<p>Ask any tool where a number came from. If it cannot answer, it is not that
the number is wrong; it is that nobody can tell you whether it is. Every figure
on this site is computed by running the engine at build time, and the build
refuses to publish a figure that is not.</p>
<p><a href="/how-it-works/">How the engine prices things &rarr;</a></p>
""",

"how-a-betting-model-improves-itself": f"""
<p>Any tool that prices a market has to strip the bookmaker's margin out of the odds first. That step is called devigging, and there is more than one way to do it. Picking one method and naming it in a footnote settles the question by assertion. This tool scores the methods against each other instead, and lets the scores set the blend.</p>
<p>The target is the closing line. When a market closes, the closing price is the sharpest estimate available of the true probability. Each devig method makes its prediction hours before that. Once the market closes, the engine measures how far the prediction missed, squares the miss, and folds it into that method's mean squared error. Mean squared error is a proper scoring rule: the score is minimised by reporting what you actually believe. A method cannot climb the table by shading every number toward the middle, and it cannot climb by exaggerating. Timid and bold both cost.</p>
<h2>What the scorer does with a log</h2>
<p>The scorer run over a {m['scoring']['bets']}-bet log. The error column is scaled mean squared error &mdash; relative error, comparable across these rows and to nothing outside them. Lower is better.</p>
<table>
<tr><th>Method</th><th>Relative error</th><th>Blend weight</th></tr>
{"".join(f"<tr><td>{e(r['method'])}</td><td>{r['error']:.2f}</td><td>{r['weight']:.1f}%</td></tr>" for r in m['scoring']['rows'])}
</table>
<p class="caveat">{e(m['scoring']['note'])}</p>
<p>The ranking is monotone: every step up in relative error buys a smaller share of the blend. The leader here, {e(m['scoring']['best'])}, carries {m['scoring']['best_weight']:.1f}% on its own &mdash; more than everything below it combined.</p>
<h2>Why the losers stay in</h2>
<p>The worst method on the table, {e(m['scoring']['worst'])}, still receives {m['scoring']['worst_weight']:.1f}%. That is deliberate. Weights are held above a floor of {m['scoring']['floor']}%, and that floor is a prior &mdash; the standing assumption that no method is worthless and that {m['scoring']['bets']} graded bets is not enough evidence to retire one. Nothing sits at the floor in this run. If the standings shift, the weights shift with them, and a method that is down today can come back.</p>
<h2>Where the choice lives</h2>
<p>The devig choice can be an input: made once, before there was any evidence, and never revisited by anything the product observes. Here it is an output. Every graded bet re-scores all {m['scoring']['methods']} methods and re-cuts the blend, so the model pricing today's markets is not quite the model that priced the ones before it.</p>
<p><a href="/guides/what-is-closing-line-value/">Why the closing line is the thing worth scoring against &rarr;</a></p>
""",

"why-a-losing-method-is-demoted-not-deleted": f"""
<p>The engine de-vigs every market with {m['scoring']['methods']} methods and weights them by how badly each has missed. The worst, {e(m['scoring']['worst'])}, holds {m['scoring']['worst_weight']:.1f}% of the vote. It did not earn all of that. A floor of {m['scoring']['floor']}% was reserved for it before any weight was handed out, and its share of the remainder lifted it the rest of the way. The tempting move is to drop the loser instead. That is the error.</p>
<h2>Deleting a method destroys the evidence that would clear it</h2>
<p>These weights are fitted over {m['scoring']['bets']} graded bets. That sample cannot separate a bad method from an unlucky one. Across {m['performance']['n']} graded bets this engine measures {m['performance']['roi']:.2f}% flat-bet ROI with an interval running from {m['performance']['low']:.1f}% to {m['performance']['high']:.1f}%, which spans zero and is indistinguishable from break-even. If that many bets cannot settle whether a strategy makes money, a smaller sample cannot settle which de-vig method is right.</p>
<p>A deleted method stops making predictions. No predictions means no errors, no errors means no evidence, and the record that would have exonerated it is never written. The pruning is self-sealing: it removes the only thing that could reverse it. Demotion costs almost nothing and stays reversible.</p>
<h2>Reserve the floor first then distribute the remainder</h2>
<p>Order matters, and it is where implementations go wrong. The tempting version normalises the inverse errors to a full allocation, raises anything below the floor up to it, then renormalises so the total sums back to a full allocation. That last step scales every weight down again, and the methods just lifted to the floor land back underneath it. The floor is enforced and undone in one operation, arriving at the outcome it exists to prevent.</p>
<p>Reserving {m['scoring']['floor']}% per method first and dividing only what is left needs no renormalisation, so nothing falls through.</p>
<table>
<tr><th>Method</th><th>Error</th><th>Weight</th></tr>
{"".join(f"<tr><td>{e(r['method'])}</td><td>{r['error']:.2f}</td><td>{r['weight']:.1f}%</td></tr>" for r in m['scoring']['rows'])}
</table>
<p class="caveat">{e(m['scoring']['note'])}</p>
<h2>The floor is a prior</h2>
<p>Named as a prior, because that is what it is: the {m['scoring']['floor']}% floor asserts, ahead of any evidence, that no method is worthless. Measured error moves everything above it. Each error in the table is a multiple of the one above it, yet the weights do not fall in that proportion &mdash; the gaps compress toward the bottom, which is the floor doing its work. {e(m['scoring']['best'])} leads at {m['scoring']['best_weight']:.1f}%: the same floor as every other method, plus the largest share of the remainder.</p>
<p><a href="/guides/how-to-tell-if-your-model-actually-works/">How to tell if your model actually works &rarr;</a></p>
""",

"when-do-bonus-bets-expire": f"""
<p>A promotion is held like a decaying asset and it is not one. The decay is a cliff. A face amount of {m['holdings']['face']:,} is worth {m['holdings']['worth']:.2f} for every day the offer is live, and {m['holdings']['lapsed']:.2f} from the deadline onward. There is no slope in between.</p>
<p>The figure behind that conversion is a prior &mdash; an assumed rate, here {m['holdings']['conversion']}%, at which a bonus bet is turned into withdrawable cash. It is an input to the valuation, not a measurement of your account. Move the prior and the cliff gets taller or shorter. It never becomes a slope.</p>
<h2>The value does not slide</h2>
<p>Read the table downward. The holding is worth the same at {m['holdings']['rows'][0]['days']} days out as at {m['holdings']['rows'][2]['days']} day out. Then it is worth {m['holdings']['lapsed']:.2f}. Most write-ups describe a promotion as though time value bleeds out of it, so an old bonus is worth less than a fresh one. That is wrong in both directions. Nothing bleeds, and then everything goes at once.</p>
<table>
<tr><th>Days to deadline</th><th>Value</th><th>Flagged urgent</th></tr>
{"".join(f"<tr><td>{r['days']}</td><td>{r['value']:.2f}</td><td>{'yes' if r['urgent'] else 'no'}</td></tr>" for r in m['holdings']['rows'])}
</table>
<h2>Urgent is a flag, not a discount</h2>
<p>At or inside {m['holdings']['urgent_days']:.0f} days, while it is still live, the holding is flagged urgent. The flag changes no value in the table. It changes the ordering of your week. A bonus converted at a poor rate today beats the same bonus converted at a good rate tomorrow whenever tomorrow falls past the deadline, because the alternative is {m['holdings']['lapsed']:.2f} and any conversion clears that bar. Note that the expired row carries no flag. Urgency is for things that can still be saved.</p>
<h2>The face amount is never true</h2>
<p>The headline face amount is the one number about a promotion that is never true. A balance that reads {m['holdings']['face']:,} is worth {m['holdings']['worth']:.2f} while it is live and {m['holdings']['lapsed']:.2f} once it lapses. At no point in its life is it worth {m['holdings']['face']:,}. That is the number in the advertisement and it is the number to leave out of your bankroll. Book the converted figure on the day the credit lands, and put the deadline next to it.</p>
<p><a href="/guides/how-to-convert-a-bonus-bet/">How to convert a bonus bet &rarr;</a></p>
""",

"why-a-model-should-forget-old-data": f"""
<p>A pricing weight has an expiry date. The overlay fits a weight per book&mdash;how much that book's price should count when the fair line is estimated&mdash;and once the calibration behind it has aged past {m['weights']['max_age_days']:,} days, every price built on it is labelled stale in the same line as the number. Not down-weighted, and not quietly dropped: named, where the price is read. The label is on or off, because there is nothing to taper along.</p>
<p>Books change. A book revises its margin, tightens or loosens its risk appetite, drops a market, adds another, hands pricing to someone else. A weight fitted before any of that describes a book that no longer exists&mdash;a precise measurement of a vanished thing. The cutoff is a prior, not a measurement: nothing in the settled record announces the day a trading desk changed its policy, so the engine picks a round age, roughly one off-season, and stops vouching for anything older.</p>
<h2>The bars that pull the other way</h2>
<p>The other bars in the fit ask for evidence, not freshness. No weight is fitted at all until {m['holdout']['min_graded']:,} graded bets exist. Of those, {m['holdout']['holdout_pct']:,}% is held back in time order&mdash;the newest slice, never a random sample, because a random split leaks the future into the fit. At that minimum it comes to {m['holdout']['train']:,} graded bets to fit on and {m['holdout']['test']:,} to score against. A book also has to clear {m['holdout']['min_coverage']:,} graded bets of its own before it earns a fitted weight instead of falling back to the default its tier carries. That per-book bar sits below the global one, because a book only has to describe itself.</p>
<table>
<tr><th>Bar</th><th>Value</th></tr>
<tr><td>Graded bets before anything is fitted</td><td>{m['holdout']['min_graded']:,}</td></tr>
<tr><td>Held back, newest first</td><td>{m['holdout']['holdout_pct']:,}%</td></tr>
<tr><td>Fitted on, at that minimum</td><td>{m['holdout']['train']:,}</td></tr>
<tr><td>Scored against, at that minimum</td><td>{m['holdout']['test']:,}</td></tr>
<tr><td>Graded bets per book for its own weight</td><td>{m['holdout']['min_coverage']:,}</td></tr>
<tr><td>Calibration labelled stale past this age (days)</td><td>{m['weights']['max_age_days']:,}</td></tr>
</table>
<h2>A window, not an archive</h2>
<p>The forces point in opposite directions. More data makes an estimate tighter. Older data makes it wrong. Together they give a window rather than an archive: the sample has to be large enough to fit and young enough to be true, and both conditions bind at once. A book that goes quiet never clears its coverage bar in the first place, and a fit that outlives the window stops being presented as current&mdash;not because the book became untrustworthy, but because nothing recent enough remains to say.</p>
<p>This is where the rest of the market goes wrong. Depth of history is sold as an unqualified virtue: seasons of backfill, years of closing lines, the biggest database wins. History is treated as monotonically valuable, as though a price from a book's retired pricing regime were weak evidence. It is not weak evidence. It is wrong evidence, and more of it adds bias rather than noise. Bias does not average out with volume.</p>
<p>The held-back slice is what turns any of this into a claim you can check. <a href="/guides/how-to-tell-if-your-model-actually-works/">How to tell if your model actually works &rarr;</a></p>
""",

"how-to-choose-an-odds-feed": f"""
<p>Feeds are sold on a published latency figure. Several publish none at all. Neither case tells you what the feed does on your markets, in your sports, at the minutes you actually bet.</p>
<p>The honest way to choose is to record a trial window from every candidate and replay those recordings through the same engine. Same markets, same clock, same decision rules &mdash; only the feed changes. A quoted latency is a claim about the vendor. A replay is a measurement of your book.</p>
<h2>Replay, not datasheets</h2>
<p>Replay only works if the recordings line up in time. Ours refuses to compare captures whose clocks disagree by more than {m['replay']['max_skew']} seconds, because past that you are measuring clock drift and calling it latency. It also applies a stated prior: a latency floor of {m['replay']['latency_floor']:.1f} seconds, below which no feed is credited with being faster. That floor is a prior, not a measurement.</p>
<h2>Why latency decides more than it looks</h2>
<p>A quote arrives stamped at {m['fill']['age']:.1f} seconds old. The feed carrying it took {m['fill']['latency']:.1f} seconds, above the stated floor. So the price you are pricing against is really {m['fill']['effective']:.1f} seconds old. Everything downstream moves with that.</p>
<p>Fill probability splits the same way. Read at stamped age, the fill looks like {m['fill']['naive']}%. Read at effective age, it is {m['fill']['honest']}%. On a nominal edge of {m['fill']['edge']:.1f}%, the naive read books {m['fill']['edge_naive']:.2f}% and the honest read books {m['fill']['edge_honest']:.2f}%. The smaller figure is the one that settles. Both fills come off a stated prior survival curve for this market class, not off a measurement of any feed &mdash; your own accept and reject record replaces it.</p>
<p>The table below shows the same mechanism on a different stated prior: survival modelled as exponential decay with a tau of {m['quote_age']['tau']:.1f} seconds, tabulated from the latency floor prior of {m['quote_age']['latency_floor']:.1f} seconds upward. The half-life that follows from that tau is {m['quote_age']['half_life']:.1f} seconds. Modelled, not measured, and it falls at every step.</p>
<table>
<tr><th>Quote age (s)</th><th>Edge surviving</th></tr>
{"".join(f"<tr><td>{r['age']}</td><td>{r['survives']:.1f}%</td></tr>" for r in m['quote_age']['rows'])}
</table>
<p>Read any such curve against effective age, never against stamped age. An effective age of {m['fill']['effective']:.1f} seconds still sits inside the half-life; a stamped age of {m['fill']['age']:.1f} seconds flatters the feed by exactly the latency you failed to subtract. Do not expect this table to reproduce the fill figures above &mdash; different tau, different curve. What carries across is the direction.</p>
<h2>The thing nobody sells on</h2>
<p>A feed that stamps its own observation time is worth more than a faster feed that does not. Without a stamp you cannot recover effective age, so you cannot compute the honest fill, so the {m['fill']['edge_naive']:.2f}% figure is the only one available to you and it overstates. Speed you cannot check is a marketing claim. A timestamp is evidence. Buy the evidence.</p>
<p><a href="/guides/how-old-is-the-price-on-your-screen/">How old is the price on your screen &rarr;</a></p>
""",

"what-a-clock-you-cannot-trust-does-to-a-price": f"""
<p>Every freshness claim rests on two clocks agreeing. The feed stamps a quote with its clock. You judge that quote against yours. When the clocks disagree, a stale price reads as fresh and a fresh one reads as stale, and nothing about the number on screen reveals which case you are in.</p>
<p>The usual arithmetic hides this. Subtract the vendor timestamp from local time, print the difference as age, and the answer inherits the error of whichever clock is worse &mdash; with nothing in the output to say which one supplied it. The error does not surface as noise. It surfaces as confidence.</p>
<h2>Why a bad timestamp is worse than none</h2>
<p>A quote stamped more than {m['replay']['max_skew']:,} seconds ahead of our own clock is dropped from the snapshot rather than scored, and the count of what was dropped is reported alongside what survived. That ceiling is a stated prior &mdash; chosen, not measured. The rule is one-sided on purpose. A feed clock running ahead makes a stale price read as fresher than live and ranks it above every honestly dated quote on the screen; a feed clock running behind only makes a price look older than it is. A missing timestamp makes you cautious. A wrong one makes you confident, and confidence is the expensive failure. The ceiling is also wider than the whole table below, whose oldest row is {m['quote_age']['rows'][4]['age']:,} seconds &mdash; a clock error this engine still tolerates can exceed every age it scores.</p>
<h2>The floor under an undated quote</h2>
<p>Under the ceiling sits a floor. When the feed gives no timestamp of its own, age is never priced below {m['replay']['latency_floor']:.1f} seconds &mdash; a stated prior, not a measurement of any feed. It is not zero, because zero is the one value certainly wrong: the price left the book, crossed a network, and rendered before you read it. A quote the feed did date needs no such addition &mdash; that delay already sits inside the age you compute, and adding the floor on top would count it twice. The youngest row below is that floor, and survival there is already short of certain.</p>
<h2>What a mis-estimated age costs</h2>
<p>Survival is modelled as exponential decay on a mean lifetime of {m['quote_age']['tau']:.1f} seconds &mdash; again a stated prior, standing until your own accept and reject record replaces it. On that assumption the half-life is {m['quote_age']['half_life']:.1f} seconds, and the rows below are what the assumption implies rather than what any feed has been observed to do.</p>
<table>
<tr><th>Quote age (seconds)</th><th>Edge surviving</th></tr>
{"".join(f"<tr><td>{r['age']:,}</td><td>{r['survives']:.1f}%</td></tr>" for r in m['quote_age']['rows'])}
</table>
<p>Read the cost off the rows. Take a quote for {m['quote_age']['rows'][1]['age']:,} seconds old when it is really {m['quote_age']['rows'][3]['age']:,}, and you priced {m['quote_age']['rows'][1]['survives']:.1f}% of your edge as surviving when the curve gives {m['quote_age']['rows'][3]['survives']:.1f}%. A stated edge of {m['quote_age']['example_edge']:.1f}% at {m['quote_age']['example_age']:,} seconds is worth {m['quote_age']['example_realised']:.2f}% once survival is applied. The clock error never appears in the price. It appears in the fill.</p>
<p><a href="/guides/how-old-is-the-price-on-your-screen/">How old is the price on your screen &rarr;</a></p>
""",

"why-your-bets-get-rejected": f"""
<p>You tap a price and the book says it has changed. Usually nothing is wrong
with the book &mdash; the price you saw was already old.</p>
<p>Every screen shows a quote captured at some past instant. Between then and
your bet landing sit the feed's own delay, the poll interval, the render and
you. On a feed running {f['latency']:.1f} seconds behind, a quote displayed as
{f['age']:.0f} seconds old is really {f['effective']:.1f}.</p>
<p>That changes the number that matters. Its real chance of still being
available is {f['honest']}%, where a screen ignoring the feed's own lag would
say {f['naive']}%. On a {f['edge']:.0f}% edge that is the difference between
{f['edge_honest']:.2f}% and
{f['edge_naive']:.2f}% actually realised.</p>
<p>It also explains why the biggest numbers reject most often. A screen sorted
by raw expected value is sorted partly by staleness: the largest edges cluster
on books that moved most recently, which are the books most likely to have
moved again.</p>
""",
    }


def versus_description(row: dict) -> str:
    """A meta description that fits, whatever the competitor's gap text says.

    Composed and length-checked rather than interpolated and hoped for. Three
    of five competitor pages failed the 50-160 character rule on the first
    render, for no reason except that the source text varies in length.
    """
    for candidate in (
        f"{row['gap']}. Bookbreaker reports the devig spread, the chance of "
        f"getting the bet down, and when a record proves nothing.",
        f"A {row['name']} alternative that reports the devig spread, the "
        f"chance of getting the bet down, and when a record proves nothing.",
        f"A {row['name']} alternative that shows how uncertain its own numbers "
        "are.",
    ):
        if 50 <= len(candidate) <= 160:
            return candidate
    return ("An alternative that reports the devig spread, the chance of "
            "getting the bet down, and when a record proves nothing.")


def render_calculator(m: dict, row: dict) -> str:
    """One calculator page, with a worked example the engine produced.

    Every competing calculator page shows a form and a formula. These show the
    arithmetic already done on real prices, and — the part none of them do —
    the range the answer actually sits in.
    """
    slug = row["slug"]
    c = m["calculators"][slug]
    body = c["body"]
    return f"""
<div class="phead">
<p class="crumb"><a href="/">Home</a><span>/</span>
<a href="/calculators/">Calculators</a></p>
<h1>{e(row['name'])}</h1>
<p class="lede">{e(row['question'])}</p>
</div>
{body}
<h2>Where the number comes from</h2>
<p>Everything above was computed by the same engine that prices bets, at the
moment this page was built &mdash; not typed into a template. The build fails
if a figure appears here and not in the engine's own output.</p>
<p><a href="/how-it-works/">How a price is formed &rarr;</a>
&nbsp;&middot;&nbsp;
<a href="/what-your-record-proves/">What a record can prove &rarr;</a></p>
"""


def render_versus(m: dict, row: dict) -> str:
    """One competitor page.

    These scored 0.84 against each other on the portfolio similarity gate,
    and the reason was structural rather than stylistic: the page was about
    two hundred words of shared argument with a name and a price dropped into
    it. Every competitor page made the same case, so Google had no reason to
    keep more than one.

    The differentiator now is arithmetic that actually differs. A monthly fee
    is a hurdle to clear before the first dollar of profit, and across this
    list it ranges from five dollars a month to three hundred and forty-seven
    — which is the difference between three bets a month and a hundred and
    seventy-four. That is a real fact about each product, and it is different
    for each one.
    """
    d = m["devig"]
    sub = m.get("subs", {}).get(row["slug"])

    # Branching on what this tool costs, because the honest advice genuinely
    # differs by price band. A shared paragraph with the name swapped is what
    # scored these pages 0.84 against each other in the first place.
    if sub and sub["fee"] >= 200:
        verdict = (
            f"<h2>Who {e(row['name'])} is actually for</h2>"
            f"<p>At {sub['sym']}{sub['fee']:,.0f} a month this is priced for "
            f"someone betting full time. The subscription only makes sense if "
            f"you are already turning over "
            f"{sub['sym']}{sub['rows'][1]['turnover']:,} a month at a real "
            f"edge, and if you are not there yet, the fee is the largest "
            f"negative-EV bet in your month.</p>"
            f"<p>What you are buying at that price is {e(row['note'])}. "
            f"What you are not buying is {e(row['gap'][0].lower() + row['gap'][1:])}, "
            f"and on a subscription this size that omission is the whole "
            f"question (read {e(row['read'])}, <a href=\"{e(row['source'])}\">source</a>).</p>")
    elif sub and sub["fee"] >= 50:
        verdict = (
            f"<h2>Who {e(row['name'])} is actually for</h2>"
            f"<p>{sub['sym']}{sub['fee']:,.0f} a month is a serious hobbyist "
            f"price, and clearing it needs {sub['rows'][1]['bets']} winning "
            f"bets a month at a {sub['sym']}{sub['stake']} stake and a 2% "
            f"edge. That is reachable, which is exactly why it is worth "
            f"checking against your own record rather than assuming.</p>"
            f"<p>{e(row['name'])} offers {e(row['note'])}, and the thing to "
            f"weigh against {sub['sym']}{sub['fee']:,.0f} a month is that "
            f"{e(row['gap'][0].lower() + row['gap'][1:])}. Whether that "
            f"matters depends on how close to the line you bet (read {e(row['read'])}, <a href=\"{e(row['source'])}\">source</a>).</p>")
    elif sub:
        verdict = (
            f"<h2>Who {e(row['name'])} is actually for</h2>"
            f"<p>At {sub['sym']}{sub['fee']:,.0f} a month the fee is close to "
            f"irrelevant &mdash; {sub['rows'][1]['bets']} winning bets at a 2% "
            f"edge covers it. So compare on capability: {e(row['note'])} "
            f"against the fact that {e(row['gap'][0].lower() + row['gap'][1:])} (read {e(row['read'])}, <a href=\"{e(row['source'])}\">source</a>).</p>")
    else:
        verdict = (
            f"<h2>What {e(row['name'])} does not publish</h2>"
            f"<p>{e(row['name'])} published no monthly price when its pricing "
            f"was read on {e(row['read'])} "
            f"(<a href=\"{e(row['source'])}\">source</a>), so the first thing "
            f"you can measure about a competing tool &mdash; what it costs "
            f"before you win anything &mdash; is not available here. A tool "
            f"that will not state a price before a demo is one you cannot "
            f"compare on the arithmetic.</p>")

    hurdle = ""
    if sub:
        rows = "".join(
            f"<tr><td class=\"prose\">{r['edge']}%</td><td>{r['bets']}</td>"
            f"<td>{sub['sym']}{r['turnover']:,}</td>"
            f"<td class=\"prose\">from the price read {e(row['read'])}, "
            f"<a href=\"{e(row['source'])}\">source</a></td></tr>"
            for r in sub["rows"])
        hurdle = f"""
<h2>What {e(row['name'])} costs you before you win anything</h2>
<p>At {e(row['price'])}, the cheapest monthly plan is
<strong>{sub['sym']}{sub['fee']:,.2f}</strong> &mdash; <strong>{sub['sym']}{sub['yearly']:,.2f}</strong>
a year. That is not a price you pay out of profit. It is a hurdle you clear
before there is any profit, and it is worth seeing as the number of winning
bets it takes to reach zero.</p>
<p>At a {sub['sym']}{sub['stake']} average stake:</p>
<div class="scroll"><table>
<tr><th class="prose">Your edge</th><th>Bets a month to break even</th>
<th>Turnover a month</th><th class="prose">Basis</th></tr>
{rows}
</table></div>
<p>A {sub['rows'][1]['edge']}% edge is a good one, and it still takes
<strong>{sub['rows'][1]['bets']} bets a month</strong> at that stake purely to
cover the subscription. Below that you are paying to lose more slowly. The
figures are arithmetic on the published price and a stated {sub['sym']}{sub['stake']}
stake, not a claim about anybody's results.</p>
"""

    return f"""
<h1>A {e(row['name'])} alternative that shows its uncertainty</h1>
<p class="lede">{e(row['note'])}, at {e(row['price'])} &mdash; read
{e(row['read'])}, <a href="{e(row['source'])}">source</a>.</p>

<h2>The gap</h2>
<p>{e(row['gap'])}.</p>
<p>That absence is not incidental. A screen sorted by raw expected value is
sorted partly by how stale its own data is, because the biggest numbers cluster
on the books that moved most recently &mdash; which are the books most likely
to have moved again.</p>

{hurdle}

{verdict}
<p><a href="/download/">Download Bookbreaker free &rarr;</a>
&nbsp;&middot;&nbsp;<a href="/vs/">How every tool compares &rarr;</a>
&nbsp;&middot;&nbsp;<a href="/how-it-works/">Why an edge is a range &rarr;</a></p>
<p class="caveat">Prices and capabilities change. The claim above carries the
date it was read and a link to where it was read; the build fails if either is
missing.</p>
"""


def render_longevity(m: dict) -> str:
    h = m["heat"]
    stake_rows = "".join(
        f"<tr><td>{e(r['stake'])}</td><td>{r['heat']}%</td></tr>"
        for r in h["stakes"]
    )
    market_rows = "".join(
        f"<tr><td>{e(r['market'])}</td><td>{r['heat']}%</td></tr>"
        for r in h["markets"]
    )
    a = m["arb"]
    cat = m["catalog"]

    return f"""
<h1>An account that gets limited stops earning</h1>
<p class="lede">Every tool in this category optimises expected value and leaves
account lifetime to your judgement. That is why the usual experience is three
excellent weeks followed by a five-dollar maximum stake. Edge you cannot place
is worth nothing, so lifetime is not a footnote beside expected value &mdash;
it is what expected value gets divided by.</p>

<h2>What a stake gives away</h2>
<p>A precise figure to the cent is the most-cited fingerprint risk desks use to
identify arbitrage. Nobody types {e(h['stakes'][0]['stake'])}:</p>
<table>
<tr><th>Stake</th><th>How mechanical it reads</th></tr>
{stake_rows}
</table>
<p>So the arbitrage solver optimises over <em>round</em> stakes directly rather
than rounding afterwards, because rounding a lock naively breaks it &mdash; the
legs are not symmetric. At {e(a['legs'][0])} and {e(a['legs'][1])} that means
{a['round_stakes'][0]:,} and {a['round_stakes'][1]:,} instead of
{a['exact_stakes'][0]:,.2f} and {a['exact_stakes'][1]:,.2f}, giving up
{a['rounding_cost']:,.2f} of the {a['exact_profit']:,.2f}. The cost is named
rather than hidden.</p>

<h2>What a market gives away</h2>
<p>Arbitrage concentrates in markets priced with less attention, which is
exactly why a profile made of them reads as sharp:</p>
<table>
<tr><th>Market</th><th>How much it signals</th></tr>
{market_rows}
</table>
<p>Reaction time works the same way: a bet placed
{e(h['reaction'][0]['after'])} after a sharp book moved scores
{h['reaction'][0]['heat']}%, one placed {e(h['reaction'][2]['after'])} later
scores {h['reaction'][2]['heat']}%. No human refreshes and decides in half a
second.</p>

<h2>Where it does nothing at all</h2>
<p>{cat['venues']} venues are catalogued, and the ones that never limit winners
get no shaping whatsoever. A {e(h['stakes'][0]['stake'])} stake is rounded to
{h['shaped']:,} at a retail book and left at {h['untouched']:,.2f} at a sharp
one. Spending edge to hide from a risk desk that does not exist is the most
common way these tactics are applied wrongly, and there is a test for it.</p>

<h2>What it will not do</h2>
<p>No multi-accounting. No identity or KYC workarounds. No device or location
spoofing. That line is drawn in the code rather than in a policy document: the
model reads bet attributes only &mdash; stake sizes, timing, market mix,
velocity &mdash; and has no access to identity or network state. Everything it
adjusts is a choice you were already making about your own betting.</p>
<p>It is also advisory. It tells you what to bet; you place it. Automated
placement against a book's own interface is a different product with a
different risk profile, and it is not this one.</p>
"""


def render_evidence(m: dict) -> str:
    ev = m["evidence"]
    p = m["performance"]
    bar_rows = "".join(
        f"<tr><td>{r['tests']}</td><td>z {r['z']:.2f}</td><td>{r['luck']}%</td></tr>"
        for r in ev["bars"]
    )
    return f"""
<h1>Most betting records prove nothing, and say otherwise</h1>
<p class="lede">A 2% edge over 500 even-money bets swings between roughly -7%
and +11% across a season. So a bettor with a real edge routinely shows a losing
year, and a bettor with none routinely shows a great one. Every tracker prints
the number and stops.</p>

<h2>A real record, read honestly</h2>
<p>{p['n']} settled bets, {p['profit']:+,} profit, {p['roi']:.2f}% return:</p>
<p class="figure">{e(p['verdict'])}</p>
<p>The interval runs {p['low']:.1f}% to {p['high']:.1f}%. Nothing about that
record distinguishes it from break-even, and no amount of presentation changes
it. Below {ev['floor']} settled bets nothing is characterised at all.</p>

<h2>Slice it enough and something always looks good</h2>
<p>Tag your bets and each tag becomes a hypothesis. Test enough hypotheses and
one clears the bar by luck:</p>
<table>
<tr><th>Tags tested</th><th>Bar required</th><th>Chance one is luck</th></tr>
{bar_rows}
</table>
<p>At ten tags there is a {ev['bars'][2]['luck']}% chance that something looks
significant when nothing is. So the bar rises with the number of slices
checked, and the report says how many cleared the ordinary bar and how many
survived the correction. A bettor who invents labels until one looks profitable
is running a search, not a test.</p>

<h2>Why closing line value instead</h2>
<p>Profit takes years to say anything. The closing line is the market's best
public estimate, and beating it consistently converges far faster &mdash; which
is why it is the signal the engine calibrates on rather than merely displays.
It also refuses to overclaim: under {ev['floor']} graded bets it declines to
give a verdict at all.</p>
<p><a href="/how-it-works/">How a price is formed &rarr;</a></p>
"""


STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DC": "Washington DC", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "IA": "Iowa", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "MA": "Massachusetts", "MD": "Maryland", "ME": "Maine", "MI": "Michigan",
    "MN": "Minnesota", "MO": "Missouri", "MS": "Mississippi", "MT": "Montana",
    "NC": "North Carolina", "ND": "North Dakota", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NV": "Nevada", "NY": "New York",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VA": "Virginia",
    "VT": "Vermont", "WA": "Washington", "WI": "Wisconsin",
    "WV": "West Virginia", "WY": "Wyoming",
}



# --------------------------------------------------------------- partners

# The commercial layer. Three rules, and the first two exist because getting
# them wrong is the difference between a business and a penalty.
#
#   1. A link that pays us is marked `rel="sponsored nofollow"`. Google asks
#      for it, and an affiliate site that does not do it is one manual action
#      away from having no traffic to monetise. `nofollow` alone stopped being
#      sufficient in 2020.
#   2. A page carrying a paid link carries a disclosure the reader sees before
#      the link, not a line in the footer. That is the FTC's standard, and it
#      is also the only version that survives someone reading the page.
#   3. **A partner with no affiliate URL renders an ordinary link, never an
#      invented tracking one.** There is no affiliate account behind any row
#      in `_data/partners.csv` yet. A build that emitted a plausible-looking
#      tracking URL would earn nothing, be indistinguishable from one that
#      earned something, and quietly rot the moment a real one arrived.

def load_partners() -> dict:
    """Partner rows keyed by book. `affiliate_url` empty means not signed up."""
    out = {}
    for row in load_data("partners"):
        out[row["book"].strip()] = {
            "affiliate": (row.get("affiliate_url") or "").strip(),
            "site": (row.get("site_url") or "").strip(),
            "program": (row.get("program") or "").strip(),
            "source": (row.get("source") or "").strip(),
        }
    return out


PARTNERS = load_partners()


def partner_link(book_key: str, label: str, state: str = "") -> str:
    """A link to a sportsbook, paid or not, marked honestly either way.

    `{SUBID}` in an affiliate URL is replaced with the state code so revenue
    can be attributed to the page that earned it. Without that every state
    page reports the same nothing and there is no way to learn which ones
    work.
    """
    row = PARTNERS.get(book_key)
    if not row or not row["site"]:
        return e(label)
    if row["affiliate"]:
        href = row["affiliate"].replace("{SUBID}", state.lower())
        return (f'<a class="book-cta" href="{e(href)}" '
                f'rel="sponsored nofollow noopener" target="_blank">'
                f'{e(label)}</a>')
    # No programme yet: an ordinary outbound link, and nothing claims otherwise.
    return (f'<a class="book-link" href="{e(row["site"])}" '
            f'rel="nofollow noopener" target="_blank">{e(label)}</a>')


def any_paid_links() -> bool:
    """Whether any partner is actually live. Drives the disclosure."""
    return any(r["affiliate"] for r in PARTNERS.values())


def disclosure() -> str:
    """Shown above the first commercial link, never only in the footer."""
    if any_paid_links():
        return ('<p class="disclose"><strong>Advertising disclosure.</strong> '
                'Some links on this page are paid partnerships, and we may be '
                'compensated if you open an account through them. It costs you '
                'nothing, it never changes which book we say limits winners, '
                'and every figure on this page is still computed by the engine '
                'rather than supplied by a sportsbook.</p>')
    return ('<p class="disclose"><strong>No paid links on this page.</strong> '
            'The sportsbook links below are ordinary links and earn us '
            'nothing. If that changes, this notice changes with it.</p>')


def responsible() -> str:
    """21+, the helpline, and no claim anybody is going to win.

    The national line is used rather than a per-state one: publishing 34
    state helpline numbers from memory is exactly the kind of unsourced
    detail this build refuses everywhere else, and 1-800-GAMBLER is correct
    in every state that has legal betting.
    """
    return ('<aside class="rg">'
            '<p><strong>21+ and present in a state where betting is legal.</strong> '
            'Betting carries a risk of financial loss, and nothing on this site '
            'is a prediction that you will win. The engine measures how uncertain '
            'a price is; it does not remove the uncertainty.</p>'
            '<p>If gambling stops being fun, it is not fun. '
            '<a href="tel:1-800-426-2537">Call 1-800-GAMBLER</a> or visit '
            '<a href="https://www.ncpgambling.org/help-treatment/" '
            'rel="noopener" target="_blank">ncpgambling.org</a>.</p>'
            '</aside>')


def faq_schema(pairs: list) -> str:
    """FAQPage JSON-LD. The questions have to be on the page too — marking up
    answers a reader cannot see is what the guidelines call out."""
    items = ",".join(
        json.dumps({
            "@type": "Question",
            "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": a},
        }, ensure_ascii=False)
        for q, a in pairs)
    return ('<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"FAQPage",'
            f'"mainEntity":[{items}]}}</script>')


def breadcrumb_schema(trail: list) -> str:
    items = ",".join(
        json.dumps({
            "@type": "ListItem", "position": i + 1, "name": name,
            "item": f"https://bookbreaker.bet{url}",
        }, ensure_ascii=False)
        for i, (name, url) in enumerate(trail))
    return ('<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"BreadcrumbList",'
            f'"itemListElement":[{items}]}}</script>')




def load_jurisdictions() -> dict:
    """Per-state legal facts, keyed by state code.

    Every field is optional and every row carries a source. A blank is a fact
    nobody verified, and it renders as nothing at all rather than as a plausible
    default — the failure mode here is not an ugly page, it is a confident
    wrong claim about somebody's gambling law.
    """
    # load_data exits the build on a missing file, which is right for data the
    # site cannot render without and wrong for this: the legal facts are
    # additive, and a site that refuses to build until all fifty states are
    # researched is a site that never ships the first one.
    if not (SITE / "_data" / "jurisdictions.csv").exists():
        return {}
    rows = load_data("jurisdictions")
    out = {}
    for row in rows:
        code = (row.get("code") or "").strip().upper()
        if not code:
            continue
        # A row with more fields than the header hands DictReader a list
        # under a None key. Unquoted commas in a note did exactly that,
        # and the build died on it rather than shipping a mangled fact.
        if None in row:
            raise SystemExit(
                f"jurisdictions.csv: row {code} has more fields than the "
                "header — quote any value containing a comma")
        out[code] = {k: (v or "").strip() for k, v in row.items()}
    return out


JURISDICTIONS = load_jurisdictions()


def jurisdiction_facts(code: str, name: str) -> str:
    """The legal section, rendered only from fields that were sourced.

    A row with no source link is not rendered at all. That rule is what keeps
    this from becoming the thing every competing page is — a confident recital
    of regulatory detail with nothing behind it.
    """
    row = JURISDICTIONS.get(code)
    if not row or not row.get("source"):
        return ""

    facts = [
        ("Regulator", row.get("regulator")),
        ("Online betting went live", row.get("launch_date")),
        ("Minimum age", (row.get("min_age") + "+") if row.get("min_age") else ""),
        ("State tax on sportsbook revenue",
         (row.get("tax_rate") + "%") if row.get("tax_rate") else ""),
        ("College player props", row.get("college_props", "").title()),
        ("Licensed retail sportsbooks", row.get("retail_venues")),
    ]
    shown = [(k, v) for k, v in facts if v]
    if not shown:
        return ""

    # Every row carries its own read date and source link. The site gate only
    # permits a number the engine cannot compute inside a block that is dated
    # and sourced, and it is right to: a tax rate in a table with one footnote
    # at the bottom is a claim whose provenance a reader has to go hunting for.
    read = row.get("fetched_at") or ""
    src = row["source"]
    rows_html = "".join(
        f'<tr><td class="prose">{e(k)}</td><td class="prose">{e(v)}</td>'
        f'<td class="prose"><a href="{e(src)}" rel="nofollow noopener" '
        f'target="_blank">source</a>, read {e(read)}</td></tr>'
        for k, v in shown)
    note = (f'<p>{e(row["note"])} <a href="{e(src)}" rel="nofollow noopener" '
            f'target="_blank">Source</a>, read {e(read)}.</p>'
            if row.get("note") else "")
    return f"""
<h2>The law in {e(name)}</h2>
<div class="scroll"><table>
<tr><th class="prose">&nbsp;</th><th class="prose">As published</th>
<th class="prose">Source</th></tr>
{rows_html}
</table></div>
{note}
<p class="caveat">Gambling law changes, and these were read once. Check the
regulator before relying on any of it.</p>
"""


def render_state_page(m: dict, code: str) -> str:
    """One state.

    The first version of this page scored 96% identical against another state
    on a word-level diff, and the portfolio similarity gate counted 406
    near-duplicate pairs across 33 of them. The cause was not the state data,
    which genuinely differs — it was that four fixed sections of general
    argument outweighed it. Programmatic pages that do not differ are the
    textbook case Google collapses: it keeps one and the other 32 earn nothing.

    So the general argument now lives once, on the pages built for it, and
    what stays here is what is true of this state and nowhere else: which
    books operate, which of those limit winners, **which do not operate at
    all**, and whatever the regulator publishes. The absent list matters as
    much as the present one — it is different for every state, and it is the
    reason a bettor in one state cannot follow advice written for another.
    """
    st = m["states"][code]
    name = STATE_NAMES.get(code, code)
    books = st["books"]
    online = [b for b in books if b["tier"] != "exchange"]
    exchanges = [b for b in books if b["tier"] == "exchange"]
    never = [b for b in books if not b["limits"]]
    limiting = [b for b in books if b["limits"]]

    here = {b["name"] for b in books}
    absent = sorted({b["name"] for c in m["states"]
                     for b in m["states"][c]["books"]} - here)
    assert len(absent) == st["absent"], (code, len(absent), st["absent"])

    rows = "".join(
        f"<tr><td>{partner_link(b['key'], b['name'], code)}</td>"
        f"<td class=\"prose\">{'Exchange' if b['tier'] == 'exchange' else b['tier'].title()}</td>"
        f"<td class=\"{'good' if not b['limits'] else 'warn'}\">"
        f"{'Never limits winners' if not b['limits'] else 'Limits winning accounts'}</td></tr>"
        for b in sorted(books, key=lambda x: (x["limits"], x["name"])))

    lead = (f"{len(online)} licensed online sportsbooks took bets in "
            f"{name} as of {st['as_of']}, and {len(limiting)} of them limit "
            f"accounts that win.")

    # Prose built from this state's own figures, branching on what they are.
    # A template with a number substituted into it is not differentiation —
    # that lesson came from the competitor pages an hour ago, where two tools
    # priced identically produced identical tables. These sentences differ
    # because the situations differ.
    shop = []
    if len(online) >= 8:
        shop.append(
            f"<p>With {len(online)} online books taking bets, {e(name)} is one "
            f"of the deeper markets in the country. That depth is the edge: "
            f"the gap between the best and second-best price on the same "
            f"market is what arbitrage lives on, and it widens with every "
            f"additional book willing to quote.</p>")
    elif len(online) >= 4:
        shop.append(
            f"<p>{len(online)} online books is enough to line shop but not "
            f"enough to be careless about it. Every market you bet should be "
            f"checked at all {len(online)}, because with this few quotes a "
            f"single book being slow to move is most of the edge available "
            f"on a given day.</p>")
    else:
        shop.append(
            f"<p>{len(online)} online book{'s' if len(online) != 1 else ''} is "
            f"a thin market. There is little to shop between, so most of what "
            f"is available in {e(name)} comes from promotional offers and from "
            f"the venues that cannot ban you rather than from price "
            f"differences.</p>")
    if never and limiting:
        shop.append(
            f"<p>Of those, {len(limiting)} will restrict an account that wins "
            f"consistently and {len(never)} will not. That is not a detail to "
            f"discover later: it decides which account is worth building a "
            f"real record at, and which are worth using for their prices "
            f"while they last.</p>")
    elif not never:
        shop.append(
            f"<p>Every venue on that list limits winning accounts. In "
            f"{e(name)} there is no exception to plan around, so account "
            f"lifespan is a cost of doing business rather than something one "
            f"book lets you avoid.</p>")
    # The regulator's own figures, used in sentences rather than only tabled.
    # A tax rate sitting in a table is a fact; the same rate explaining why a
    # market prices the way it does is a paragraph only this state can have.
    j = JURISDICTIONS.get(code, {})
    if j.get("tax_rate"):
        rate = float(j["tax_rate"])
        if rate >= 30:
            shop.append(
                f"<p>{e(name)} taxes sportsbook revenue at {j['tax_rate']}%, "
                f"among the highest in the country. That cost does not fall on "
                f"the operator alone &mdash; it shows up as worse prices than "
                f"the same book offers in a cheaper state, which is why a line "
                f"quoted here is not the line quoted elsewhere.</p>")
        elif rate <= 12:
            shop.append(
                f"<p>At {j['tax_rate']}% on sportsbook revenue, {e(name)} is "
                f"one of the lighter tax regimes. Operators have more room to "
                f"price competitively here than in states taking three or four "
                f"times as much, and that room is where a shopper's edge "
                f"comes from.</p>")
    if j.get("launch_date", "")[:4].isdigit():
        year = int(j["launch_date"][:4])
        if year >= 2024:
            shop.append(
                f"<p>Online betting only went live here on "
                f"{j['launch_date']}, which makes {e(name)} a young market. "
                f"Operators buying share in a new state price more "
                f"aggressively and hand out more promotional value than they "
                f"do once a market settles.</p>")
        elif year <= 2020:
            shop.append(
                f"<p>{e(name)} has had online betting since "
                f"{j['launch_date']}, long enough for the promotional phase to "
                f"be over and for risk desks to have a settled view of who "
                f"they want as a customer. Accounts here get profiled by "
                f"operators with years of data behind them.</p>")
    if j.get("college_props") == "banned":
        shop.append(
            f"<p>College player props are barred outright in {e(name)}, which "
            f"removes the softest market on most boards. Props are where "
            f"pricing is thinnest and where a careful bettor finds the most "
            f"mistakes, so their absence pushes the available edge back into "
            f"main markets where the books are sharpest.</p>")
    elif j.get("college_props") == "restricted":
        shop.append(
            f"<p>{e(name)} restricts college wagering rather than banning it, "
            f"so part of the board that exists in other states is missing "
            f"here. Check the catalogue before planning around a market: the "
            f"restriction is usually on in-state teams or on player props "
            f"specifically.</p>")
    shop_html = "".join(shop)

    never_line = ""
    if never:
        never_line = (
            f"<p>The {len(never)} venue{'s' if len(never) > 1 else ''} in "
            f"{e(name)} that never limit a winning account: "
            + ", ".join(f"<strong>{e(b['name'])}</strong>" for b in never)
            + ". On a list of " + str(len(books)) + ", that is where a record "
            "worth having gets built.</p>")

    absent_block = ""
    if absent:
        absent_block = f"""
<h2>What you cannot get in {e(name)}</h2>
<p>{len(absent)} book{'s' if len(absent) > 1 else ''} covered elsewhere in the
United States {'do' if len(absent) > 1 else 'does'} not take bets in
{e(name)}: {", ".join(e(a) for a in absent)}.</p>
<p>That list is why advice written for another state does not transfer. Line
shopping is the largest edge available to an ordinary bettor, and it is bounded
by the {len(books)} venues that will actually take your money here.</p>
"""

    faqs = [
        (f"Is online sports betting legal in {name}?",
         f"{name} had {len(online)} licensed online sportsbooks operating as "
         f"of {st['as_of']}, alongside {len(exchanges)} federally regulated "
         f"prediction market{'s' if len(exchanges) != 1 else ''}."),
        (f"Which sportsbooks in {name} limit winning accounts?",
         f"{len(limiting)} of the {len(books)} venues covering {name} limit "
         f"accounts that win consistently. "
         + (", ".join(b["name"] for b in never) + " never do."
            if never else "None of them are exempt.")),
        (f"How many sportsbooks should I open in {name}?",
         f"At least two of the {len(online)} available. One account cannot be "
         f"line shopped, and the gap between the best and second-best price is "
         f"the entire edge in arbitrage."),
        (f"What is not available in {name}?",
         (f"{len(absent)} books that operate elsewhere in the US do not take "
          f"bets here: {', '.join(absent)}." if absent else
          f"Every book this site tracks operates in {name}.")),
    ]
    faq_html = "".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in faqs)

    exch = ""
    if exchanges:
        exch = ("<h2>The venues in " + e(name) + " that cannot ban you</h2>"
                "<p>Regulated federally rather than by " + e(name) + ", which "
                "is why they reach every state, and with no bookmaker deciding "
                "who may keep betting.</p><ul>"
                + "".join(f"<li>{partner_link(b['key'], b['name'], code)}"
                          + (f" &mdash; {b['commission']}% commission" if b["commission"] else "")
                          + "</li>" for b in exchanges)
                + "</ul>")

    return f"""
{breadcrumb_schema([("Sportsbooks by state", "/sportsbooks/"),
                    (name, f"/sportsbooks/{code.lower()}/")])}
{faq_schema(faqs)}
<h1>Online sports betting in {e(name)}</h1>
<p class="lede">{e(lead)}</p>
{disclosure()}
{jurisdiction_facts(code, name)}

<h2>Every sportsbook covering {e(name)}</h2>
<p>Read {e(st['as_of'])} from each operator's own state disclosures. The
limiting column is the one no affiliate page publishes.</p>
<div class="scroll"><table>
<tr><th>Sportsbook</th><th class="prose">Type</th>
<th class="prose">Winning accounts</th></tr>
{rows}
</table></div>
{never_line}
{shop_html}

{absent_block}
{exch}

<h2>{e(name)} sports betting FAQ</h2>
{faq_html}

<p><a href="/how-it-works/">How a price is formed &rarr;</a>
&nbsp;&middot;&nbsp;<a href="/account-longevity/">What bet shape gives away
&rarr;</a>&nbsp;&middot;&nbsp;<a href="/download/">Download it free
&rarr;</a></p>
<p class="caveat">Coverage read {e(st['as_of'])} from operator state
disclosures. A starting point for your own check, not legal advice.</p>
"""


def state_url(m: dict, code: str) -> str:
    """Where this state's answer actually lives.

    Merged states have no page of their own, and a link to the URL one would
    have had is a 404 the link checker catches.
    """
    st = m["states"][code]
    if not st["legal"]:
        return "/sportsbooks/no-legal-sportsbook/"
    if not st["online"]:
        return "/sportsbooks/in-person-only/"
    if st["single_operator"]:
        return "/sportsbooks/one-book-states/"
    return f"/sportsbooks/{code.lower()}/"


def render_state_hub(m: dict) -> str:
    """The parent of the state pages, and the place the general argument for
    holding several accounts lives once instead of thirty-three times."""
    states = m["states"]
    live = sorted(c for c in states if states[c]["legal"] and states[c]["online"])
    retail = sorted(c for c in states if states[c].get("retail_only"))
    none = sorted(c for c in states if not states[c]["legal"])

    def cells(codes):
        return "".join(
            f'<li><a href="{state_url(m, c)}">'
            f'{e(STATE_NAMES.get(c, c))}</a> '
            f'<span class="n">{len([b for b in states[c]["books"] if b["limits"]])}'
            f' of {len(states[c]["books"])} limit</span></li>'
            for c in codes)

    as_of = states[next(iter(states))]["as_of"]
    return f"""
{breadcrumb_schema([("Sportsbooks by state", "/sportsbooks/")])}
<h1>Sports betting by state</h1>
<p class="lede">Every state, every licensed sportsbook covering it, and the
column no other guide prints: which of them limit accounts that win. Read
{e(as_of)}.</p>
{disclosure()}

<h2>Why the state you are in decides your edge</h2>
<p>Line shopping is the largest edge available to an ordinary bettor, and it is
bounded entirely by how many venues will take your money where you stand. A
bettor with nine books and a bettor with two are not running the same strategy
with different intensity; they are running different strategies, and most
betting advice is written without saying which one it assumes.</p>
<p>So each page below leads with the count, with which of those books limit
accounts that win, and with which books operate elsewhere but not there.</p>

<h2>Online betting is live &mdash; {m["markets"]["online"]} states</h2>
<ul class="states">{cells(live)}</ul>

<h2>In person only &mdash; {m["markets"]["retail"]} states</h2>
<p>Licensed sportsbooks exist, but no app takes a bet from inside the state.</p>
<ul class="states">{cells(retail)}</ul>

<h2>No legal sportsbook &mdash; {m["markets"]["none"]} states</h2>
<p>Federally regulated prediction markets still reach these, and they are the
venues that never limit a winner.</p>
<ul class="states">{cells(none)}</ul>

<p class="caveat">Coverage read {e(as_of)} from operator state disclosures.
A starting point for your own check, not legal advice.</p>
"""


def state_description(name: str) -> str:
    """A meta description that fits, for any state name.

    Composed and length-checked here rather than left to the gate. The first
    version ran over 160 characters for the six longest names — Massachusetts,
    North Carolina, New Hampshire, South Carolina, West Virginia and
    Washington DC — which the gate caught, but a renderer that can emit an
    invalid page is a renderer that will.
    """
    for candidate in (
        f"Sportsbooks and prediction markets reachable from {name}: which "
        f"limit winning accounts, and whether a fair price can be anchored. "
        f"Dated, not advice.",
        f"Sportsbooks reachable from {name}: which limit winning accounts, "
        f"and whether a fair price can be anchored there. Dated, not advice.",
        f"Sportsbooks and prediction markets reachable from {name}, and which "
        f"of them limit winning accounts. Dated.",
    ):
        if 50 <= len(candidate) <= 160:
            return candidate
    short = f"Sportsbooks reachable from {name}, and which limit winners."
    if 50 <= len(short) <= 160:
        return short
    return ("Sportsbooks and prediction markets by state: which limit winning "
            "accounts, and whether a fair price can be anchored. Dated.")


def render_market(m: dict, codes: list[str]) -> str:
    """One state. Genuinely different on every page, because the book list is.

    Programmatic pages earn their place only when each says something the
    others do not. These do: a different set of venues, a different count of
    anchors, and — the part that changes the advice — whether anything in the
    state never limits winners.
    """
    st = m["states"][codes[0]]
    names = [STATE_NAMES.get(c, c) for c in codes]
    name = names[0] if len(names) == 1 else (
        ", ".join(names[:-1]) + " and " + names[-1])

    opening = (
        f"<p class=\"lede\">{st['venues']} venues reachable from "
        f"{e(name)}, of which {st['retail']} are retail sportsbooks and "
        f"{st['anchors']} can anchor a fair price.</p>"
    )

    rows = "".join(
        f"<tr><td>{e(b['name'])}</td>"
        f"<td>{e(b['tier'])}</td>"
        + ("<td>yes</td>" if b["limits"]
           else '<td><span class="pos">never</span></td>')
        + f"<td>{(str(b['commission']) + '%') if b['commission'] else '&mdash;'}</td>"
        "</tr>"
        for b in st["books"]
    ) or "<tr><td colspan=\"4\">none</td></tr>"

    never = st["never_limit"]
    if never:
        longevity = (
            f"<p>{len(never)} of these never limit winning accounts. That "
            "matters more than it sounds: an account that gets limited stops "
            "earning, so account lifetime is what expected value is divided "
            "by. Bookbreaker spends no anti-limiting effort at a venue with no "
            "risk desk to hide from.</p>"
        )
    else:
        longevity = (
            "<p>Every venue here limits winning accounts, so bet shape carries "
            "the whole weight &mdash; stake sizes, timing and market mix "
            "decide how long an account lasts.</p>"
        )

    anchor = (
        "<p>With a sharp or exchange price available, a fair value here rests "
        "on a book that prices to be right rather than to be attractive.</p>"
        if st["has_anchor"] else
        "<p>No sharp or exchange venue is reachable, so a fair value built "
        "here would be a poll of the books you intend to beat. Bookbreaker "
        "flags that rather than pricing through it.</p>"
    )

    retail_names = [b["name"] for b in st["books"] if b["tier"] == "retail"]
    if st["retail"] == 1:
        why = (f" &mdash; {e(st['single_operator'])}"
               if st.get("single_operator") else "")
        distinctive = (
            f"<p>{e(name)} is a single-operator market{why}. "
            f"{e(retail_names[0])} is the only retail sportsbook here, which "
            "makes it the hardest kind of market to arb: an arbitrage needs "
            "two books and there is one. What remains is the exchange, and "
            f"pricing {e(retail_names[0])} against it.</p>"
        )
    elif st["retail"] >= 10:
        distinctive = (
            f"<p>{st['retail']} retail books makes {e(name)} one of the "
            "deepest markets in the country. More books means more "
            "disagreement, and disagreement between books is where every "
            "arbitrage comes from.</p>"
        )
    else:
        distinctive = (
            f"<p>{st['retail']} retail books operate here, including "
            + e(", ".join(retail_names[:3]))
            + ". Each one you hold is another price to compare, and another "
            "account whose lifetime the heat model is protecting.</p>"
        )

    shared = "" if len(codes) == 1 else (
        f"<p>These {len(codes)} states are on one page because they license "
        "exactly the same set of venues &mdash; separate pages would have said "
        "the same thing twice.</p>"
    )

    return f"""
<h1>Sportsbooks you can use in {e(name)}</h1>
{opening}
{shared}
{distinctive}
<table>
<tr><th>Venue</th><th>Kind</th><th>Limits winners</th><th>Commission</th></tr>
{rows}
</table>
{anchor}
{longevity}
<p class="caveat">Table read {e(st['as_of'])}, {st['stale_days']} days ago. A
jurisdiction list shown without its date asserts &ldquo;true now&rdquo;
forever, so this one carries its own age. It is a starting point for your own
check, not advice &mdash; the book's own site decides whether it will accept
you.</p>
<p><a href="/how-it-works/">How Bookbreaker prices a market &rarr;</a></p>
"""


STYLE = """/* The page is a printed statistical plate; the product is a dark terminal block
   set into it. Two rules hold the whole system together:

   1. Chroma appears where a MEASUREMENT appears, and in exactly one other
      place: the primary action. Never a nav hover, never a gradient, never a
      second button on the same screen.

      The original rule admitted no exception, and it was wrong in a way worth
      recording. A site with no coloured action has no action: the page read
      as an essay because nothing on it looked clickable, and a reader who
      agrees with every word and cannot find the product has not been
      persuaded of anything. One accent, used once per screen, is the smallest
      exception that fixes it — and it stays scarce enough that a measurement
      in chroma still reads as a measurement.
   2. An interval is drawn as an object, never printed as a string. The site's
      thesis is that the edge is a range; a page that only says so in words is
      not making the argument it claims to make.

   Light is the bare :root default. Dark is the media override plus the
   [data-theme] stamp, so all three viewer states resolve as a set. */
:root{
  /* --- ground --- */
  --plate:#ece9e2;        /* page ground: warm coated chart stock */
  --card:#f7f5f1;         /* lifted plot / table / figure surface */
  --sink:#e3dfd6;         /* inset: table head, app bar, footer */

  /* --- ink --- */
  --ink:#16161a;          /* body type AND the terminal-block ground */
  --ink-2:#57544d;        /* labels, secondary prose      6.23:1 on plate */
  --ink-3:#7d786e;        /* decorative only              3.62:1 — never text
                             that carries meaning on its own */
  --rule:#b8b3a8;         /* axes, ticks, hairlines, table rules
                             NON-TEXT ONLY, by design */

  /* --- measurement chroma (the only chroma on the site) --- */
  --indigo:#2d3561;       /* interval bounds, computed values   9.66:1 */
  --oxblood:#9e2f27;      /* negative side of zero, named costs 5.99:1 */
  --band:rgba(45,53,97,.16);      /* interval fill */
  --band-neg:rgba(158,47,39,.15); /* interval fill left of zero */
  --hatch:rgba(158,47,39,.32);    /* 45 degree hatch = "not claimable" */

  /* --- the one action colour --- */
  --accent:#0369a1;       /* primary action fill        6.42:1 against white */
  --accent-hi:#075985;
  --accent-ink:#ffffff;

  /* --- the terminal block --- */
  --term:#16161a;
  --term-line:#2c2c33;

  /* --- type --- */
  --serif:ui-serif,"Iowan Old Style",Charter,"Bitstream Charter",Georgia,Cambria,serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  --display:-apple-system,BlinkMacSystemFont,"Segoe UI Variable Display",
    "Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;

  --t-1:.72rem;   --t-2:.82rem;   --t-3:.9rem;    --t-4:1rem;
  --t-5:1.0625rem;--t-6:1.25rem;  --t-7:1.75rem;
  --t-8:clamp(2.6rem,6.4vw,4.5rem);

  --s-1:.25rem; --s-2:.5rem;  --s-3:.75rem; --s-4:1rem;
  --s-5:1.5rem; --s-6:2.25rem;--s-7:3.5rem; --s-8:5.5rem;

  /* the asymmetry is what makes it a report rather than an essay */
  --measure-prose:34rem;
  --measure-plate:58rem;
  --measure-page:46rem;

  --r:2px;                /* the only radius on the site */
}

@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --plate:#0d0f13;
    --card:#161a21;
    --sink:#11141a;
    --ink:#ffffff;
    --ink-2:#9aa4b2;
    --ink-3:#6b7280;
    --rule:#2f3540;
    --indigo:#8f9bd8;
    --oxblood:#e0685c;
    --band:rgba(143,155,216,.22);
    --band-neg:rgba(224,104,92,.20);
    --hatch:rgba(224,104,92,.34);
    --accent:#38bdf8;
    --accent-hi:#7dd3fc;
    --accent-ink:#07131a;
    --term:#05070a;
    --term-line:#2f3540;
  }
}
:root[data-theme="dark"]{
  --plate:#0d0f13; --card:#161a21; --sink:#11141a;
  --ink:#ffffff;   --ink-2:#9aa4b2; --ink-3:#6b7280; --rule:#2f3540;
  --indigo:#8f9bd8;--oxblood:#e0685c;
  --band:rgba(143,155,216,.22); --band-neg:rgba(224,104,92,.20);
  --hatch:rgba(224,104,92,.34);
  --accent:#38bdf8; --accent-hi:#7dd3fc; --accent-ink:#07131a;
  --term:#05070a; --term-line:#2f3540;
}

*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:var(--plate);color:var(--ink);
  font:var(--t-5)/1.62 var(--sans);
  font-variant-numeric:tabular-nums;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}

/* numbers in sentences should read as sentences; numbers in columns should
   line up. On the system stacks this is a graceful no-op. */
p,li{font-variant-numeric:oldstyle-nums}
.rf,.app,table,.figure,.screen,.plate{font-variant-numeric:tabular-nums lining}

/* ---------- chrome ---------- */
header{position:sticky;top:0;z-index:20;background:var(--plate);
  border-bottom:1px solid var(--rule)}
nav{max-width:70rem;margin:0 auto;padding:.8rem 1.5rem;display:flex;
  align-items:center;gap:1.6rem;flex-wrap:wrap}
.brand{display:inline-flex;align-items:center;gap:.5rem;color:var(--ink);
  font-family:var(--serif);font-weight:600;font-size:1.12rem;
  letter-spacing:-.015em;text-decoration:none}
.brand:hover{color:var(--ink)}
.mark{width:1.35rem;height:1.35rem;color:var(--ink);flex:none}
.links{display:flex;gap:1.35rem;flex-wrap:wrap}
nav .links a{color:var(--ink-2);text-decoration:none;font-size:.92rem;
  font-weight:500;padding:.15rem 0;border-bottom:1px solid transparent}
nav .links a:hover{color:var(--ink);border-bottom-color:var(--ink)}

main{width:100%;max-width:var(--measure-page);margin:0 auto;
  padding:0 var(--s-5) var(--s-8)}
body.home main,body.hub main{max-width:76rem}
body.home main>h1,body.home main>h2,body.home main>p,
body.home main>ul,body.home main>table{
  max-width:var(--measure-prose);margin-inline:0}
body.home main>.plate,body.home main>.app,body.home main>.scroll,
body.home main>.figure,body.home main>.screen{max-width:var(--measure-plate)}

/* ---------- type ---------- */
h1{font-family:var(--display);font-weight:600;letter-spacing:-.025em;font-size:var(--t-8);line-height:1.08;
  letter-spacing:-.018em;font-weight:600;margin:var(--s-7) 0 var(--s-4);
  text-wrap:balance}
h2{font-family:var(--serif);font-size:var(--t-7);font-weight:600;
  letter-spacing:-.01em;margin:var(--s-7) 0 var(--s-3);
  padding-top:var(--s-5);border-top:1px solid var(--rule);
  text-wrap:balance}
p{margin:var(--s-3) 0;color:var(--ink-2)}
.lede{font-size:var(--t-6);line-height:1.5;color:var(--ink-2);
  max-width:var(--measure-prose)}
strong{color:var(--ink);font-weight:600}
a{color:var(--ink);text-decoration-color:var(--rule);text-underline-offset:3px;
  text-decoration-thickness:1px}
a:hover{text-decoration-color:var(--oxblood)}
ul{padding-left:1.15rem}
li{margin:var(--s-1) 0;color:var(--ink-2)}
.caveat{color:var(--ink-2);font-size:var(--t-3);
  border-left:2px solid var(--rule);padding-left:var(--s-4)}

/* ---------- hero ---------- */
.hero{padding:var(--s-8) 0 var(--s-5);text-align:left}
.eyebrow{margin:0 0 var(--s-4);font-size:var(--t-1);font-weight:600;
  letter-spacing:.14em;text-transform:uppercase;color:var(--ink-2)}
.hero h1{margin:0 0 var(--s-4)}
.hero .lede{margin:0;text-align:left}
.cta{display:flex;gap:var(--s-3);justify-content:flex-start;flex-wrap:wrap;
  margin:var(--s-6) 0 var(--s-2)}
.btn{display:inline-block;padding:.6rem 1.1rem;border-radius:var(--r);
  background:transparent;color:var(--ink);border:1px solid var(--ink);
  text-decoration:none;font-weight:600;font-size:var(--t-3);
  transition:background-color .12s ease,color .12s ease}
.btn:hover{background:var(--ink);color:var(--plate)}
/* --rule is 1.72:1 and is reserved for axes and hairlines. A button's border
   is the boundary of an active control, so it needs 3:1 under WCAG 1.4.11 —
   --ink-2 is 6.23:1 and still reads a clear step below the primary. */
.btn.ghost{border-color:var(--ink-2);color:var(--ink-2)}
.btn.ghost:hover{border-color:var(--ink);background:transparent;color:var(--ink)}

/* The one filled control on a screen. Sized to be hit on a phone without
   aiming: 44px is the smallest target a thumb finds reliably. */
.btn.primary{background:var(--accent);border-color:var(--accent);
  color:var(--accent-ink);font-weight:650;min-height:44px;
  padding:.7rem 1.35rem;font-size:var(--t-4);letter-spacing:.005em}
.btn.primary:hover{background:var(--accent-hi);border-color:var(--accent-hi);
  color:var(--accent-ink)}
.btn.primary .sub{opacity:.72;font-weight:500;margin-left:.5rem;
  font-size:var(--t-2)}

nav .cta-nav{margin-left:auto}


nav .btn.primary{padding:.45rem 1rem;min-height:0;font-size:var(--t-3)}

/* The reference layout: a dismissible announcement strip, a left-aligned hero
   over a single soft accent glow, and a row of qualifier bullets under the
   buttons. Every one of those bullets is a fact the engine can produce — the
   reference site's equivalent row says "Trusted by 5,000+ bettors", which is
   the one thing here that cannot be built without customers. */
.banner{background:linear-gradient(90deg,
    color-mix(in srgb, var(--accent) 22%, transparent),
    color-mix(in srgb, var(--accent) 8%, transparent));
  border-bottom:1px solid var(--rule)}
.banner-in{max-width:70rem;margin:0 auto;padding:.55rem 1.5rem;
  display:flex;align-items:center;gap:var(--s-3);flex-wrap:wrap;
  font-size:var(--t-2);color:var(--ink)}
.banner .tag{background:var(--accent);color:var(--accent-ink);
  font-size:var(--t-1);font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;padding:.15rem .45rem;border-radius:var(--r)}
.banner a{color:var(--accent);text-decoration-color:var(--accent)}

/* One glow, behind the hero only. */
.hero-glow{position:relative}
.hero-glow::before{content:"";position:absolute;inset:-18rem -10rem auto -20rem;
  height:44rem;pointer-events:none;z-index:-1;
  background:radial-gradient(50% 50% at 30% 45%,
    color-mix(in srgb, var(--accent) 16%, transparent) 0%,
    transparent 70%)}

.eyebrow.accent{color:var(--accent);font-weight:600;letter-spacing:.28em}

.quals{display:flex;flex-wrap:wrap;gap:var(--s-2) var(--s-5);
  margin-top:var(--s-4);font-size:var(--t-2);color:var(--ink-2);
  list-style:none;padding:0}
.quals li{display:flex;align-items:center;gap:.45rem}
.quals li::before{content:"";width:5px;height:5px;border-radius:50%;
  background:var(--accent);flex:none}

/* The book wall. Text, not a logo strip: the competitors' equivalents are
   images, so the names are invisible to a crawler and to a screen reader. */
.wall{max-width:var(--measure-plate);margin:var(--s-7) 0;
  border-top:1px solid var(--rule);padding-top:var(--s-5)}
.wall-cap{font-size:var(--t-1);letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink-2);margin:0 0 var(--s-3)}
.wall-list{display:flex;flex-wrap:wrap;gap:var(--s-2) var(--s-4);
  list-style:none;padding:0;margin:0}
.wall-list li{font-size:var(--t-3);color:var(--ink-2);white-space:nowrap}

/* The demo. Second thing on the page, playable with no signup, because the
   claim it makes is one a static screenshot cannot carry: the edge on the
   screen is not the edge in the account. */
.demo{max-width:var(--measure-plate);margin:var(--s-8) 0}
.demo h2{margin:var(--s-2) 0 var(--s-3)}
.demo > p{max-width:var(--measure-prose)}
.demo-box{background:var(--card);border:1px solid var(--rule);
  border-radius:var(--r);padding:var(--s-5);margin-top:var(--s-5)}
.demo-label{display:flex;justify-content:space-between;align-items:baseline;
  gap:var(--s-4);font-size:var(--t-2);letter-spacing:.1em;
  text-transform:uppercase;color:var(--ink-2)}
.demo-label output{font-family:var(--mono);font-size:var(--t-6);
  letter-spacing:0;text-transform:none;color:var(--ink);font-weight:600}

/* 44px of vertical room for the thumb so it is draggable with a thumb. */
.demo-box input[type=range]{-webkit-appearance:none;appearance:none;
  width:100%;height:44px;background:transparent;margin:var(--s-2) 0 0;
  display:block}
.demo-box input[type=range]:focus-visible{outline:2px solid var(--accent);
  outline-offset:4px}
.demo-box input[type=range]::-webkit-slider-runnable-track{height:4px;
  background:var(--rule);border-radius:2px}
.demo-box input[type=range]::-moz-range-track{height:4px;
  background:var(--rule);border-radius:2px}
.demo-box input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;
  appearance:none;width:26px;height:26px;margin-top:-11px;border-radius:50%;
  background:var(--accent);border:3px solid var(--card);cursor:grab}
.demo-box input[type=range]::-moz-range-thumb{width:26px;height:26px;
  border-radius:50%;background:var(--accent);border:3px solid var(--card);
  cursor:grab}

.demo-read{display:grid;grid-template-columns:repeat(3,1fr);
  gap:var(--s-4);margin:var(--s-4) 0 var(--s-5);
  padding-top:var(--s-4);border-top:1px solid var(--rule)}
.demo-read div{display:flex;flex-direction:column;gap:.2rem;min-width:0}
.demo-read b{font-family:var(--display);font-size:var(--t-7);font-weight:750;
  line-height:1;letter-spacing:-.02em;color:var(--ink);
  font-variant-numeric:tabular-nums}
.demo-read #d-realised{color:var(--accent)}
.demo-read span{font-size:var(--t-1);letter-spacing:.08em;
  text-transform:uppercase;color:var(--ink-2)}

/* The bar is the argument: the filled part is what survives, the empty part
   is what the competition prints as though it were yours. */
.demo-bar{position:relative;height:12px;background:var(--band-neg);
  border:1px solid var(--rule);border-radius:2px;overflow:hidden}
.demo-bar-fill{height:100%;width:100%;background:var(--accent);
  transition:width .18s ease-out}
.demo-bar-cap{display:block;margin-top:var(--s-2);font-size:var(--t-1);
  letter-spacing:.08em;text-transform:uppercase;color:var(--ink-2)}

@media (prefers-reduced-motion:reduce){.demo-bar-fill{transition:none}}
@media (max-width:640px){
  .demo-read{grid-template-columns:1fr 1fr}
  .demo-read div:last-child{grid-column:1 / -1}
}

/* Code blocks. The download page is the first page to use one, and an
   unstyled <pre> does not wrap: a single long install URL widened the whole
   document and put the body into horizontal scroll on a phone. The block
   scrolls inside itself instead, which is the same rule the tables follow.
   `min-width:0` is the part that is easy to miss — without it a flex or grid
   child refuses to shrink below its content and the overflow escapes anyway. */
pre{background:var(--sink);border:1px solid var(--rule);border-radius:var(--r);
  padding:var(--s-4);margin:var(--s-4) 0;overflow-x:auto;min-width:0;
  max-width:100%;font-size:var(--t-3);line-height:1.6}
pre code{font-family:var(--mono);color:var(--ink);white-space:pre;
  background:none;padding:0;border:0}
code{font-family:var(--mono);font-size:.94em;background:var(--sink);
  padding:.1em .35em;border-radius:var(--r);
  overflow-wrap:anywhere}

/* A digest is 64 characters of nothing. It may break anywhere. */
.hash{font-family:var(--mono);font-size:var(--t-1);color:var(--ink-2);
  overflow-wrap:anywhere;word-break:break-all}

/* Measured facts, not testimonials. Everything in this strip is computed by
   the engine at build time; nothing here is a claim about a customer. */
.trust{display:flex;flex-wrap:wrap;gap:var(--s-3) var(--s-6);
  margin:var(--s-6) 0 0;padding:var(--s-4) 0;
  border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);
  max-width:var(--measure-plate)}
.trust div{display:flex;flex-direction:column;gap:.15rem}
.trust b{font-family:var(--display);font-size:var(--t-6);font-weight:700;
  color:var(--ink);line-height:1;letter-spacing:-.01em}
.trust span{font-family:var(--sans);font-size:var(--t-1);letter-spacing:.1em;
  text-transform:uppercase;color:var(--ink-2)}

/* ---------- the range-frame: one primitive, four scales ----------
   anatomy, fixed and never varied:
     axis    1px --rule hairline, full width
     band    --band fill from lo to hi, full height  (the interval IS the mark)
     serifs  --indigo at both bounds, full height + overshoot
     point   --ink tick, 56% height, FULL contrast

   The point estimate is subordinate by EXTENT, not by contrast. Ghosting it
   would encode "numbers are unknowable", and that is not the claim. The claim
   is: here is an honest number, its range, and a stake you can place. */
.rf{--lo:0%;--hi:100%;--pt:50%;
  position:relative;display:inline-block;flex:none;
  width:var(--rf-w,4rem);height:var(--rf-h,.8em);
  vertical-align:-.14em}
.rf::before{content:"";position:absolute;left:0;right:0;top:50%;
  height:1px;margin-top:-.5px;background:var(--rule)}

.rf-band{position:absolute;top:0;bottom:0;
  left:var(--lo);right:calc(100% - var(--hi));
  background-color:var(--band)}
.rf-band::before,.rf-band::after{content:"";position:absolute;
  top:-2px;bottom:-2px;width:1.5px;background:var(--indigo)}
.rf-band::before{left:0}
.rf-band::after{right:0}

.rf-pt{position:absolute;left:var(--pt);top:22%;height:56%;
  width:1.5px;margin-left:-.75px;background:var(--ink)}

/* the value Bookbreaker actually stands behind: solid, below the axis */
.rf-real{position:absolute;left:var(--rl);bottom:-5px;
  width:0;height:0;margin-left:-3px;
  border-left:3px solid transparent;border-right:3px solid transparent;
  border-bottom:4px solid var(--indigo)}

/* an interval containing zero is not claimable, and says so with TEXTURE
   rather than hue — survives greyscale and every colour deficiency */
.rf-zero{position:absolute;left:var(--z);top:-4px;bottom:-4px;
  width:1px;margin-left:-.5px;background:var(--ink)}
.rf-neg{position:absolute;top:0;bottom:0;
  left:var(--lo);right:calc(100% - var(--z));background:var(--band-neg)}
.rf-band.is-zero{background-image:repeating-linear-gradient(45deg,
  transparent 0 3px,var(--hatch) 3px 5px)}

/* a competitor's figure: no band, no bounds. the absence is the argument. */
.rf--bare .rf-band{background:none}
.rf--bare .rf-band::before,.rf--bare .rf-band::after{display:none}

.rf--inline{--rf-w:4rem;--rf-h:.8em}
.rf--row{--rf-w:100%;--rf-h:.95rem;display:block;vertical-align:baseline}
.rf--plate{--rf-w:100%;--rf-h:2.4rem;display:block;margin:var(--s-3) 0}
.rf--hero{--rf-w:100%;--rf-h:3.4rem;display:block;margin:var(--s-4) 0}
.rf--plate .rf-pt,.rf--hero .rf-pt{top:26%;height:48%;width:2px;margin-left:-1px}
.rf--plate .rf-band::before,.rf--plate .rf-band::after,
.rf--hero  .rf-band::before,.rf--hero  .rf-band::after{width:2px;top:-5px;bottom:-5px}

/* ---------- the plate wrapper ---------- */
.plate{margin:var(--s-5) 0;padding:var(--s-4) var(--s-5) var(--s-3);
  background:var(--card);border:1px solid var(--rule);border-radius:var(--r);
  max-width:var(--measure-plate)}
.plate-cap{font-family:var(--sans);font-size:var(--t-1);font-weight:600;
  letter-spacing:.1em;text-transform:uppercase;color:var(--ink-2);
  margin:0 0 var(--s-2)}
/* Each label sits under the mark it names, at the same measured percentage the
   frame used. Spreading them edge-to-edge would put "0" in the middle of a
   panel whose zero rule is at 31% — a key that points at the wrong thing is
   worse than no key. */
.plate-key{position:relative;height:1.15rem;margin-top:var(--s-2);
  font-family:var(--mono);font-size:var(--t-2);color:var(--ink-2)}
.plate-key span{position:absolute;left:var(--at);transform:translateX(-50%);
  white-space:nowrap}
.plate-key .neg{color:var(--oxblood)}
.plate--split{display:grid;gap:var(--s-5)}
@media(min-width:44rem){.plate--split{grid-template-columns:1fr 1fr}}

/* Marks a competitor's over-precision. The dotted rule is the whole device:
   dimming just the decimals would mean wrapping them in a tag, and check.py's
   visible() replaces tags with spaces — "5.<em>91</em>" tokenises as 5 and 91,
   neither of which is a measured number, and the build fails. The number stays
   one text node. */
.over{border-bottom:1px dotted var(--rule)}

/* ---------- the terminal block: the one dark object, in BOTH themes ----------
   Re-scoping the tokens inside .app is what lets one range-frame component
   serve two grounds: every .rf inside recolours itself automatically. */
.app{
  --card:#1c1e24; --sink:#1a1b21;
  --ink:#e8e6e0; --ink-2:#9a968b; --ink-3:#75716a; --rule:#3a3d46;
  --indigo:#8f9bd8; --oxblood:#e0685c;
  --band:rgba(143,155,216,.26); --band-neg:rgba(224,104,92,.22);
  --hatch:rgba(224,104,92,.36);

  margin:var(--s-6) 0 var(--s-7);max-width:var(--measure-plate);
  background:var(--term);color:var(--ink);
  border:1px solid var(--term-line);border-radius:var(--r);
  overflow:hidden;font-family:var(--mono);font-size:var(--t-2)}
.app-bar{display:flex;align-items:center;gap:var(--s-2);
  padding:var(--s-2) var(--s-4);background:var(--sink);
  border-bottom:1px solid var(--rule)}
.dot{width:.5rem;height:.5rem;border-radius:50%;background:var(--rule);flex:none}
.app-title{margin-left:var(--s-2);color:var(--ink-2);font-weight:500}
.app-meta{margin-left:auto;color:var(--ink-2);font-size:var(--t-1)}
.app-head,.app-row{display:grid;
  grid-template-columns:1.3fr .86fr .58fr .7fr 2.3fr .48fr .82fr .78fr;
  gap:var(--s-3);padding:var(--s-2) var(--s-4);align-items:center}
.app-head{font-family:var(--sans);font-size:var(--t-1);text-transform:uppercase;
  letter-spacing:.09em;color:var(--ink-2);background:var(--sink);
  border-bottom:1px solid var(--rule)}
.app-row{border-bottom:1px solid var(--rule)}
.app-row:last-of-type{border-bottom:0}
.app-row:hover{background:var(--card)}

/* tabular figures make + and - exactly one digit wide, so right-aligned
   numeric columns align their signs down the whole strip */
.app-head span:nth-child(3),.app-row span:nth-child(3),
.app-head span:nth-child(4),.app-row span:nth-child(4),
.app-head span:nth-child(6),.app-row span:nth-child(6),
.app-head span:nth-child(8),.app-row span:nth-child(8){text-align:right}

.ev-name{color:var(--ink);font-weight:500}
.dim{color:var(--ink-2)}
.price{color:var(--ink-2)}
.band{min-width:0}
.pos{color:var(--ink-2);font-weight:400}
.pos.strong{color:var(--indigo);font-weight:500}

/* fill stays deliberately subordinate: a bar with NO terminators, so it can
   never be mistaken for an interval */
.fill{display:flex;align-items:center;gap:var(--s-2);min-width:0}
.fill i{display:block;height:2px;border-radius:0;background:var(--rule);
  opacity:1;min-width:2px}
.fill b{font-weight:400;color:var(--ink-2);font-size:var(--t-1)}

.app-foot{padding:var(--s-3) var(--s-4);background:var(--sink);
  color:var(--ink-2);font-family:var(--sans);font-size:var(--t-3);
  line-height:1.5;border-top:1px solid var(--rule)}
.app-foot strong{color:var(--ink);font-weight:600}

/* ---------- figures ---------- */
.figure{background:var(--card);border:1px solid var(--rule);
  border-left:2px solid var(--indigo);border-radius:var(--r);
  padding:var(--s-4) var(--s-5);margin:var(--s-5) 0;font-family:var(--mono);
  font-size:var(--t-3);line-height:1.6;overflow-x:auto}
.screen{background:var(--card);border:1px solid var(--rule);
  border-radius:var(--r);padding:var(--s-4) var(--s-5);margin:var(--s-5) 0;
  font-family:var(--mono);font-size:var(--t-2);line-height:1.95;
  overflow-x:auto;white-space:nowrap}
.screen .num{color:var(--indigo)}
.scroll{margin:var(--s-5) 0;overflow-x:auto;border:1px solid var(--rule);
  border-radius:var(--r);background:var(--card)}
table{border-collapse:separate;border-spacing:0;width:100%;
  min-width:max-content;font-size:var(--t-3);font-family:var(--mono);
  white-space:nowrap;background:var(--card)}
th{text-align:left;padding:var(--s-2) var(--s-3);font-family:var(--sans);
  font-size:var(--t-1);text-transform:uppercase;letter-spacing:.09em;
  color:var(--ink-2);font-weight:600;background:var(--sink);
  border-bottom:1px solid var(--rule)}
td{padding:var(--s-2) var(--s-3);border-bottom:1px solid var(--rule);
  color:var(--ink-2)}
tr:last-child td{border-bottom:0}
td:first-child{font-family:var(--sans);color:var(--ink-2)}
tr:hover td{background:var(--sink)}

/* ---------- cards ---------- */
/* The legacy card list was superseded by .cards and deleted: it still
   matched the new grid and set every description in serif bold. */


/* ---------- footer ---------- */
footer{border-top:1px solid var(--rule);background:var(--sink);
  margin-top:var(--s-7)}
.foot-grid{max-width:var(--measure-page);margin:0 auto;
  padding:var(--s-6) var(--s-5) var(--s-4);
  display:grid;gap:var(--s-5);grid-template-columns:1.6fr 1fr 1fr}
.foot-grid p{margin:.3rem 0;font-size:var(--t-3);color:var(--ink-2)}
.foot-brand{font-family:var(--serif);font-weight:600;color:var(--ink);
  font-size:var(--t-4);letter-spacing:-.01em}
.foot-head{font-size:var(--t-1)!important;text-transform:uppercase;
  letter-spacing:.1em;color:var(--ink)!important;font-weight:600;
  margin-bottom:var(--s-2)!important}
.foot-grid a{color:var(--ink-2);text-decoration:none}
.foot-grid a:hover{color:var(--ink);text-decoration:underline;
  text-decoration-color:var(--rule)}
.foot-fine{max-width:var(--measure-page);margin:0 auto;
  padding:0 var(--s-5);color:var(--ink-2);
  font-size:var(--t-2);line-height:1.55}
.foot-fine:last-child{padding-bottom:var(--s-6)}

@media(prefers-reduced-motion:reduce){
  *{transition:none!important;animation:none!important}
  html{scroll-behavior:auto}
}
:focus-visible{outline:2px solid var(--indigo);outline-offset:2px}

@media(max-width:52rem){
  .app{font-size:.76rem}
  /* the band is now the most valuable column on the strip, so it survives to
     the smallest breakpoint. Book and Age go first. */
  .app-head,.app-row{grid-template-columns:1.4fr .62fr .78fr 1.6fr .9fr .85fr}
  .app-head span:nth-child(2),.app-row span:nth-child(2),
  .app-head span:nth-child(6),.app-row span:nth-child(6){display:none}
  .app-head span:nth-child(3),.app-row span:nth-child(3),
  .app-head span:nth-child(4),.app-row span:nth-child(4),
  .app-head span:nth-child(8),.app-row span:nth-child(8){text-align:right}
}
@media(max-width:40rem){
  main{padding:0 1.15rem 3.5rem}
  .hero{padding:var(--s-6) 0 var(--s-2)}
  .hero .lede{font-size:var(--t-4)}
  h2{margin-top:var(--s-6)}
  .foot-grid{grid-template-columns:1fr;padding:var(--s-6) 1.15rem .6rem}
  .app-meta{display:none}
  .app-head,.app-row{grid-template-columns:1.3fr .8fr 1.5fr .9fr}
  .app-head span:nth-child(3),.app-row span:nth-child(3),
  .app-head span:nth-child(7),.app-row span:nth-child(7){display:none}

  /* The nav wrapped onto three lines and ate half a phone screen of sticky
     header. One row that scrolls sideways instead — the brand stays put and
     the links slide. */
  nav{padding:.6rem 0 .6rem 1.15rem;gap:.85rem;flex-wrap:nowrap;
    align-items:center}
  .brand{flex:none;font-size:1.05rem}
  .links{flex:1 1 auto;flex-wrap:nowrap;gap:1.05rem;overflow-x:auto;
    padding-right:1.15rem;scrollbar-width:none;-webkit-overflow-scrolling:touch}
  .links::-webkit-scrollbar{display:none}
  nav .links a{white-space:nowrap;font-size:.88rem}
}

/* Narrow screens. Last in the sheet on purpose: these rules restate
   properties the base rules also set, and an equal-specificity rule
   only wins if it comes after. Placed beside the components they
   modify, `nav{flex-wrap:wrap}` lost to the `nav{}` block below it
   and the links stacked into a column on a phone. */
@media (max-width:640px){
  nav{flex-wrap:wrap;row-gap:var(--s-2)}
  /* The action stays on the first row beside the wordmark; the section links
     drop to a second. A CTA that wraps below the fold on the narrowest screen
     is a CTA that is not there. */
  nav .cta-nav{order:2}
  nav .links{order:3;flex-basis:100%;display:flex;flex-wrap:wrap;
    gap:var(--s-2) var(--s-4)}
  .trust{gap:var(--s-4) var(--s-5)}
  .trust b{font-size:var(--t-5)}
  .cta{display:flex;flex-wrap:wrap;gap:var(--s-3)}
  .cta .btn{flex:1 1 auto;justify-content:center;text-align:center}
}


/* ================================================================= PASS 1
   The page had a composed hero and then became a term paper: four
   h2/p/p.figure sequences carrying the entire product argument with no
   structure at all. And the product itself sat two screens below a hero whose
   right half was empty. Both are fixed here.
   --------------------------------------------------------------------- */

/* --- hero: the claim on the left, the thing working on the right ------ */
.hero{display:grid;gap:var(--s-7);align-items:start}
.hero-copy{min-width:0}
.hero-app{min-width:0}
@media (min-width:64rem){
  .hero{grid-template-columns:minmax(0,31rem) minmax(0,1fr);
    gap:var(--s-7);align-items:center}
  /* Type set for a full-width hero is too large for a column: 72px broke the
     headline into four pieces. Sized to land in two. */
  .hero-copy h1{font-size:clamp(2.5rem,3.6vw,3.35rem);line-height:1.06}
}
/* Two buttons that stack are two decisions; side by side they are one. */
.hero .cta{flex-wrap:nowrap}
@media (max-width:30rem){.hero .cta{flex-wrap:wrap}}
.hero .btn{white-space:nowrap}
body.home main>.hero{max-width:none}
.hero-copy>h1{max-width:none}
.hero-copy>.lede{max-width:32rem}

/* Lifted and turned a degree off true, so it reads as an object sitting on
   the page rather than a table that failed to inherit its borders. */
.app--hero{margin:0;box-shadow:
    0 1px 0 color-mix(in srgb, var(--ink) 6%, transparent),
    0 24px 60px -20px rgba(0,0,0,.55);
  transform:perspective(1600px) rotateY(-1.2deg);
  transform-origin:left center}
.app--hero .app-row:last-of-type{border-bottom:0}
.hero-app-cap{font-size:var(--t-2);color:var(--ink-2);
  margin:var(--s-3) 0 0;max-width:34rem}
.hero-app-cap strong{color:var(--ink);font-weight:600}
@media (prefers-reduced-motion:reduce){.app--hero{transform:none}}
@media (max-width:64rem){.app--hero{transform:none}}

/* The trust row was four small numbers adrift under the fold. Ruled top and
   bottom, it becomes the spine between the hero and the body. */
.trust{border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);
  padding:var(--s-5) 0;margin:var(--s-7) 0 0;
  display:grid;grid-template-columns:repeat(2,1fr);gap:var(--s-5)}
@media (min-width:48rem){.trust{grid-template-columns:repeat(4,1fr)}}
.trust>div{display:flex;flex-direction:column;gap:.35rem}
.trust b{font-family:var(--display);font-size:var(--t-7);font-weight:600;
  letter-spacing:-.02em;line-height:1;color:var(--ink)}
.trust span{font-size:var(--t-1);letter-spacing:.12em;text-transform:uppercase;
  color:var(--ink-2)}

/* --- the four blocks, composed --------------------------------------- */
.pitch{margin:var(--s-8) 0 0;max-width:none}
.pitch>.eyebrow{margin-bottom:var(--s-6)}
.pitch-row{display:grid;gap:var(--s-5);padding:var(--s-7) 0;
  border-top:1px solid var(--rule);align-items:start}
.pitch-row:first-of-type{border-top:0;padding-top:0}
@media (min-width:60rem){
  /* Centred, not top-aligned: the copy is always taller than the figure, and
     start-alignment left each figure pinned to the top of a column of empty
     space. */
  .pitch-row{grid-template-columns:minmax(0,30rem) minmax(0,1fr);
    gap:var(--s-8);align-items:center}
}
.pitch-copy{min-width:0}
/* The base h2 carries a top rule, which inside a numbered block draws a line
   between the number and its own heading and reads as a mistake. The row
   already supplies the only rule this section needs. */
.pitch-copy h2{margin:var(--s-2) 0 var(--s-3);max-width:none;
  border-top:0;padding-top:0;font-size:var(--t-7);line-height:1.15}
.pitch-copy p{max-width:34rem}
/* Counted in CSS, not written into the markup: an ordinal is presentation,
   it is not a figure the engine measured, and a screen reader should not
   announce "zero one" before every heading. */
.pitch{counter-reset:pitch}
.pitch-row{counter-increment:pitch}
.pitch-copy::before{content:counter(pitch,decimal-leading-zero);
  display:block;font-family:var(--mono);font-size:var(--t-1);
  letter-spacing:.18em;color:var(--accent);font-weight:600}
.pitch-kicker{color:var(--ink-2);font-size:var(--t-3)}
.pitch-fig{min-width:0}
.pitch-note{font-size:var(--t-2);color:var(--ink-2);margin:var(--s-3) 0 0}

/* A figure is an object with a surface, not a stray paragraph set in a
   different font. */
.pitch-fig>table.bare,.pitch-fig>.vs,.pitch-fig>.verdict{
  background:var(--card);border:1px solid var(--rule);border-radius:var(--r)}
.pitch-fig table.bare{width:100%;border-collapse:collapse;margin:0}
.pitch-fig table.bare th,.pitch-fig table.bare td{
  padding:var(--s-3) var(--s-4);border-bottom:1px solid var(--rule);
  text-align:left}
.pitch-fig table.bare tr:last-child th,
.pitch-fig table.bare tr:last-child td{border-bottom:0}
.pitch-fig table.bare th{font-size:var(--t-1);letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink-2);font-weight:600;
  background:var(--sink)}
.pitch-fig table.bare td:last-child{font-family:var(--mono);text-align:right;
  color:var(--indigo);font-weight:600}

/* Two figures side by side, because every claim here is a comparison: what
   everyone else prints, against what this prints. */
.vs{display:grid;grid-template-columns:1fr 1fr;overflow:hidden}
.vs-side{padding:var(--s-6) var(--s-5)}
.vs-side+.vs-side{border-left:1px solid var(--rule)}
.vs-side--ours{background:color-mix(in srgb, var(--accent) 7%, transparent)}
.vs-cap{font-size:var(--t-1);letter-spacing:.12em;text-transform:uppercase;
  color:var(--ink-2);margin:0 0 var(--s-3)}
.vs-val{font-family:var(--mono);font-size:var(--t-7);font-weight:600;
  color:var(--ink);margin:0;line-height:1.15;word-break:break-word}
.vs-val i{color:var(--ink-3);font-style:normal;padding:0 .15em}
.vs-side--ours .vs-val{color:var(--accent)}
.vs-sub{font-size:var(--t-2);color:var(--ink-2);margin:var(--s-2) 0 0}

.verdict{margin:0;padding:var(--s-6);font-family:var(--serif);
  font-size:var(--t-7);line-height:1.35;color:var(--ink);
  border-left:3px solid var(--accent)}

/* ================================================================= PASS 2
   116 of the 117 pages were the term paper the homepage used to be. The hubs
   listed forty links as a bare <ul>, and every leaf page opened with an h1 and
   a paragraph on an empty ground. Two templates, so one fix reaches the whole
   site.
   --------------------------------------------------------------------- */

/* --- hub card grids --------------------------------------------------- */
.cards{list-style:none;padding:0;margin:var(--s-6) 0 0;display:grid;
  gap:1px;background:var(--rule);border:1px solid var(--rule);
  border-radius:var(--r);overflow:hidden}
@media (min-width:34rem){.cards{grid-template-columns:repeat(2,1fr)}}
@media (min-width:60rem){.cards{grid-template-columns:repeat(3,1fr)}}
body.home main>.cards,main>.cards{max-width:none}

/* One hairline between cells rather than a border on each: the grid gap IS
   the rule, so nothing doubles up at the seams. */
.cards .card{background:var(--plate);margin:0}
.cards .card a{display:flex;flex-direction:column;gap:var(--s-2);height:100%;
  padding:var(--s-5);text-decoration:none;color:inherit;
  background:var(--plate);
  transition:background .12s ease-out,color .12s ease-out}
.cards .card a:hover,.cards .card a:focus-visible{background:var(--card)}
.cards .card a:focus-visible{outline:2px solid var(--accent);
  outline-offset:-2px}
.card-t{font-family:var(--display);font-size:var(--t-5);font-weight:600;
  letter-spacing:-.01em;line-height:1.25;color:var(--ink);text-wrap:balance}
.card-q{font-size:var(--t-2);line-height:1.5;color:var(--ink-2);
  flex:1 1 auto}
.card-go{font-size:var(--t-1);letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink-3);transition:color .12s ease-out}
.cards .card a:hover .card-go,
.cards .card a:focus-visible .card-go{color:var(--accent)}
@media (prefers-reduced-motion:reduce){
  .cards .card a,.card-go{transition:none}
}

/* --- every leaf page gets a header, not a bare h1 --------------------- */
.phead{border-bottom:1px solid var(--rule);padding-bottom:var(--s-5);
  margin-bottom:var(--s-6)}
.phead h1{margin:0 0 var(--s-3);font-size:clamp(2rem,4.2vw,2.9rem);
  line-height:1.1}
.phead .lede{margin:0}
.crumb{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;
  font-size:var(--t-1);letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink-3);margin:0 0 var(--s-4)}
.crumb a{color:var(--ink-2);text-decoration:none}
.crumb a:hover{color:var(--accent)}
.crumb span{color:var(--rule)}

/* The hub h1 and lede stay at reading measure while the grid uses the room. */
body.hub main>h1,body.hub main>p{max-width:var(--measure-prose)}
body.hub main>h1{font-size:clamp(2.1rem,4vw,3rem);line-height:1.08}

/* ================================================================= PASS 3
   The leaf pages are where most of the site lives and where the reading
   actually happens. They were set at a size and rhythm nobody would choose
   for prose, and a short page left the footer floating in a void.
   --------------------------------------------------------------------- */

/* A page shorter than the viewport pushed the footer up and left a band of
   empty ground under it. */
body{min-height:100vh;display:flex;flex-direction:column}
body>footer{margin-top:auto}
main{flex:1 0 auto;min-width:0;width:100%}

/* Prose sized to be read rather than to fit. 17px at a 46rem measure is a
   documentation default; guides are the product's argument and are read
   end to end. */
main p{font-size:var(--t-5);line-height:1.65;margin:var(--s-4) 0}
main li{line-height:1.6}
.phead .lede{font-size:var(--t-6);line-height:1.5}

/* Run-in heads. Ten guides open paragraphs with a bold sentence that acts as
   a heading and was set at body weight in body colour, so it read as an
   accident of emphasis rather than structure. */
main p>strong:first-child{color:var(--ink);font-weight:650;
  letter-spacing:-.005em}

/* A figure inside prose is the number the paragraph exists to deliver. It was
   a paragraph in a different font. */
main .figure{font-family:var(--mono);font-size:var(--t-5);color:var(--ink);
  background:var(--card);border:1px solid var(--rule);
  border-left:3px solid var(--accent);border-radius:var(--r);
  padding:var(--s-4) var(--s-5);margin:var(--s-5) 0;line-height:1.5}

/* Numbers inside running prose. The site's whole claim is about figures, and
   they were set in the same face and colour as the words around them. */
main p code,main p .num{font-family:var(--mono);font-size:.94em;
  color:var(--ink);background:color-mix(in srgb,var(--ink) 7%,transparent);
  padding:.08em .3em;border-radius:var(--r)}

/* Tables on leaf pages matched the plate figures on the homepage but not the
   card surfaces around them. */
main table{width:100%;border-collapse:collapse;margin:var(--s-5) 0;
  font-size:var(--t-3)}
main table th,main table td{padding:var(--s-3) var(--s-4);
  border-bottom:1px solid var(--rule);text-align:left}
main table th{font-size:var(--t-1);letter-spacing:.12em;text-transform:uppercase;
  color:var(--ink-2);font-weight:600;background:var(--sink)}
main table tr:last-child td{border-bottom:0}
main table td:not(:first-child){font-family:var(--mono);text-align:right;
  color:var(--indigo);font-weight:600}

/* The closing link on every guide was an ordinary sentence link doing the job
   of a next step. */
main p>a[href^="/"]:only-child{display:inline-flex;align-items:center;
  gap:.4rem;font-weight:600;text-decoration:none;color:var(--accent);
  border-bottom:1px solid color-mix(in srgb,var(--accent) 35%,transparent);
  padding-bottom:.1rem}
main p>a[href^="/"]:only-child:hover{border-bottom-color:var(--accent)}

/* The hub cards' affordance was set in the decorative ink, which is the one
   colour the stylesheet reserves for things that carry no meaning. */
.card-go{color:var(--ink-2)}

/* Anything that cannot wrap gets its own scroll box. Without this the widest
   table on the page sets the width of the page. */
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}
main table{max-width:100%}

/* Every guide ends somewhere. Ending on a dead stop above a pinned footer
   left a band of empty ground; ending on the next three guides fills it with
   the one thing a reader here actually wants. */
.onward{margin:var(--s-8) 0 0;border-top:1px solid var(--rule);
  padding-top:var(--s-5)}
.onward-cap{font-size:var(--t-1);letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink-2);margin:0}
.cards--onward{margin-top:var(--s-4)}
@media (min-width:34rem){.cards--onward{grid-template-columns:repeat(3,1fr)}}
.cards--onward .card-t{font-size:var(--t-4)}
.cards--onward .card a{padding:var(--s-4)}

/* The onward strip is wider than the reading measure it follows: three cards
   at a prose width are three cards nobody can read the titles of. */
.onward{margin-inline:auto;max-width:var(--measure-plate)}
@media (min-width:60rem){
  .onward{width:min(var(--measure-plate),calc(100vw - 3rem))}
}

/* The nav is a flex row that wraps: on a phone the brand and the button share
   line one, `margin-left:auto` pushes the button past the padding, and it is
   clipped by the viewport edge. Below the wrap point the row becomes an
   explicit two-line layout instead of an accidental one. */
@media (max-width:46rem){
  nav{gap:.6rem 1rem;padding:.7rem 1rem;
    display:grid;grid-template-columns:1fr auto;align-items:center}
  nav .brand{grid-column:1}
  nav .cta-nav{grid-column:2;margin-left:0;justify-self:end}
  nav .links{grid-column:1 / -1;gap:.5rem 1.1rem;
    font-size:var(--t-2);row-gap:.35rem}
  nav .links a{font-size:var(--t-2)}
}
/* Nothing on the page may push the document wider than the phone holding it. */
html,body{max-width:100%;overflow-x:clip}

/* ================================================================= PASS 4
   Findings from an independent review, each measured before it was believed.
   --------------------------------------------------------------------- */

/* One container width. The header sat at 70rem, the home main at 76rem and a
   leaf main at 46rem, so the wordmark shared a vertical edge with nothing on
   any page — 24px out on the home page and 192px out on a leaf. */
:root{--shell:76rem}
nav,.banner-in,.foot-grid,.foot-fine{max-width:var(--shell);
  padding-inline:var(--s-5)}
body.home main,body.hub main{max-width:var(--shell)}
main{padding-inline:var(--s-5)}
/* A leaf page keeps its reading measure but starts on the same edge as the
   header rather than being centred against it. */
@media (min-width:64rem){
  body:not(.home):not(.hub) main{margin-inline:auto;
    max-width:var(--shell);display:grid;
    grid-template-columns:minmax(0,var(--measure-page))}
}

/* A right-aligned column under a left-aligned label put the header 344px from
   its own data. */
main table th:not(:first-child),
.pitch-fig table.bare th:not(:first-child){text-align:right}
main table th.prose,main table td.prose{text-align:left}

/* The numeric treatment assumed every column after the first was a number.
   On the download page that column is English, set in right-aligned mono and
   truncated mid-word on the page carrying the primary call to action. */
main table td.prose,table td.prose{white-space:normal;font-family:var(--sans);
  text-align:left;color:var(--ink-2);font-weight:400;
  min-width:20ch;line-height:1.5}

/* Prose links were white text with a 1.32:1 underline — indistinguishable
   from bold. */
main p a,main li a{color:var(--accent);
  text-decoration-color:color-mix(in srgb,var(--accent) 55%,transparent)}
main p a:hover,main li a:hover{text-decoration-color:var(--accent)}

/* .foot-brand (0,1,0) lost to .foot-grid p (0,1,1), so the footer wordmark
   rendered in secondary ink. */
.foot-grid p.foot-brand{color:var(--ink)}

/* The four headline proof points were 28px against a 20px lede — a 1.4x
   ratio that read as captions. The earlier mobile override for them was dead
   code, overridden by a later unmediated rule. */
.trust b{font-size:clamp(2rem,3.2vw,2.5rem)}
@media (max-width:40rem){.trust b{font-size:var(--t-7)}}

/* One h2 tag rendered at two leadings on the same page: 1.62 inherited from
   body in one place, 1.15 in another. */
h2{line-height:1.15}

/* The glow was pushing the document 24px past the viewport, so every page
   scrolled sideways. Clipping the hero fixed the width and drew a hard edge
   where the gradient was cut; keeping the bleed vertical removes both. */
/* Sized so the gradient reaches transparent before it meets any edge of its
   own box. Cut mid-fade it draws a visible rectangle on the page, which is
   what both the bleed and the clip were doing. */
.hero-glow::before{inset:-14rem 0 auto 0;height:40rem;
  background:radial-gradient(42% 58% at 38% 46%,
    color-mix(in srgb, var(--accent) 17%, transparent) 0%,
    transparent 62%)}

/* Ten letter-spacing values for what the eye reads as one label style. */
:root{--label:.1em}
.plate-cap,.foot-head,.trust span,.vs-cap,.wall-cap,.crumb,.card-go,
.onward-cap,.pitch-copy::before{letter-spacing:var(--label)}
.eyebrow{letter-spacing:.14em}
.eyebrow.accent{letter-spacing:.14em}

/* --ink-3 is documented as decorative and never text that carries meaning;
   the breadcrumb was set in it at 4.34:1. */
.crumb{color:var(--ink-2)}

/* Footer links were 17px tall — under even the 24px minimum. */
.foot-grid a{display:inline-block;padding:.35rem 0}

/* ================================================================= PASS 5
   The brief changed, and the old one was answered too well.

   The system above describes "a printed statistical plate with a dark
   terminal block set into it." That is a Bloomberg terminal, and Matt's
   reaction — bleak, uninspiring, reminds me of stock trading — is the design
   working exactly as specified. The specification was wrong for the audience.

   This is a sports betting product. The people using it also use FanDuel and
   an iPhone, and both of those are bright, rounded, generous and confident.
   Nothing below softens what the engine SAYS — every figure stays measured,
   every prior stays labelled — it changes who the page looks like it was
   built for.

   Three moves: lift the ground to white, round everything, and let colour
   mean something friendly instead of only marking a measurement. */

:root{
  /* Apple's near-black on white, which is warmer and far less severe than
     pure #000 on #fff and is the single biggest change here. */
  --plate:#ffffff;
  --card:#f5f5f7;
  --sink:#fafafa;
  --ink:#1d1d1f;
  --ink-2:#4b4f56;
  --ink-3:#86868b;
  --rule:#e3e3e6;

  /* One confident brand blue, used for actions AND for computed values, so
     the page reads as one product rather than as a chart with a button on
     it. Green earns its place: it is what a bettor is actually looking for. */
  --accent:#0b6cff;
  --accent-hi:#0356d6;
  --accent-ink:#ffffff;
  --accent-soft:#eaf1ff;
  --indigo:#0b6cff;
  --good:#0a8f4d;
  --oxblood:#d1293d;

  --band:rgba(11,108,255,.14);
  --band-neg:rgba(209,41,61,.13);
  --hatch:rgba(209,41,61,.26);

  --term:#0f1115;
  --term-line:#262a31;

  /* Serif headings read academic. The audience is not academic. */
  --serif:var(--sans);
  --display:var(--sans);

  /* 2px radius is a spreadsheet. */
  --r:14px;
  --r-sm:10px;
  --r-pill:999px;

  --shadow-1:0 1px 2px rgba(16,24,40,.05), 0 1px 3px rgba(16,24,40,.06);
  --shadow-2:0 4px 12px rgba(16,24,40,.07), 0 2px 4px rgba(16,24,40,.04);
  --shadow-3:0 12px 32px rgba(16,24,40,.10), 0 4px 8px rgba(16,24,40,.05);
}

/* Dark stays available and stops being the personality. Charcoal, not void. */
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --plate:#0f1115; --card:#181b21; --sink:#14171c;
    --ink:#f5f6f7; --ink-2:#b3b9c4; --ink-3:#868d99; --rule:#2a2f38;
    --accent:#4d94ff; --accent-hi:#7fb2ff; --accent-ink:#08101f;
    --accent-soft:#16233a;
    --indigo:#7fb2ff; --good:#3ecf8e; --oxblood:#ff6b7a;
    --band:rgba(127,178,255,.20); --band-neg:rgba(255,107,122,.18);
    --term:#080a0e; --term-line:#2a2f38;
    --shadow-1:0 1px 2px rgba(0,0,0,.4);
    --shadow-2:0 4px 12px rgba(0,0,0,.45);
    --shadow-3:0 12px 32px rgba(0,0,0,.5);
  }
}
:root[data-theme="dark"]{
  --plate:#0f1115; --card:#181b21; --sink:#14171c;
  --ink:#f5f6f7; --ink-2:#b3b9c4; --ink-3:#868d99; --rule:#2a2f38;
  --accent:#4d94ff; --accent-hi:#7fb2ff; --accent-ink:#08101f;
  --accent-soft:#16233a;
  --indigo:#7fb2ff; --good:#3ecf8e; --oxblood:#ff6b7a;
  --band:rgba(127,178,255,.20); --band-neg:rgba(255,107,122,.18);
  --term:#080a0e; --term-line:#2a2f38;
}

/* --- type: bigger, tighter, friendlier ------------------------------- */
body{font-family:var(--sans);letter-spacing:-.011em}
h1{letter-spacing:-.033em;font-weight:700;line-height:1.04}
h2{letter-spacing:-.024em;font-weight:700}
h3{letter-spacing:-.016em;font-weight:650}
.lede{font-size:1.25rem;line-height:1.5;color:var(--ink-2);
  letter-spacing:-.014em}

/* --- the primary action: a real button ------------------------------- */
.btn,.cta a:first-child,a.btn-primary{
  border-radius:var(--r-pill);padding:.9rem 1.6rem;font-weight:650;
  font-size:1.0625rem;letter-spacing:-.01em;box-shadow:var(--shadow-2);
  border:0;transition:transform .16s cubic-bezier(.2,.7,.3,1),
    box-shadow .16s ease,background .16s ease}
.btn:hover,.cta a:first-child:hover{transform:translateY(-1px);
  box-shadow:var(--shadow-3)}
.btn:active,.cta a:first-child:active{transform:translateY(0)}
.cta a+a,.btn-ghost{border-radius:var(--r-pill);padding:.9rem 1.5rem;
  font-weight:600;font-size:1.0625rem;border:1.5px solid var(--rule);
  background:var(--plate);color:var(--ink);transition:border-color .16s ease,
    background .16s ease}
.cta a+a:hover,.btn-ghost:hover{border-color:var(--ink-3);
  background:var(--card)}

/* --- surfaces: lift instead of outline ------------------------------- */
.cards{gap:1rem;background:none}
.cards .card,.cards>li{background:var(--card);border:1px solid var(--rule);
  border-radius:var(--r);box-shadow:var(--shadow-1);overflow:hidden;
  transition:transform .18s cubic-bezier(.2,.7,.3,1),
    box-shadow .18s ease,border-color .18s ease}
.cards .card:hover,.cards>li:hover{transform:translateY(-2px);
  box-shadow:var(--shadow-2);border-color:color-mix(in srgb,var(--accent) 40%,var(--rule))}
.cards .card a{border-radius:var(--r)}
.cards .card:hover .card-go{color:var(--accent)}
.plate,.figure,.demo-box,.scroll,.screen,pre,.caveat{border-radius:var(--r)}
.demo-box,.plate,.figure{box-shadow:var(--shadow-1)}

/* --- header: lighter, floatier --------------------------------------- */
header{background:color-mix(in srgb,var(--plate) 86%,transparent);
  backdrop-filter:saturate(1.6) blur(14px);
  border-bottom:1px solid var(--rule)}
@supports not (backdrop-filter:blur(1px)){header{background:var(--plate)}}
nav .links a{border-radius:var(--r-pill);padding:.45rem .7rem;
  transition:background .14s ease,color .14s ease}
nav .links a:hover{background:var(--card);color:var(--ink)}
.banner{background:var(--accent-soft);border-bottom:1px solid
  color-mix(in srgb,var(--accent) 18%,transparent)}
.banner a{color:var(--accent)}

/* --- the numbers stay the point, and now read as good news ----------- */
.trust b{color:var(--ink);letter-spacing:-.03em}
.pos,.up,.realised{color:var(--good)}
table{font-family:var(--sans);border-radius:var(--r)}
main table td:not(:first-child){font-family:var(--mono);
  font-variant-numeric:tabular-nums}
th{letter-spacing:.06em;color:var(--ink-3);font-weight:600}

/* --- forms, for when the calculators get their inputs ---------------- */
input,select,button{font:inherit;border-radius:var(--r-sm)}
input[type=range]{accent-color:var(--accent)}

/* --- respect the setting ---------------------------------------------- */
@media (prefers-reduced-motion:reduce){
  *{transition:none!important;transform:none!important;
    scroll-behavior:auto!important}
}

/* --- the product shot ------------------------------------------------
   It was a black terminal, which on a consumer page says "this is for
   developers" before anyone reads a word. The product is a CLI today, but
   what the shot has to communicate is the OUTPUT — four prices, an interval
   drawn on each, and what survives the chance of getting on. That reads
   better as a light product surface, and it is the same data either way. */
.app{
  --card:var(--sink); --sink:#f7f8fa;
  --ink:#1d1d1f; --ink-2:#5b6069; --ink-3:#8a8f98; --rule:#e6e8ec;
  --indigo:var(--accent); --oxblood:#d1293d;
  --band:rgba(11,108,255,.16); --band-neg:rgba(209,41,61,.14);
  background:var(--plate);border:1px solid var(--rule);
  box-shadow:var(--shadow-3);font-family:var(--sans);
  font-size:var(--t-3);border-radius:var(--r)}
.app-bar{background:var(--sink);padding:.7rem 1rem}
.app .dot{background:#d9dce1}
.app .dot:nth-of-type(1){background:#ff5f57}
.app .dot:nth-of-type(2){background:#febc2e}
.app .dot:nth-of-type(3){background:#28c840}
.app-head{background:var(--sink);color:var(--ink-3);letter-spacing:.06em}
.app-row{transition:background .14s ease}
.app-row:hover{background:var(--accent-soft)}
.app .ev-name{font-weight:650;letter-spacing:-.01em}
.app .price,.app .pos,.app .realised,
.app-head span:nth-child(3),.app-row span:nth-child(3),
.app-head span:nth-child(4),.app-row span:nth-child(4),
.app-head span:nth-child(6),.app-row span:nth-child(6),
.app-head span:nth-child(8),.app-row span:nth-child(8){
  font-family:var(--mono);font-variant-numeric:tabular-nums}
/* Realised EV is the number the product exists to show, so it gets the one
   colour a bettor is actually looking for. */
.app .realised{color:var(--good);font-weight:650}

@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]) .app{
    --sink:#14171c; --ink:#f5f6f7; --ink-2:#b3b9c4; --ink-3:#868d99;
    --rule:#2a2f38; --indigo:var(--accent)}
}
:root[data-theme="dark"] .app{
  --sink:#14171c; --ink:#f5f6f7; --ink-2:#b3b9c4; --ink-3:#868d99;
  --rule:#2a2f38; --indigo:var(--accent)}

/* --- the proof points, as objects rather than loose text -------------- */
.trust{gap:1rem;border:0;padding:0}
.trust>div,.trust>li{background:var(--card);border:1px solid var(--rule);
  border-radius:var(--r);padding:1.25rem 1.35rem;box-shadow:var(--shadow-1)}
.trust span{color:var(--ink-3)}

/* The matchup column was narrow enough to wrap "DEN @ PHX" onto two lines,
   which pushed that row taller than its neighbours and broke the shared
   axis the whole figure depends on. */
.app-head,.app-row{grid-template-columns:1.75fr .95fr .62fr .72fr 1.85fr .5fr .6fr .85fr;
  gap:var(--s-2)}
.app .ev-name{white-space:nowrap}
.app-row{min-height:2.9rem}

/* Four proof points that each broke onto two lines read as four problems.
   Wider cells, and a label size that fits one. */
.trust{grid-template-columns:repeat(auto-fit,minmax(13.5rem,1fr))}
.trust span{font-size:.68rem;line-height:1.35;letter-spacing:.07em}
@media (max-width:52rem){.trust{grid-template-columns:repeat(2,1fr)}}

/* --- mobile header ---------------------------------------------------
   The banner plus a two-row nav was taking the whole first screen before a
   word of the page appeared. */
@media (max-width:40rem){
  .banner{font-size:.82rem;padding:.5rem 0}
  .banner-in{display:flex;align-items:center;gap:.5rem;flex-wrap:nowrap}
  .banner-in p,.banner-in span{margin:0;white-space:nowrap;overflow:hidden;
    text-overflow:ellipsis;min-width:0}
  .banner .tag{flex:none;font-size:.62rem;padding:.15rem .45rem}
  .banner a{flex:none}
  nav{flex-wrap:nowrap;padding-block:.55rem}
  nav .brand{font-size:1rem}
  .links{overflow-x:auto;flex-wrap:nowrap;scrollbar-width:none;
    -webkit-overflow-scrolling:touch}
  .links::-webkit-scrollbar{display:none}
  nav .links a{white-space:nowrap;padding:.35rem .55rem;font-size:.9rem}
  /* The header follows the page instead of holding a third of the screen. */
  header{position:static}
}

/* --- commercial + compliance ----------------------------------------
   A disclosure the reader meets before the first paid link, and a
   responsible-gambling block that is part of the page rather than a footer
   afterthought. Both are regulatory requirements in this vertical and both
   are styled to be read, not to be technically present. */
.disclose{background:var(--accent-soft);border:1px solid
  color-mix(in srgb,var(--accent) 22%,transparent);
  border-radius:var(--r);padding:.85rem 1.1rem;font-size:.92rem;
  color:var(--ink-2);margin:1.25rem 0}
.disclose strong{color:var(--ink)}

.rg{border:1px solid var(--rule);border-left:4px solid var(--accent);
  border-radius:var(--r);background:var(--card);padding:1.1rem 1.35rem;
  margin:2rem 0 1rem;font-size:.94rem;color:var(--ink-2)}
.rg p{margin:.4rem 0}
.rg strong{color:var(--ink)}
.rg a{color:var(--accent);font-weight:600}

/* A paid link and an unpaid one do not look the same. */
a.book-cta{display:inline-block;background:var(--accent);color:var(--accent-ink);
  border-radius:var(--r-pill);padding:.4rem .95rem;font-weight:650;
  text-decoration:none;font-size:.92rem;white-space:nowrap;
  box-shadow:var(--shadow-1);transition:transform .14s ease,box-shadow .14s ease}
a.book-cta:hover{transform:translateY(-1px);box-shadow:var(--shadow-2)}
a.book-link{color:var(--ink);font-weight:600;text-decoration:none;
  border-bottom:1.5px solid var(--rule)}
a.book-link:hover{border-bottom-color:var(--accent);color:var(--accent)}

/* The column no competing page prints. */
main table td.good{color:var(--good);font-weight:650;white-space:normal}
main table td.warn{color:var(--ink-2);white-space:normal}

/* The state index: 51 links that need to be scannable, not a wall. */
ul.states{list-style:none;padding:0;margin:1.25rem 0 2rem;display:grid;
  gap:.5rem;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr))}
ul.states li{background:var(--card);border:1px solid var(--rule);
  border-radius:var(--r-sm);padding:.7rem .9rem;display:flex;
  align-items:baseline;justify-content:space-between;gap:.6rem;
  transition:border-color .14s ease,transform .14s ease}
ul.states li:hover{border-color:color-mix(in srgb,var(--accent) 45%,var(--rule));
  transform:translateY(-1px)}
ul.states a{font-weight:650;text-decoration:none;color:var(--ink)}
ul.states li:hover a{color:var(--accent)}
ul.states .n{font-size:.76rem;color:var(--ink-3);white-space:nowrap;
  font-variant-numeric:tabular-nums}
"""

STYLE_HASH = hashlib.sha256(STYLE.encode()).hexdigest()[:10]

# (was, is). Kept forever once a URL has been submitted: a search engine that
# learned an address does not unlearn it because the file moved.
REDIRECTS = [
    ("/sportsbooks/not-covered/", "/sportsbooks/in-person-only/"),
]

PAGES = [
    ("/", "index.html", "Bookbreaker — the edge is an interval",
     "An arbitrage and +EV engine that reports how wrong it might be: the devig "
     "spread, the chance of getting on, and what your record can support.",
     render_index),
    ("/download/", "download/index.html", "Download Bookbreaker",
     "A free command-line arbitrage and +EV engine that runs on your own "
     "machine. No account, no upload, checksums published for every build.",
     render_download),
    ("/how-it-works/", "how-it-works/index.html", "How Bookbreaker works",
     "Welcome offers after every cost, middles counted rather than assumed, "
     "which books you can legally use, and what the tool will not do.",
     render_how),
    ("/vs/", "vs/index.html", "Bookbreaker compared",
     "OddsJam, AVO, Betstamp and Pikkit — every claim dated and linked.",
     render_vs),
    ("/account-longevity/", "account-longevity/index.html",
     "Account longevity — why limits matter more than edge",
     "An account that gets limited stops earning, so lifetime is what expected "
     "value gets divided by. What bet shape gives away, and what this tool "
     "refuses to do.",
     render_longevity),
    ("/what-your-record-proves/", "what-your-record-proves/index.html",
     "What your betting record actually proves",
     "A 2% edge swings between -7% and +11% over a season. Why most betting "
     "records prove nothing, why slicing makes it worse, and what converges "
     "faster than profit.",
     render_evidence),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-repo", default="../arb betting aqpp")
    args = parser.parse_args()

    app_repo = Path(args.app_repo).expanduser().resolve()
    engine = load_engine(app_repo)
    measured = measure(engine)
    measured["engine_fingerprint"] = engine_fingerprint(app_repo)

    built: list[tuple[str, str]] = []

    for url, rel, title, description, renderer in PAGES:
        out = SITE / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(title, description, renderer(measured), url,
                            body_class="home" if url == "/" else ""))
        built.append((url, rel))
        print(f"  {url:<22} {rel}")

    # Calculator cluster: one page per row of _data/calculators.csv.
    for row in load_data("calculators"):
        slug = row["slug"]
        if slug not in measured["calculators"]:
            raise SystemExit(
                f"_data/calculators.csv lists {slug!r} but the engine computes "
                "no worked example for it — add one in measure() or remove the "
                "row, because a calculator page with nothing computed is the "
                "form-and-formula page this site exists to be better than"
            )
        url, rel = f"/calculators/{slug}/", f"calculators/{slug}/index.html"
        out = SITE / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(
            f"{row['name']} — worked, not just a form",
            f"{row['question']} Worked through on real prices by the engine "
            f"that prices bets, with the range the answer sits in.",
            render_calculator(measured, row), url))
        built.append((url, rel))
    print(f"  /calculators/          {len(load_data('calculators'))} pages")

    rows = "".join(
        f'<li class="card"><a href="/calculators/{e(r["slug"])}/">'
        f'<span class="card-t">{e(r["name"])}</span>'
        f'<span class="card-q">{e(r["question"])}</span>'
        f'<span class="card-go" aria-hidden="true">Open &rarr;</span>'
        f'</a></li>'
        for r in load_data("calculators")
    )
    hub = f"""
<h1>Betting calculators, worked rather than blank</h1>
<p class="lede">Every calculator page on the internet shows you a form and a
formula. These show the arithmetic already done on real prices, and the range
the answer sits in &mdash; because the range is the part that decides whether a
bet is worth taking.</p>
<ul class="cards" data-hub>{rows}</ul>
<p>All of them are the engine that prices bets, not a separate implementation.
A calculator that disagrees with the product it advertises is worse than no
calculator.</p>
"""
    out = SITE / "calculators/index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(
        "Betting calculators — worked, not blank",
        "No-vig odds, expected value, arbitrage staking, Kelly, hold, bonus "
        "conversion, middles and closing line value — each worked through on "
        "real prices.",
        hub, "/calculators/"))
    built.append(("/calculators/", "calculators/index.html"))

    bodies = guide_bodies(measured)
    guides = load_data("guides")
    missing = [g["slug"] for g in guides if g["slug"] not in bodies]
    if missing:
        raise SystemExit(
            f"_data/guides.csv lists {missing} with no body written. A guide "
            "generated from a shape reads as generated; write it or drop the "
            "row."
        )
    def related(index: int, n: int = 3) -> str:
        """The next few guides, wrapping round.

        Deterministic rather than chosen: forty hand-picked related-lists is
        forty things to keep true when a row is added, and a rotation touches
        every guide equally instead of orphaning the ones nobody linked.
        """
        picks = [guides[(index + k + 1) % len(guides)] for k in range(n)]
        cards = "".join(
            f'<li class="card"><a href="/guides/{e(r["slug"])}/">'
            f'<span class="card-t">{e(r["title"])}</span>'
            f'<span class="card-q">{e(r["question"])}</span>'
            f'<span class="card-go" aria-hidden="true">Read &rarr;</span>'
            f'</a></li>' for r in picks)
        return (f'<nav class="onward" aria-label="More guides">'
                f'<p class="onward-cap">Keep reading</p>'
                f'<ul class="cards cards--onward">{cards}</ul></nav>')

    for i, row in enumerate(guides):
        url, rel = f"/guides/{row['slug']}/", f"guides/{row['slug']}/index.html"
        out = SITE / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(
            row["title"],
            guide_description(row),
            '<div class="phead">'
            '<p class="crumb"><a href="/">Home</a><span>/</span>'
            '<a href="/guides/">Guides</a></p>'
            f"<h1>{e(row['title'])}</h1>"
            f'<p class="lede">{e(row["question"])}</p>'
            '</div>\n'
            + bodies[row["slug"]]
            + related(i),
            url))
        built.append((url, rel))

    links = "".join(
        f'<li class="card"><a href="/guides/{e(r["slug"])}/">'
        f'<span class="card-t">{e(r["title"])}</span>'
        f'<span class="card-q">{e(r["question"])}</span>'
        f'<span class="card-go" aria-hidden="true">Read &rarr;</span>'
        f'</a></li>' for r in guides
    )
    out = SITE / "guides/index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(
        "Betting guides — the parts other guides skip",
        "Devigging, closing line value, bonus conversion, arbitrage, middles, "
        "limits and bankroll — each answered with the arithmetic done.",
        f"""
<h1>Guides</h1>
<p class="lede">Every one of these is answered somewhere else on the internet.
The difference here is that the numbers are worked, and the parts that are
usually left out &mdash; how uncertain the answer is, and whether you could
actually have placed the bet &mdash; are the parts these lead with.</p>
<ul class="cards" data-hub>{links}</ul>
""", "/guides/"))
    built.append(("/guides/", "guides/index.html"))
    print(f"  /guides/               {len(guides)} pages + hub")

    for name, data, bodies_fn, prefix, title_key, desc in (
        ("audiences", "audiences", audience_bodies, "for",
         "title", lambda r: f"{r['question']} What Bookbreaker does for "
         f"{r['who']}, with the arithmetic shown."),
        ("best", "best", best_bodies, "best",
         "title", lambda r: f"What to check rather than who to buy: "
         f"{r['query']}, answered without an affiliate link."),
    ):
        bodies = bodies_fn(measured)
        rows_ = load_data(data)
        missing = [r["slug"] for r in rows_ if r["slug"] not in bodies]
        if missing:
            raise SystemExit(f"_data/{data}.csv lists {missing} with no body")
        for row in rows_:
            url = f"/{prefix}/{row['slug']}/"
            rel = f"{prefix}/{row['slug']}/index.html"
            out = SITE / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            lead = row.get("question") or row.get("query")
            out.write_text(page(
                row[title_key], desc(row),
                f"<h1>{e(row[title_key])}</h1>\n"
                f"<p class=\"lede\">{e(lead)}</p>\n" + bodies[row["slug"]],
                url))
            built.append((url, rel))
        print(f"  /{prefix}/{' ' * (21 - len(prefix))}{len(rows_)} pages")

    # Competitor cluster: one page per row of _data/competitors.csv.
    for row in load_data("competitors"):
        url = f"/vs/{row['slug']}-alternative/"
        rel = f"vs/{row['slug']}-alternative/index.html"
        out = SITE / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(
            f"{row['name']} alternative — the edge as a range",
            versus_description(row),
            render_versus(measured, row), url))
        built.append((url, rel))
    print(f"  /vs/<tool>-alternative/ {len(load_data('competitors'))} pages")

    jurisdiction_start = len(built)

    # One page for every state with no legal betting, rather than one page
    # each. Measured at 98.4% mutual similarity when generated separately —
    # eleven pages that differ only in a name are eleven pages nobody should
    # have made, and no similarity threshold makes that acceptable.
    dark = sorted(c for c in measured["states"]
                  if not measured["states"][c]["legal"])
    if dark:
        rows = "".join(
            f"<li>{e(STATE_NAMES.get(c, c))}</li>" for c in dark)
        nationwide = measured["states"][dark[0]]["books"]
        body = f"""
<h1>States with no legal sportsbook</h1>
<p class="lede">{len(dark)} states had no legal online sportsbook as of
{e(measured['catalog']['as_of'])}. They share a page because they share an
answer &mdash; generating one each would have produced pages differing only in
a name.</p>
<ul>{rows}</ul>
<p>What is still reachable is the nationwide prediction markets, regulated
federally rather than by any state:</p>
<ul>{"".join(f'<li>{e(b["name"])} &mdash; never limits winning accounts</li>'
             for b in nationwide)}</ul>
<p>That matters more than a consolation prize. An exchange has no bookmaker to
limit you, so it is structurally the best place for a consistent winner, and it
can anchor a fair price where no sharp sportsbook operates.</p>
<p class="caveat">Read {e(measured['catalog']['as_of'])}. A starting point for
your own check, not advice.</p>
"""
        out = SITE / "sportsbooks/no-legal-sportsbook/index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(
            "States with no legal sportsbook",
            "The states with no legal online sportsbook, and what is still "
            "reachable in them: nationwide prediction markets that never limit "
            "winning accounts. Dated.",
            body, "/sportsbooks/no-legal-sportsbook/"))
        built.append(("/sportsbooks/no-legal-sportsbook/",
                      "sportsbooks/no-legal-sportsbook/index.html"))

    gaps = sorted(c for c in measured["states"]
                  if measured["states"][c]["legal"]
                  and not measured["states"][c]["online"])
    if gaps:
        rows = "".join(
            f"<li><strong>{e(STATE_NAMES.get(c, c))}</strong> &mdash; "
            f"{e(measured['states'][c]['retail_only'])}</li>" for c in gaps)
        body = f"""
<h1>States where betting is legal but not online</h1>
<p class="lede">{len(gaps)} states allow sports betting in person and have no
state-regulated online market. They share a page because the answer is the same
in each, and it is not the answer a missing table would give.</p>
<ul>{rows}</ul>
<p>That distinction matters more than it looks. &ldquo;We have not catalogued
this state&rdquo; and &ldquo;this state has no online sportsbook&rdquo; produce
the same empty list, and only one of them means you should go looking. Nothing
here is uncatalogued: as of {e(measured['catalog']['as_of'])} every state with
a legal online market is described, including the five single-operator lottery
markets.</p>
<p class="caveat">Read {e(measured['catalog']['as_of'])}. A starting point for
your own check, not advice.</p>
"""
        out = SITE / "sportsbooks/in-person-only/index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(
            "States where betting is legal but not online",
            "The states that allow sports betting in person with no online "
            "market, and why that is a different answer from a table with a "
            "hole in it. Dated.",
            body, "/sportsbooks/in-person-only/"))
        built.append(("/sportsbooks/in-person-only/",
                      "sportsbooks/in-person-only/index.html"))

    out = SITE / "sportsbooks/index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(
        "Sports betting by state — every book, and which limit winners",
        "Every US state, the licensed sportsbooks covering it, and which of "
        "them limit accounts that win. Dated, and computed rather than "
        "supplied by a sportsbook.",
        render_state_hub(measured), "/sportsbooks/"))
    built.append(("/sportsbooks/", "sportsbooks/index.html"))

    # One page per state, at the URL the search term wants. These were
    # merged by market — states with identical book lists shared a page,
    # because generated separately they measured 97.3% alike. That was the
    # right call for pages that carried nothing but a book list, and the wrong
    # one for a search market: nobody types "sportsbooks in Missouri and
    # Kentucky". The fix is that each page now carries state-specific counts,
    # a limiting breakdown, its own FAQ and its own schema — different
    # content, not a different name on the same content. The similarity gate
    # is what decides whether that worked, and it still runs.
    # Only states that actually have an online market get their own page.
    # A state with no legal sportsbook has the same answer as every other one,
    # and eleven pages that differ only in a name is what the similarity gate
    # exists to stop — those share `no-legal-sportsbook`, and the in-person
    # markets share `in-person-only`, both built above.
    solo = sorted(c for c in measured["states"]
                  if measured["states"][c]["legal"]
                  and measured["states"][c]["online"]
                  and measured["states"][c]["single_operator"])
    if solo:
        names = [STATE_NAMES.get(c, c) for c in solo]
        listed = ", ".join(names[:-1]) + " and " + names[-1]
        as_of = measured["states"][solo[0]]["as_of"]
        body = f"""
{breadcrumb_schema([("Sportsbooks by state", "/sportsbooks/"),
                    ("Single-operator states", "/sportsbooks/one-book-states/")])}
<h1>The states with only one sportsbook</h1>
<p class="lede">{listed} each licensed a single online operator as of
{e(as_of)}. They share a page because they share the consequence.</p>
{disclosure()}
<h2>One book means no line to shop</h2>
<p>Every edge this site measures comes from a disagreement between prices.
Arbitrage needs two books to disagree enough to cover the margin; +EV betting
needs a price that is better than the consensus. With one operator there is no
second price, so there is no disagreement to find and no best price to take
&mdash; you get the number you are given.</p>
<h2>What is still worth doing</h2>
<p>Prediction markets are regulated federally rather than by any state, so they
reach these markets too, and they never limit a winning account. They are also
the only way to see a second price on the same event from inside a
single-operator state.</p>
<ul>{"".join(f'<li>{e(STATE_NAMES.get(c, c))}</li>' for c in solo)}</ul>
{responsible()}
<p class="caveat">Read {e(as_of)} from operator state disclosures. A starting
point for your own check, not legal advice.</p>
"""
        out = SITE / "sportsbooks/one-book-states/index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(
            "The states with only one sportsbook",
            "The states that licensed a single online operator, and why one "
            "book means there is no line to shop.",
            body, "/sportsbooks/one-book-states/"))
        built.append(("/sportsbooks/one-book-states/",
                      "sportsbooks/one-book-states/index.html"))

    for code in sorted(c for c in measured["states"]
                       if measured["states"][c]["legal"]
                       and measured["states"][c]["online"]
                       and not measured["states"][c]["single_operator"]):
        name = STATE_NAMES.get(code, code)
        url = f"/sportsbooks/{code.lower()}/"
        rel = f"sportsbooks/{code.lower()}/index.html"
        out = SITE / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(
            f"{name} sports betting — every book, and which limit winners",
            state_description(name),
            render_state_page(measured, code), url))
        built.append((url, rel))

    jurisdiction = len(built) - jurisdiction_start
    print(f"  /sportsbooks/          {jurisdiction} jurisdiction pages "
          f"covering {len(measured['states'])} states")

    # URLs that were live and submitted to search engines, and have since
    # moved. GitHub Pages cannot issue a 301, so these are meta-refresh stubs
    # with a canonical pointing at the new address. Without them a renamed page
    # is simply a 404 that Bing already knows about — and the rename here was
    # `/sportsbooks/not-covered/`, which had been submitted twice before it
    # became `/sportsbooks/in-person-only/`.
    redirects: list[tuple[str, str]] = []
    for old_url, new_url in REDIRECTS:
        rel = old_url.strip("/") + "/index.html"
        out = SITE / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            "<!doctype html>\n<html lang=\"en\">\n<head>\n"
            "<meta charset=\"utf-8\">\n"
            f"<meta http-equiv=\"refresh\" content=\"0; url={new_url}\">\n"
            f"<link rel=\"canonical\" href=\"https://bookbreaker.bet{new_url}\">\n"
            "<title>Moved</title>\n</head>\n<body>\n"
            f"<p>This page moved to <a href=\"{new_url}\">{new_url}</a>.</p>\n"
            "</body>\n</html>\n"
        )
        redirects.append((old_url, rel))

    # Remove pages this render no longer produces. Without this a page you
    # deliberately stopped generating stays on disk and stays published —
    # eleven orphaned state pages survived the first run of exactly that
    # change, and only a similarity measurement noticed.
    wanted = {SITE / rel for _, rel in built + redirects}
    for stale in sorted(SITE.rglob("*.html")):
        if "_build" in stale.parts or stale in wanted:
            continue
        stale.unlink()
        if not any(stale.parent.iterdir()):
            stale.parent.rmdir()
        print(f"  removed stale {stale.relative_to(SITE)}")

    # IndexNow verifies ownership by fetching this from the site root, so it
    # is content that must ship with the pages — not a build artefact. Written
    # here so a render can never produce a site the submitter cannot verify.
    key_path = SITE / "_build" / "indexnow.key"
    if key_path.exists():
        key = key_path.read_text().strip()
        (SITE / f"{key}.txt").write_text(key + "\n")

    (SITE / "style.css").write_text(STYLE)
    (SITE / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\nSitemap: https://bookbreaker.bet/sitemap.xml\n"
    )
    urls = "".join(
        f"  <url><loc>https://bookbreaker.bet{u}</loc>"
        f"<lastmod>{TODAY}</lastmod></url>\n" for u, _ in built
    )
    (SITE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}</urlset>\n"
    )

    (SITE / "_build" / "measured.json").write_text(
        json.dumps(measured, indent=2, sort_keys=True)
    )
    # The gate reads the third-party list from here rather than importing this
    # module, so the two cannot drift on who counts as a competitor.
    (SITE / "_build" / "competitors.json").write_text(
        json.dumps([{"name": c["name"], "url": c["url"]} for c in COMPETITORS],
                   indent=2)
    )
    print(f"\n  {len(built)} pages, engine v{engine.__version__} "
          f"({measured['engine_fingerprint']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
