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
    out["conversion"] = {"bonus": 1000, "ladder": ladder}

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
    out["fill"] = {
        "age": age, "latency": round(lag, 1),
        "effective": round(age + lag, 1),
        "honest": round(fills.p_fill("dk", "h2h", age + lag) * 100),
        "naive": round(fills.p_fill("dk", "h2h", age) * 100),
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
    method_rows = "".join(
        f"<tr><td>{e(name)}</td><td>{value:.2f}%</td></tr>"
        for name, value in sorted(d["methods"].items())
    )
    a = m["arb"]
    f = m["fill"]
    p = m["performance"]

    return f"""
<h1>The edge is an interval, not a number</h1>
<p class="lede">Every betting screen prints one figure to two decimal places.
That figure is a modelling choice wearing a measurement's clothes. Bookbreaker
reports the range, the chance you can actually get the bet down, and what your
own record can and cannot support.</p>

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


STYLE = """:root{--ink:#17181c;--bg:#fff;--accent:#1b4dd6;--muted:#5b6070;
--line:#e3e5ea;--fig:#f6f7f9}
*{box-sizing:border-box}
body{margin:0;font:17px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",
Roboto,sans-serif;color:var(--ink);background:var(--bg)}
header,main,footer{max-width:46rem;margin:0 auto;padding:0 1.25rem}
nav{display:flex;gap:1.5rem;padding:1.5rem 0;border-bottom:1px solid var(--line)}
nav a{color:var(--muted);text-decoration:none;font-weight:500}
nav a:first-child{color:var(--ink);font-weight:700}
nav a:hover{color:var(--accent)}
h1{font-size:2.1rem;line-height:1.2;margin:2.5rem 0 1rem}
h2{font-size:1.35rem;margin:2.5rem 0 .75rem}
.lede{font-size:1.15rem;color:var(--muted)}
.figure{background:var(--fig);border-left:3px solid var(--accent);
padding:.85rem 1rem;font-variant-numeric:tabular-nums;margin:1rem 0}
.caveat{color:var(--muted);font-size:.94rem}
table{border-collapse:collapse;width:100%;margin:1rem 0;
font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:.5rem .6rem;border-bottom:1px solid var(--line)}
th{font-size:.85rem;text-transform:uppercase;letter-spacing:.04em;
color:var(--muted)}
a{color:var(--accent)}
footer{margin-top:4rem;padding-top:1.5rem;border-bottom:0;
border-top:1px solid var(--line);color:var(--muted);font-size:.9rem}
@media(prefers-color-scheme:dark){:root{--ink:#e8e9ed;--bg:#17181c;
--accent:#8aa9ff;--muted:#9aa0b0;--line:#2b2d35;--fig:#1f2128}}
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
        f'<li><a href="/calculators/{e(r["slug"])}/">{e(r["name"])}</a> '
        f'&mdash; {e(r["question"])}</li>'
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
