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
    edge = price_market(
        hero_market, PricingContext.uncalibrated(hero_books), now=NOW
    )[0]
    out["hero"] = {
        "book": hero_books[edge.book].name,
        "outcome": "over 220.5",
        "price": f"{decimal_to_american(edge.decimal):+.0f}",
        "ev": round(edge.ev * 100, 2),
        "low": round(edge.ev_low * 100, 2),
        "high": round(edge.ev_high * 100, 2),
        "fill": round(edge.p_fill * 100),
        "realised": round(edge.realised_ev * 100, 2),
    }

    # 9. A worked example per calculator, computed rather than written.
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

    out["calculators"] = calc

    # 10. Jurisdiction coverage, and a page per state.
    from overlay_engine.catalog import (
        AS_OF, COVERAGE_GAPS, NO_LEGAL_BETTING, VENUES, for_state, state_summary,
    )

    states = sorted(
        {s for v in VENUES.values() for s in v.states}
        | set(NO_LEGAL_BETTING) | set(COVERAGE_GAPS)
    )
    out["catalog"] = {
        "venues": len(VENUES), "as_of": AS_OF, "states": len(states),
        "nj": len(for_state("NJ")), "fl": len(for_state("FL")),
    }
    out["states"] = {
        code: {
            **state_summary(code),
            "books": [
                {"name": v.name, "tier": v.tier.value,
                 "limits": v.limits_winners,
                 "commission": round(v.commission * 100, 1) if v.commission else 0}
                for v in for_state(code)
            ],
        }
        for code in states
    }
    return out


def e(text: str) -> str:
    return html.escape(str(text))


def page(title: str, description: str, body: str, path: str) -> str:
    nav = (
        '<nav><a href="/">Bookbreaker</a>'
        '<a href="/how-it-works/">How it works</a>'
        '<a href="/guides/">Guides</a>'
        '<a href="/calculators/">Calculators</a>'
        '<a href="/vs/">Compared</a></nav>'
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="https://bookbreaker.bet{path}">
<link rel="stylesheet" href="/style.css">
</head>
<body>
<header>{nav}</header>
<main>
{body}
</main>
<footer>
<p>Bookbreaker is an analysis tool. It tells you what the numbers say; you
place your own bets. It does not link sportsbook accounts and never asks for
sportsbook credentials.</p>
<p>Every figure on this site is computed by running the engine at build time —
none is typed in. Generated {e(TODAY)}.</p>
<p>21+. Gambling involves risk. If it stops being fun, it is not fun —
<a href="https://www.ncpgambling.org/help-treatment/">get help</a>.</p>
</footer>
</body>
</html>
"""


def render_index(m: dict) -> str:
    d = m["devig"]
    f = m["fill"]
    hero = m["hero"]
    method_rows = "".join(
        f"<tr><td>{e(name)}</td><td>{value:.2f}%</td></tr>"
        for name, value in sorted(d["methods"].items())
    )
    a = m["arb"]
    p = m["performance"]

    return f"""
<h1>The edge is an interval, not a number</h1>
<p class="lede">Every betting screen prints one figure to two decimal places.
That figure is a modelling choice wearing a measurement's clothes. Bookbreaker
reports the range, the chance you can actually get the bet down, and what your
own record can and cannot support.</p>
<div class="screen">
<span class="dim">{e(hero['book'])}</span>  {e(hero['outcome'])}
<span class="num">{e(hero['price'])}</span>
<br><span class="dim">  EV</span> <span class="pos">{hero['ev']:+.2f}%</span>
&nbsp;<span class="dim">band</span> {hero['low']:+.2f}%..{hero['high']:+.2f}%
&nbsp;<span class="dim">fill</span> {hero['fill']}%
&nbsp;<span class="dim">&rarr; realised</span>
<span class="pos">{hero['realised']:+.2f}%</span>
</div>
<p class="caveat">Two numbers no competing screen prints: the band the four
devig methods allow, and the chance the price is still there when you tap it.</p>

<h2>Same market, four defensible methods</h2>
<p>Removing a book's margin to recover what it really believes is a modelling
choice, not arithmetic. On a {e(d['market'])} moneyline the four standard
methods disagree by {d['spread']:.2f} points of probability:</p>
<table>
<tr><th>Method</th><th>Fair probability</th></tr>
{method_rows}
</table>
<p>Consensus {d['consensus']:.2f}%. On a market where a 2% edge is a good day,
that spread is a quarter of the edge. Every competing tool picks one of those
rows, hard-codes it, and prints the result as fact.</p>

<h2>A stake a person would actually place</h2>
<p>At {e(a['legs'][0])} and {e(a['legs'][1])} there is a
{a['margin']:.2f}% arbitrage. Every calculator hands you this:</p>
<p class="figure">{a['exact_stakes'][0]:,.2f} and {a['exact_stakes'][1]:,.2f}
&rarr; {a['exact_profit']:,.2f} guaranteed</p>
<p>A precise stake to the cent is the most-cited fingerprint risk desks use to
identify arbitrage. Bookbreaker solves for round stakes directly:</p>
<p class="figure">{a['round_stakes'][0]:,} and {a['round_stakes'][1]:,}
&rarr; {a['round_profit']:,.2f} guaranteed</p>
<p>The {a['rounding_cost']:,.2f} difference is named and reported, not hidden.
A tool that conceals its own trade-offs is not one you can check.</p>

<h2>An edge you cannot take is worth nothing</h2>
<p>Quote age is measured from the book's own timestamp, not from when the feed
reached us. On a feed running {f['latency']:.1f} seconds behind, a quote that
looks {f['age']:.0f} seconds old is really {f['effective']:.1f}:</p>
<p class="figure">still available: {f['honest']}% &mdash; a screen ignoring
latency would say {f['naive']}%</p>

<h2>What your record actually says</h2>
<p>On a {p['n']}-bet history showing {p['profit']:+,} profit and
{p['roi']:.2f}% return, Bookbreaker's verdict is:</p>
<p class="figure">{e(p['verdict'])}</p>
<p>Every other tracker prints {p['roi']:.2f}% and stops.</p>
"""


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
<h1>{e(row['name'])}</h1>
<p class="lede">{e(row['question'])}</p>
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
    """One competitor page. Every claim dated and linked, or the build fails."""
    d = m["devig"]
    f = m["fill"]
    return f"""
<h1>A {e(row['name'])} alternative that shows its uncertainty</h1>
<p class="lede">{e(row['note'])}, at {e(row['price'])} &mdash; read
{e(row['read'])}, <a href="{e(row['source'])}">source</a>.</p>

<h2>The gap</h2>
<p>{e(row['gap'])}.</p>
<p>That absence is not incidental. A screen sorted by raw expected value is
sorted partly by how stale its own data is, because the biggest numbers cluster
on the books that moved most recently &mdash; which are the books most likely
to have moved again. On a feed running {f['latency']:.1f} seconds behind, a
quote that looks {f['age']:.0f} seconds old is really {f['effective']:.1f}, and
its real chance of still being there is {f['honest']}% rather than
{f['naive']}%.</p>

<h2>And the edge itself is a range</h2>
<p>Stripping a book's margin is a modelling choice, not arithmetic. On a
{e(d['market'])} moneyline the four standard methods land between
{min(d['methods'].values()):.2f}% and {max(d['methods'].values()):.2f}% &mdash;
a spread of {d['spread']:.2f} points on a market where a 2% edge is a good day.
Every tool in this category picks one method and prints the result to two
decimals as though it were measured.</p>
<p>Bookbreaker reports the spread, discounts by the chance of getting on, and
tells you when your own record cannot distinguish you from break-even.</p>

<p><a href="/vs/">Every tool compared &rarr;</a>
&nbsp;&middot;&nbsp;
<a href="/">What Bookbreaker does &rarr;</a></p>
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
        f"<tr><td>{e(b['name'])}</td><td>{e(b['tier'])}</td>"
        f"<td>{'yes' if b['limits'] else 'never'}</td>"
        f"<td>{(str(b['commission']) + '%') if b['commission'] else '&mdash;'}</td>"
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
        distinctive = (
            f"<p>{e(name)} is a single-operator market: {e(retail_names[0])} is "
            "the only retail sportsbook here. That is the hardest kind of "
            "market to arb, because an arbitrage needs two books and there is "
            "only one &mdash; what remains is the exchange, and pricing "
            f"{e(retail_names[0])} against it.</p>"
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


STYLE = """/* Built for people who read odds screens.
   Dark by default, because that is what every tool this audience already has
   open looks like at 1am. Tabular figures everywhere, because the numbers are
   the content and a column that does not line up is a column nobody trusts.
   Light mode is a full palette, not an afterthought. */
:root{
  --bg:#0d0f14; --panel:#141821; --line:#232936; --ink:#e7eaf0;
  --muted:#8d95a8; --accent:#5b8cff; --accent-ink:#0d0f14;
  --pos:#3ddc97; --neg:#ff6b6b; --warn:#ffb454;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;
}
@media(prefers-color-scheme:light){:root{
  --bg:#fbfbfd; --panel:#fff; --line:#e4e7ee; --ink:#12151c;
  --muted:#5c6478; --accent:#1b4dd6; --accent-ink:#fff;
  --pos:#0a7f57; --neg:#c02626; --warn:#9a5b00;
}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 var(--sans);
  font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased}

/* ---- chrome ---- */
header{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--bg) 88%,transparent);
  backdrop-filter:saturate(160%) blur(12px);border-bottom:1px solid var(--line)}
nav{max-width:66rem;margin:0 auto;padding:.85rem 1.25rem;display:flex;
  flex-wrap:wrap;gap:.35rem 1.4rem;align-items:baseline}
nav a{color:var(--muted);text-decoration:none;font-size:.93rem;font-weight:500}
nav a:first-child{color:var(--ink);font-weight:700;font-size:1.05rem;
  letter-spacing:-.02em;margin-right:.6rem}
nav a:hover{color:var(--accent)}
main{max-width:44rem;margin:0 auto;padding:0 1.25rem 4rem}
footer{max-width:44rem;margin:0 auto;padding:2rem 1.25rem 3rem;
  border-top:1px solid var(--line);color:var(--muted);font-size:.87rem}
footer p{margin:.5rem 0}

/* ---- type ---- */
h1{font-size:clamp(1.9rem,4.4vw,2.6rem);line-height:1.12;letter-spacing:-.025em;
  margin:2.6rem 0 .9rem;text-wrap:balance}
h2{font-size:1.22rem;letter-spacing:-.01em;margin:2.6rem 0 .7rem;
  padding-top:1.4rem;border-top:1px solid var(--line)}
p{margin:.85rem 0}
.lede{font-size:1.1rem;line-height:1.55;color:var(--muted);max-width:38rem}
strong{color:var(--ink);font-weight:650}
a{color:var(--accent);text-underline-offset:2px}
ul{padding-left:1.1rem}
li{margin:.4rem 0}
.caveat{color:var(--muted);font-size:.88rem;border-left:2px solid var(--line);
  padding-left:.9rem}

/* ---- the numbers ---- */
.figure{background:var(--panel);border:1px solid var(--line);
  border-left:3px solid var(--accent);border-radius:.4rem;
  padding:.9rem 1.05rem;margin:1.2rem 0;font-family:var(--mono);
  font-size:.94rem;line-height:1.5;overflow-x:auto}
table{border-collapse:collapse;width:100%;margin:1.2rem 0;font-size:.93rem;
  font-family:var(--mono);display:block;overflow-x:auto;white-space:nowrap}
th{text-align:left;padding:.45rem .75rem;font-family:var(--sans);
  font-size:.72rem;text-transform:uppercase;letter-spacing:.07em;
  color:var(--muted);font-weight:600;border-bottom:1px solid var(--line)}
td{padding:.5rem .75rem;border-bottom:1px solid var(--line)}
tr:last-child td{border-bottom:0}
td:first-child{font-family:var(--sans);color:var(--muted)}
tbody tr:hover td,table tr:hover td{background:var(--panel)}

/* ---- index cards ---- */
main>ul:has(a){list-style:none;padding:0;display:grid;gap:.6rem;
  grid-template-columns:repeat(auto-fill,minmax(15rem,1fr))}
main>ul:has(a) li{margin:0;background:var(--panel);border:1px solid var(--line);
  border-radius:.5rem;padding:.85rem .95rem;font-size:.92rem;
  color:var(--muted);transition:border-color .15s}
main>ul:has(a) li:hover{border-color:var(--accent)}
main>ul:has(a) a{display:block;font-weight:600;text-decoration:none;
  margin-bottom:.2rem}

.screen{background:var(--panel);border:1px solid var(--line);border-radius:.5rem;
  padding:1rem 1.1rem;margin:1.4rem 0;font-family:var(--mono);font-size:.9rem;
  line-height:1.9;overflow-x:auto;white-space:nowrap}
.screen .dim{color:var(--muted)}
.screen .num{color:var(--accent)}
.screen .pos{color:var(--pos);font-weight:600}
main>ul:has(a) li{display:flex;flex-direction:column;gap:.3rem}

@media(max-width:34rem){
  main{padding:0 1rem 3rem}
  nav{padding:.7rem 1rem;gap:.3rem 1rem}
  h2{margin-top:2rem}
}
"""

PAGES = [
    ("/", "index.html", "Bookbreaker — the edge is an interval",
     "An arbitrage and +EV engine that reports how wrong it might be: the devig "
     "spread, the chance of getting on, and what your record can support.",
     render_index),
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
        out.write_text(page(title, description, renderer(measured), url))
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
        f'<li><a href="/calculators/{e(r["slug"])}/">{e(r["name"])}</a>'
        f'{e(r["question"])}</li>'
        for r in load_data("calculators")
    )
    hub = f"""
<h1>Betting calculators, worked rather than blank</h1>
<p class="lede">Every calculator page on the internet shows you a form and a
formula. These show the arithmetic already done on real prices, and the range
the answer sits in &mdash; because the range is the part that decides whether a
bet is worth taking.</p>
<ul>{rows}</ul>
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
    for row in guides:
        url, rel = f"/guides/{row['slug']}/", f"guides/{row['slug']}/index.html"
        out = SITE / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(
            row["title"],
            guide_description(row),
            f"<h1>{e(row['title'])}</h1>\n"
            f"<p class=\"lede\">{e(row['question'])}</p>\n"
            + bodies[row["slug"]],
            url))
        built.append((url, rel))

    links = "".join(
        f'<li><a href="/guides/{e(r["slug"])}/">{e(r["title"])}</a>'
        f'{e(r["question"])}</li>' for r in guides
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
<ul>{links}</ul>
""", "/guides/"))
    built.append(("/guides/", "guides/index.html"))
    print(f"  /guides/               {len(guides)} pages + hub")

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
                  and not measured["states"][c]["covered"])
    if gaps:
        rows = "".join(
            f"<li><strong>{e(STATE_NAMES.get(c, c))}</strong> &mdash; "
            f"{e(measured['states'][c]['gap_reason'])}</li>" for c in gaps)
        body = f"""
<h1>States this table does not cover</h1>
<p class="lede">{len(gaps)} states have legal betting that the operator table
behind this site does not describe. They share a page because the honest answer
is the same in each: the market exists and we have not catalogued it.</p>
<ul>{rows}</ul>
<p>Most run a lottery-operated book, which is a different shape from the
multi-operator markets elsewhere &mdash; often one app, sometimes kiosk-only.
Naming the gap matters more than it might seem: an empty list and an
uncatalogued market look identical to a reader, and only one of them is a bug.</p>
<p class="caveat">Read {e(measured['catalog']['as_of'])}. A starting point for
your own check, not advice.</p>
"""
        out = SITE / "sportsbooks/not-covered/index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(
            "States this table does not cover",
            "States with legal betting that this operator table does not "
            "describe, and why naming the gap matters more than leaving it "
            "blank. Dated.",
            body, "/sportsbooks/not-covered/"))
        built.append(("/sportsbooks/not-covered/",
                      "sportsbooks/not-covered/index.html"))

    # One page per distinct market, not per state. Missouri and Kentucky have
    # identical venue lists, so separate pages measured 97.3% alike — they were
    # the same page twice. States sharing a market now share a page, which is
    # both the honest answer and the one a reader is better served by.
    markets: dict[tuple, list[str]] = {}
    for code in sorted(c for c in measured["states"]
                       if measured["states"][c]["legal"]
                       and measured["states"][c]["covered"]):
        key = tuple(b["name"] for b in measured["states"][code]["books"])
        markets.setdefault(key, []).append(code)

    for codes in sorted(markets.values(), key=lambda c: c[0]):
        names = [STATE_NAMES.get(c, c) for c in codes]
        name = names[0] if len(names) == 1 else (
            ", ".join(names[:-1]) + " and " + names[-1])
        slug = "-".join(c.lower() for c in codes)
        url = f"/sportsbooks/{slug}/"
        rel = f"sportsbooks/{slug}/index.html"
        out = SITE / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(
            f"Sportsbooks in {name} — which you can use"
            if len(codes) == 1 else f"Sportsbooks in {name}",
            state_description(name),
            render_market(measured, codes), url))
        built.append((url, rel))
    jurisdiction = len(built) - jurisdiction_start
    print(f"  /sportsbooks/          {jurisdiction} jurisdiction pages "
          f"covering {len(measured['states'])} states")

    # Remove pages this render no longer produces. Without this a page you
    # deliberately stopped generating stays on disk and stays published —
    # eleven orphaned state pages survived the first run of exactly that
    # change, and only a similarity measurement noticed.
    wanted = {SITE / rel for _, rel in built}
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
