"""The calculators on bookbreaker.bet, as one module.

It runs in two places and has to behave the same in both. Under CPython, the
site's build and its gate import it. Under Pyodide, a visitor's browser loads
it after installing the engine wheel this site publishes in /releases/, and
calls `run_json` with whatever they typed.

Nothing here prices a bet. Every figure is a call into `overlay_engine`, the
same functions render.py calls to work the example at the top of each page, and
what is left in this file is reading what a person typed and laying the answer
out the way the worked example does. The browser side (calc.js) does no
arithmetic at all: it hands strings to `run_json` and draws what comes back.

Inputs arrive as strings and are read here, in Python, so that "+150", "2.5",
"$1,000" and "55%" mean what the engine says they mean and not what a second
parser in JavaScript would guess.
"""

from __future__ import annotations

import json
import re

from overlay_engine.arb import arb_margin, ideal_stakes, middle_probability, stake_arb
from overlay_engine.clv import closing_fair, implied_clv
from overlay_engine.devig import devig_all
from overlay_engine.ev import breakeven_prob, ev_per_unit
from overlay_engine.kelly import MAX_SINGLE, size_bet
from overlay_engine.odds import (
    decimal_to_american, decimal_to_prob, hold, overround, parse_odds)
from overlay_engine.parlay import ASSUMPTION, correlation_note, value as parlay_value
from overlay_engine.roundrobin import build as round_robin_build
from overlay_engine.middles import MiddlePlan, stake_middle
from overlay_engine.poisson import build as poisson_build
from overlay_engine import lowhold
from overlay_engine.portfolio import effective_bets as effective_count
from overlay_engine.offers import ClassHold, Verdict
from overlay_engine.promo import breakeven_hold
from overlay_engine.promo import (
    bet_and_get_value, bonus_bet_conversion, fair_conversion_ceiling, profit_boost_value,
    safety_net_premium, safety_net_value)


# BEGIN NFL_SPREAD (written by _build/nfl_spread_moneyline.py; do not edit by hand)
NFL_SPREAD_READ = '2026-10-22'
NFL_SPREAD_GAMES = 3023
NFL_SPREAD = {
    1: (206, 99, 0, 0.5185),
    1.5: (102, 55, 0, 0.5306),
    2: (80, 44, 1, 0.5432),
    2.5: (311, 165, 3, 0.5653),
    3: (433, 259, 1, 0.5974),
    3.5: (308, 195, 1, 0.6312),
    4: (133, 74, 0, 0.6514),
    4.5: (106, 70, 0, 0.6659),
    5: (63, 45, 0, 0.6778),
    5.5: (142, 91, 1, 0.6889),
    6: (142, 99, 0, 0.7025),
    6.5: (136, 107, 0, 0.7197),
    7: (172, 129, 2, 0.7414),
    7.5: (165, 125, 0, 0.7597),
    8: (41, 30, 0, 0.7751),
    8.5: (49, 36, 0, 0.7821),
    9.5: (48, 41, 0, 0.7933),
    10: (80, 65, 0, 0.7982),
    10.5: (64, 55, 0, 0.8107),
    14: (42, 37, 0, 0.8762),
}
# END NFL_SPREAD


class CalcError(ValueError):
    """Something the person typed that cannot be used, in words they can act on."""


# ---------------------------------------------------------------------------
# Reading what was typed
# ---------------------------------------------------------------------------

def _raw(values: dict, name: str) -> str:
    text = str(values.get(name, "")).strip()
    # A pasted minus sign is often U+2212 or an en dash, and float() refuses both.
    return text.replace("−", "-").replace("–", "-")


def _price(values: dict, name: str, label: str) -> float:
    """One price, American or decimal, as the engine's decimal."""
    text = _raw(values, name)
    if not text:
        raise CalcError(f"{label} is empty.")
    try:
        return parse_odds(text)
    except ValueError as exc:
        raise CalcError(_price_problem(text, exc)) from exc


def _prices(values: dict, name: str, label: str, least: int, most: int) -> list:
    tokens = [t for t in re.split(r"[,;\s]+", _raw(values, name)) if t]
    if len(tokens) < least:
        raise CalcError(
            f"{label}: enter at least {least} price" + ("" if least == 1 else "s")
            + ", separated by commas.")
    if len(tokens) > most:
        raise CalcError(f"{label}: enter at most {most} prices.")
    out = []
    for token in tokens:
        try:
            out.append(parse_odds(token))
        except ValueError as exc:
            raise CalcError(_price_problem(token, exc)) from exc
    return out


def _price_problem(token: str, exc: Exception) -> str:
    message = str(exc)
    if "quotable" in message or "must exceed" in message:
        return message[:1].upper() + message[1:].rstrip(".") + "."
    return (f"“{token}” is not a price I can read. "
            "Use American, like -110 or +150, or decimal, like 1.91.")


def _number(values: dict, name: str, label: str) -> float:
    text = _raw(values, name).replace(",", "").replace("$", "").replace("%", "")
    if not text:
        raise CalcError(f"{label} is empty.")
    try:
        number = float(text)
    except ValueError:
        raise CalcError(f"{label} must be a number; “{_raw(values, name)}” is not.")
    if number != number or number in (float("inf"), float("-inf")):
        raise CalcError(f"{label} must be a finite number.")
    return number


def _amount(values: dict, name: str, label: str) -> float:
    number = _number(values, name, label)
    if number <= 0:
        raise CalcError(f"{label} must be more than zero.")
    return number


def _percent(values: dict, name: str, label: str, most: float = 100.0,
             closed: bool = False) -> float:
    """A percentage typed as 55 or 55%, returned as the fraction 0.55.

    Zero is never allowed. `closed` lets the top of the range through, for
    inputs where a hundred per cent is a real answer (a cash refund converts
    at 100) and not for probabilities, where it is not.
    """
    number = _number(values, name, label)
    if not (0.0 < number <= most if closed else 0.0 < number < most):
        raise CalcError(
            f"{label} must be between 0 and {most:g} per cent, not {number:g}.")
    return number / 100.0


def _american(decimal: float) -> str:
    return f"{round(decimal_to_american(decimal)):+d}"


def _plain(number: float) -> str:
    """300.0 as 300, and 12.5 as 12.50."""
    return f"{int(number):,}" if number == int(number) else f"{number:,.2f}"


def _signed(number: float) -> str:
    # "-0.00" is what a float that is a hair under zero prints, and it reads as
    # a loss when the answer is nothing.
    return f"{(0.0 if abs(number) < 0.005 else number):+,.2f}"


def _stand(count: int) -> str:
    return ("both bets are accepted and stand" if count == 2
            else "every bet is accepted and stands")


def _both(count: int) -> str:
    return "both" if count == 2 else "all"


# ---------------------------------------------------------------------------
# The calculators. Each returns headline / caption / table / notes, any of
# which may be absent; calc.js draws whatever is there.
# ---------------------------------------------------------------------------

def dutching(v: dict) -> dict:
    prices = _prices(v, "prices", "The prices", 2, 12)
    total = _amount(v, "total", "The total to stake")
    plan = stake_arb(prices, total, round_stakes=False)
    implied = overround(prices)
    profit = plan.profit
    rows = [[_american(leg.decimal), f"{leg.stake:,.2f}", f"{leg.payout:,.2f}"]
            for leg in plan.legs]
    notes = [f"The prices imply {implied:.2%} of probability between them."]
    if profit > 0:
        # Only an arbitrage when these prices cover EVERY outcome of the event: a dutch over two of three outcomes
        # loses everything when the third lands (the full audit, 2026-11-04, on +240 / +250).
        notes.append(
            "That is under 100%. It is an arbitrage only if these prices cover every possible outcome of the "
            f"event, and then the return holds if {_stand(len(prices))}. If any outcome is left out, "
            "every stake here is lost when that outcome happens.")
    else:
        notes.append(
            "Anything above 100% is the book's margin, so this spread costs "
            "money. It expresses a view that the winner is somewhere in this "
            "set, at a known price. It does not manufacture an edge.")
    return {
        "headline": _signed(profit),
        "caption": f"on {_plain(total)} staked, whichever of these outcomes "
                   f"wins ({profit / total:+.2%})",
        "table": {"head": ["Price", "Stake", "Returns"], "rows": rows},
        "notes": notes,
    }


def kelly(v: dict) -> dict:
    price = _price(v, "price", "The price offered")
    prob = _percent(v, "prob", "Your win probability")
    bankroll = _amount(v, "bankroll", "The bankroll")
    fraction = _percent(v, "fraction", "The Kelly fraction", closed=True)
    sizing = size_bet(price, prob, bankroll, fraction=fraction)
    name = {0.25: "quarter", 0.5: "half", 1.0: "full"}.get(fraction, f"{fraction:.0%}")
    notes = []
    if sizing.binding == "max_single":
        notes.append(
            f"Capped: no single bet takes more than {MAX_SINGLE:.0%} of the "
            "bankroll, whatever Kelly says.")
    elif sizing.binding == "no_edge":
        notes.append("At this probability the price has no edge, so Kelly says "
                     "to bet nothing.")
    notes.append("Kelly trusts your probability completely. Overestimate it and "
                 "the stake is too large, which costs far more than "
                 "underestimating it.")
    return {
        "headline": f"{sizing.stake:,.2f}",
        "caption": f"stake, at {name} Kelly on a {_plain(bankroll)} bankroll",
        "table": {"head": None, "rows": [
            ["Full Kelly", f"{sizing.full_kelly:.2%} of bankroll"],
            [f"At {name} Kelly", f"{sizing.stake:,.2f}"],
            ["Share of bankroll", f"{sizing.bankroll_share:.2%}"],
            ["Binding constraint", sizing.binding]]},
        "notes": notes,
    }


def hedge(v: dict) -> dict:
    stake = _amount(v, "stake", "Your stake")
    opened = _price(v, "open", "The price you took")
    lays = _prices(v, "lay", "The prices to bet the other side at", 1, 12)
    rows, locked_last = [], 0.0
    for close in lays:
        # Stakes that make both outcomes pay the same, scaled so the first
        # leg is the bet already placed.
        unit = ideal_stakes([opened, close], 1.0)
        plan = stake_arb([opened, close], stake / unit[0], round_stakes=False)
        lay, locked = plan.legs[1].stake, plan.profit
        locked_last = locked
        rows.append([_american(close), f"{lay:,.2f}", _signed(locked),
                     f"{locked / plan.total_stake:+.2%}"])
    out = {
        "table": {"head": ["Lay at", "Lay stake", "Locked",
                           "Return on total staked"], "rows": rows},
        "notes": ["Locked is what you keep whichever side wins, if the second "
                  "bet is accepted and stands. A negative figure is a loss "
                  "taken on purpose, because covering the position costs more "
                  "than the open bet stands to make."],
    }
    if len(lays) == 1:
        out["headline"] = _signed(locked_last)
        out["caption"] = "locked if the second bet is accepted and stands"
    return out


def arbitrage(v: dict) -> dict:
    prices = _prices(v, "prices", "The prices", 2, 4)
    total = _amount(v, "total", "The total to stake")
    margin = arb_margin(prices)
    exact = stake_arb(prices, total, round_stakes=False)
    stakes = " / ".join(f"{leg.stake:,.2f}" for leg in exact.legs)
    count = len(prices)
    if margin <= 0:
        return {
            "headline": "No arbitrage",
            "caption": f"The prices imply {overround(prices):.2%} of probability "
                       "between them. An arbitrage needs less than 100%.",
            "table": {"head": None, "rows": [
                ["Stakes that equalise the return", stakes],
                ["Result whichever side wins", _signed(exact.profit)]]},
            "notes": ["Betting every side at these prices loses money, "
                      "whichever wins. Check the prices are for the same "
                      "market, and that each is still on offer."],
        }
    rounded = stake_arb(prices, total)
    rows = [["Exact stakes", stakes],
            [f"Locked if {_both(count)} stand, exact", f"{exact.profit:,.2f}"]]
    notes = ["A stake to the cent is the loudest fingerprint a risk desk reads. "
             "The round stakes are solved for directly, because rounding a "
             "lock afterwards can break it."]
    if rounded.rounded:
        rows += [
            ["Round stakes", " / ".join(f"{round(leg.stake):,}" for leg in rounded.legs)],
            [f"Locked if {_both(count)} stand, rounded", f"{rounded.profit:,.2f}"],
            ["Cost of rounding", f"{rounded.rounding_cost:,.2f}"]]
    else:
        notes.insert(0, "No set of round stakes keeps this lock: the margin is "
                        "thinner than one step of rounding.")
    return {
        "headline": f"{margin:.2%}",
        "caption": "arbitrage margin on these prices, before the stakes are "
                   f"rounded. Locked if {_stand(count)}.",
        "table": {"head": None, "rows": rows},
        "notes": notes,
    }


def closing_line_value(v: dict) -> dict:
    bet = _price(v, "bet", "Your price")
    close = _price(v, "close", "The closing price")
    rows = [["Your price", _american(bet)],
            ["Closing price", _american(close)],
            ["CLV against the raw close", f"{implied_clv(bet, close):+.2%}"]]
    other_text = _raw(v, "other")
    if not other_text:
        return {
            "headline": f"{implied_clv(bet, close):+.2%}",
            "caption": "against the raw close, which compares two vigged prices",
            "table": {"head": None, "rows": rows},
            "notes": ["That overstates the real edge, by about the closing margin. "
                      "Use it to rank bets against each other, not to claim an "
                      "edge size. Add the other side's closing price and the "
                      "engine devigs the close first."],
        }
    other = _price(v, "other", "The other side's closing price")
    fair = closing_fair([close, other], 0)
    rows += [["Fair closing probability, devigged", f"{fair:.2%}"],
             ["CLV against the devigged close", f"{ev_per_unit(bet, fair):+.2%}"]]
    return {
        "headline": f"{ev_per_unit(bet, fair):+.2%}",
        "caption": "against the devigged close",
        "table": {"head": None, "rows": rows},
        "notes": ["One bet proves nothing. Closing line value is a rate, and "
                  "it converges far faster than profit does."],
    }


def expected_value(v: dict) -> dict:
    price = _price(v, "price", "The price offered")
    own = _raw(v, "own")
    rows = []
    worst = spread = None
    if own:
        fair = _percent(v, "own", "Your fair probability")
        where = "at your fair probability"
    else:
        side = _price(v, "side", "The market price for this side")
        other = _price(v, "other", "The market price for the other side")
        market = devig_all([side, other])
        fair, worst, spread = market.consensus(0), market.low(0), market.spread(0)
        where = f"at a consensus fair probability of {fair:.2%}"
    rows.append(["Expected value per unit", f"{ev_per_unit(price, fair):+.2%}"])
    rows.append(["Break-even win rate", f"{breakeven_prob(price):.2%}"])
    notes = []
    if worst is not None:
        rows.append(["Worst method's answer", f"{ev_per_unit(price, worst):+.2%}"])
        notes.append(f"The four devig methods disagree by {spread * 100:.2f} "
                     "points on that probability. An edge that exists under "
                     "one method and vanishes under another is a modelling "
                     "artefact, not an opportunity.")
    return {
        "headline": f"{ev_per_unit(price, fair):+.2%}",
        "caption": f"expected value per unit staked, {where}",
        "table": {"head": None, "rows": rows},
        "notes": notes,
    }


def parlay(v: dict) -> dict:
    legs = _prices(v, "legs", "The legs", 2, 12)
    value = parlay_value(legs)
    rows = [["Pays, in profit per unit staked", f"{value.offered - 1:.2f}"],
            ["A fair price would pay", f"{value.fair - 1:.2f}"],
            ["Hold on the ticket", f"{value.hold:.1%}"]]
    notes = [ASSUMPTION]
    if len(set(legs)) == 1:
        rows += [["Hold on a single leg", f"{value.leg_hold:.2%}"],
                 ["Times the single-leg hold", f"{value.multiple:.1f}"]]
    if _raw(v, "same_game"):
        notes.append(correlation_note(same_game=True))
    return {
        "headline": f"{value.hold:.1%}",
        "caption": f"hold on this {value.legs}-leg ticket: the share of its "
                   "fair value the book keeps",
        "table": {"head": None, "rows": rows},
        "notes": notes,
    }


def odds_converter(v: dict) -> dict:
    prices = _prices(v, "prices", "The prices", 1, 20)
    stake = _amount(v, "stake", "The stake") if _raw(v, "stake") else None
    head = ["American", "Decimal", "Implied"]
    rows = [[_american(d), f"{d:.3f}", f"{decimal_to_prob(d):.2%}"] for d in prices]
    if stake is not None:
        head += [f"Profit on ${stake:,.2f}", "Paid back if it wins"]
        for row, d in zip(rows, prices):
            row += [f"${stake * (d - 1):,.2f}", f"${stake * d:,.2f}"]
    return {
        "table": {"head": head, "rows": rows},
        "notes": ["The implied column is vig-inclusive: it is what the price "
                  "asserts, not a fair probability. Devig the market before "
                  "calling it one."],
    }


def breakeven(v: dict) -> dict:
    prices = _prices(v, "prices", "The prices", 1, 20)
    rows = [[_american(d), f"{breakeven_prob(d):.2%}"] for d in prices]
    return {
        "table": {"head": ["Price", "Break-even win rate"], "rows": rows},
        "notes": ["Win less often than this and the price loses money over "
                  "time. Win more often and it earns."],
    }


def low_hold(v: dict) -> dict:
    first = _prices(v, "first", "The first side's prices", 2, 12)
    second = _prices(v, "second", "The other side's prices", 2, 12)
    if len(first) != len(second):
        raise CalcError(f"Type one price per book on each side, in the same book order: {len(first)} on the first "
                        f"side and {len(second)} on the other.")
    turnover = _amount(v, "turnover", "The turnover")
    quotes = []
    for i, (a, b) in enumerate(zip(first, second), start=1):
        quotes += [lowhold.Quote(f"Book {i}", "first", a), lowhold.Quote(f"Book {i}", "second", b)]
    split, alone = lowhold.best(quotes)[0], lowhold.single_book_baseline(quotes)
    rows = [["Split across books", f"{split.hold * 100:+.3f}%, costs {split.cost_of(turnover):,.2f}"]]
    if alone is not None:
        rows += [["Cheapest single book", f"{alone.hold * 100:+.3f}%, costs {alone.cost_of(turnover):,.2f}"],
                 ["Difference", f"{alone.cost_of(turnover) - split.cost_of(turnover):,.2f}"]]
    picked = ", ".join(f"the {q.side} side at {q.book}" for q in split.picks)
    return {
        "headline": f"{split.hold * 100:+.3f}%",
        "caption": "hold on the cheapest way to cover both sides",
        "table": {"head": None, "rows": rows},
        "notes": [f"Cheapest: {picked}. A negative hold is an arbitrage, which holds only if both bets are accepted "
                  "and stand; a positive one is a cost, smaller than the obvious way and not free."],
    }


def totals_middle(v: dict) -> dict:
    low_line = _number(v, "low", "The lower total (your over)")
    high_line = _number(v, "high", "The higher total (your under)")
    if not high_line > low_line:
        raise CalcError("The under's total must be higher than the over's, or there is no window between them.")
    over = _price(v, "over", "The price on the over")
    under = _price(v, "under", "The price on the under")
    total = _amount(v, "total", "The total to stake")
    sigma = _amount(v, "sigma", "The spread of finals around the total")
    mid = (low_line + high_line) / 2.0
    p = middle_probability(low_line - mid, high_line - mid, sigma)
    lo, hi = stake_middle(over, under, total, round_stakes=False)
    plan = MiddlePlan(low_line=low_line, high_line=high_line, low_book="", high_book="", low_decimal=over,
                      high_decimal=under, low_stake=lo, high_stake=hi, p_middle=p, source="approximated")
    expected = p * plan.middle_profit + (1.0 - p) * plan.one_side_profit
    return {
        "headline": f"{p * 100:.2f}%",
        "caption": f"chance the final lands between {low_line:g} and {high_line:g}, by a normal approximation",
        "table": {"head": None, "rows": [["Window", f"{p * 100:.2f}%"],
                                         ["Break-even", f"{plan.breakeven_p * 100:.2f}%"],
                                         ["Worth, on average", _signed(expected)]]},
        "notes": [f"The spread of {sigma:g} points is a prior you typed, not a measurement, and the window is "
                  "centred halfway between the two totals. A count of real finals beats it once there are enough."],
    }


def effective_bets(v: dict) -> dict:
    n_text = _raw(v, "bets")
    if not n_text.isdigit() or not 1 <= int(n_text) <= 500:
        raise CalcError("Type how many bets you hold as a whole number, like 12.")
    n = int(n_text)
    rho = _number(v, "rho", "The average correlation")
    if not 0.0 <= rho < 1.0:
        raise CalcError("Type the average correlation between your bets as a number from 0 to just under 1, "
                        "like 0.25.")
    eff = effective_count(n, rho)
    return {
        "headline": f"{eff:.1f}",
        "caption": f"independent bets is what {n} bets at an average correlation of {rho:g} add up to",
        "table": {"head": None, "rows": [["Bets", f"{n}"], ["Effective bets", f"{eff:.1f}"]]},
        "notes": ["Effective bets is n divided by one plus n minus one times rho. The correlation is yours: a "
                  "starting point, not a measurement, until a ledger of your own settled bets measures one."],
    }


def deposit_match(v: dict) -> dict:
    deposit = _amount(v, "deposit", "The deposit")
    bonus = _amount(v, "bonus", "The bonus")
    rollover = _amount(v, "rollover", "The playthrough")
    market = _prices(v, "market", "The prices of the market you play through", 2, 12)
    churn = hold(market)
    if churn <= 0:
        raise CalcError("Those prices carry no margin, so they are not one book's market. Type one book's prices "
                        "for every side of the market you would play through.")
    with_deposit = bool(_raw(v, "bonus_only")) is False
    verdict = Verdict(book="", state="", bonus=bonus, deposit=deposit, rollover=rollover,
                      breakeven=breakeven_hold(deposit, bonus, rollover, with_deposit),
                      churn=ClassHold("the market you play through", churn, "prior"), terms_age_days=0.0,
                      includes_deposit=with_deposit)
    net = verdict.net
    return {
        "headline": f"{'-' if net < 0 else ''}${abs(net):,.2f}",
        "caption": "what the bonus is worth after the playthrough, on average, at the hold you typed",
        "table": {"head": None, "rows": [["Break-even hold", f"{verdict.breakeven * 100:.2f}%"],
                                         ["Hold of that market", f"{churn * 100:.2f}%"],
                                         ["Headroom", f"{verdict.margin * 100:.2f}%"]]},
        "notes": ["The playthrough is the multiple times the deposit and bonus together, or the bonus alone when "
                  "that box is ticked, all of it bet at the hold of the market shown. Any one bet can lose; this is "
                  "the average over the whole playthrough."],
    }


def bet_and_get(v: dict) -> dict:
    """"Bet $5, get $200 in bonus bets": the qualifying bet's average cost against what the bonus converts to.
    The qualifier's chance comes from its own market with the margin removed (the four-method average)."""
    stake = _amount(v, "stake", "The qualifying stake")
    side = _price(v, "side", "The qualifying price")
    other = _price(v, "other", "The price of the other side")
    bonus = _amount(v, "bonus", "The bonus bets")
    conversion = _percent(v, "conversion", "The bonus-bet conversion rate", closed=True)
    on_win = bool(_raw(v, "on_win"))
    if 1 / side + 1 / other < 1:
        raise CalcError("Those two prices cross, so they are two books' prices, not one market. Type the qualifying "
                        "book's price for both sides.")
    win = devig_all([side, other]).consensus(0)
    loss_rate = 1 - win * side                     # what the qualifier loses on average, per dollar staked
    arrives = win if on_win else 1.0
    worth = bet_and_get_value(stake, loss_rate, bonus * arrives, conversion)
    converted = bonus * arrives * conversion
    rows = [["Qualifying bet costs, on average", f"${worth.cost:,.2f}"],
            ["Chance the qualifier wins", f"{win:.2%}"],
            ["Bonus bets received" + (", on average" if on_win else ""), f"${bonus * arrives:,.2f}"],
            ["Bonus converts to", f"${converted:,.2f}"]]
    notes = ["The conversion rate is your assumption: what share of each bonus bet you keep in cash when you bet it "
             "and cover the other side. The bonus bet conversion calculator works it out from real prices, and the "
             "cash is locked only if every bet is accepted and stands."]
    if on_win:
        notes.append("This bonus arrives only if the qualifying bet wins, so a short price collects it more often. "
                     "It cannot be hedged: a bet against the qualifier cannot pay out bonus bets.")
    else:
        notes.append("This bonus arrives whatever the qualifying bet does, so the qualifier is a small fee. Place it "
                     "on the market with the smallest margin you can find.")
    return {
        "headline": f"{'-' if worth.expected < 0 else ''}${abs(worth.expected):,.2f}",
        "caption": ("what the offer is worth on average, after the qualifying bet's cost"
                    if on_win else "what the offer is worth after the qualifying bet's cost, at your conversion rate"),
        "table": {"head": None, "rows": rows},
        "notes": notes,
    }


def spread_to_moneyline(v: dict) -> dict:
    """An NFL point spread as a moneyline: what the closing moneylines implied, on average, for favourites at that
    closing spread from 2015 to 2025, and how often those favourites actually won outright."""
    raw = _raw(v, "spread").replace("\u2212", "-").strip()
    try:
        spread = abs(float(raw.lstrip("+")))
    except ValueError:
        raise CalcError(f"{raw!r} is not a spread. Type the points, like -3.5 or 7.") from None
    if spread == 0 or spread * 2 != int(spread * 2):
        raise CalcError("Type a spread in half points other than zero, like -3 or -6.5.")
    if spread not in NFL_SPREAD:
        below = [k for k in NFL_SPREAD if k < spread]
        above = [k for k in NFL_SPREAD if k > spread]
        near = " and ".join(f"{k:g}" for k in ([max(below)] if below else []) + ([min(above)] if above else []))
        raise CalcError(f"Fewer than 40 NFL games since 2015 closed at exactly {spread:g}, too few to measure. "
                        f"The nearest spreads measured are {near}.")
    games, won, tied, fair = NFL_SPREAD[spread]
    decided = games - tied
    rate = won / decided
    z = 1.96                                       # a 95% Wilson interval on the outright rate
    centre = (rate + z * z / (2 * decided)) / (1 + z * z / decided)
    half = z * ((rate * (1 - rate) / decided + z * z / (4 * decided * decided)) ** 0.5) / (1 + z * z / decided)
    return {
        "headline": f"{_american(1 / fair)} / {_american(1 / (1 - fair))}",
        "caption": f"the fair moneyline for a {spread:g}-point NFL favourite and its underdog, with the margin removed",
        "table": {"head": None, "rows": [
            ["Favourite's chance in the closing moneylines", f"{fair:.2%}"],
            ["Games that closed at this spread, 2015 to 2025", f"{games}"],
            ["Favourites that won outright", f"{won} of {decided}, {rate:.1%}"],
            ["Range that outright rate could sit in (95%)", f"{centre - half:.1%} to {centre + half:.1%}"]]},
        "notes": [f"The moneyline is the average of each game's own closing moneylines with the margin removed, across "
                  f"every NFL game since 2015 that closed at this spread (nflverse's public games file, read "
                  f"{NFL_SPREAD_READ}). A book's posted moneyline adds its margin on top. A game with a high total "
                  f"makes the same spread a smaller edge, so one game can sit either side of this average."],
    }


def poisson(v: dict) -> dict:
    home = _amount(v, "home", "Home expected goals")
    away = _amount(v, "away", "Away expected goals")
    if home > 10 or away > 10:
        raise CalcError("Expected goals are per match, like 1.6. Above 10 is not a football score.")
    line = _number(v, "line", "The total line")
    if line <= 0 or (line * 2) != int(line * 2):
        raise CalcError("Type the total as a whole or half number, like 2.5 or 3.")
    po = poisson_build(home, away)
    res, tot = po.outcomes(), po.total_over(line)
    top = po.top_scorelines(1)[0]
    rows = [["Home", f"{res['home'] * 100:.2f}%"], ["Draw", f"{res['draw'] * 100:.2f}%"],
            ["Away", f"{res['away'] * 100:.2f}%"], [f"Over {line:g}", f"{tot['over'] * 100:.2f}%"]]
    if tot["push"]:
        rows.append([f"Push on a {line:g} line", f"{tot['push'] * 100:.2f}%"])
    rows.append(["Most likely score", f"{top['score']} at {top['prob'] * 100:.2f}%"])
    return {
        "headline": f"{res['home'] * 100:.2f}%",
        "caption": "the home side wins, under this model",
        "table": {"head": None, "rows": rows},
        "notes": ["Poisson assumes the two sides score independently. Real matches carry more draws and more "
                  "blowouts than this, so treat it as one model's opinion, not a fair price."],
    }


def middle(v: dict) -> dict:
    low = _price(v, "low", "The price on the first bet")
    high = _price(v, "high", "The price on the second bet")
    total = _amount(v, "total", "The total to stake")
    chance = _percent(v, "chance", "How often the result lands in the window")
    lo, hi = stake_middle(low, high, total, round_stakes=False)
    plan = MiddlePlan(low_line=0.0, high_line=1.0, low_book="", high_book="", low_decimal=low, high_decimal=high,
                      low_stake=lo, high_stake=hi, p_middle=chance, source="yours")
    return {
        "headline": f"{plan.ev * 100:+.2f}%",
        "caption": "expected value per unit staked, at the hit rate you typed",
        "table": {"head": None, "rows": [["Hits", f"{chance * 100:.2f}%"],
                                         ["Break-even", f"{plan.breakeven_p * 100:.2f}%"],
                                         ["Expected value", f"{plan.ev * 100:+.2f}%"]]},
        "notes": [f"Bet {lo:,.2f} on the first and {hi:,.2f} on the second. If the result lands in the window both "
                  f"win: {_signed(plan.middle_profit)}. If only one wins: {_signed(plan.one_side_profit)}, which is "
                  "the usual result. Break-even is arithmetic on the two prices; the hit rate is yours, so the "
                  "expected value is only as good as it."],
    }


def round_robin(v: dict) -> dict:
    legs = _prices(v, "legs", "The legs", 2, 8)
    size_text = _raw(v, "size")
    if not size_text.isdigit() or not 2 <= int(size_text) <= len(legs):
        raise CalcError(f"Parlays of how many legs: a whole number from 2 to {len(legs)}, like 2 for by 2s.")
    size = int(size_text)
    stake = _amount(v, "stake", "The stake on each ticket")
    probs = None
    if _raw(v, "chance"):
        probs = [_percent(v, "chance", "Each leg's win chance")] * len(legs)
    rr = round_robin_build(legs, [size], stake, probs=probs)
    # With mixed prices, which legs win changes the return, so a range is given where the engine has one.
    rows = [[f"{r['legs_won']} of {len(legs)} legs win",
             f"{r['returned_low']:,.2f} back, {_signed(r['profit_low'])}" if r["returned_low"] == r["returned_high"]
             else f"{r['returned_low']:,.2f} to {r['returned_high']:,.2f} back, {_signed(r['profit_low'])} to "
                  f"{_signed(r['profit_high'])}"]
            for r in rr.by_leg_count() if r["legs_won"] >= size]
    notes = [f"{rr.tickets} tickets at {_plain(stake)} each, so {_plain(rr.total_stake)} is at risk, not "
             f"{_plain(stake)}. At least {rr.breakeven_legs()} of the {len(legs)} legs must win to get it all back."]
    ev = rr.expected_value()
    if ev:
        rows += [[f"Expected profit, every leg at {_raw(v, 'chance').rstrip('%')}%", _signed(ev["expected_profit"])],
                 ["Same money on singles", _signed(ev["same_money_on_singles"])]]
        notes.append("Expected profit treats the legs as independent. Legs from one game are not, and then it is a "
                     "bound, not an estimate.")
    return {
        "headline": _plain(rr.total_stake),
        "caption": f"at risk: {rr.tickets} parlays of {size} legs at {_plain(stake)} each",
        "table": {"head": None, "rows": rows},
        "notes": notes,
    }


def no_vig(v: dict) -> dict:
    side = _price(v, "side", "The price for the first side")
    other = _price(v, "other", "The price for the other side")
    total = 1 / side + 1 / other
    if total < 1:
        raise CalcError(f"Those two prices imply {total:.2%} together, under 100%. One book does not price a market "
                        "that way: two books' prices that do are an arbitrage, with no margin to remove.")
    if total > 1.12:
        raise CalcError(f"Those two prices imply {total:.2%} together, a margin over 12%. That is not the two sides "
                        "of one market, so there is no fair probability to give.")
    market = devig_all([side, other])
    fair, spread = market.consensus(0), market.spread(0)
    return {
        "headline": f"{fair:.2%}",
        "caption": "consensus fair probability for the first side, with the book's margin removed",
        "table": {"head": ["Method", "First side"],
                  "rows": [[name, f"{p[0]:.2%}"] for name, p in sorted(market.by_method.items())]},
        "notes": [f"The four methods disagree by {spread * 100:.2f} points. A calculator that prints one number has "
                  "picked one of them."],
    }


def hold_calc(v: dict) -> dict:
    prices = _prices(v, "prices", "The prices", 2, 12)
    return {
        "headline": f"{hold(prices):.2%}",
        "caption": "hold: the book's margin, measured against the money bet",
        "table": {"head": None, "rows": [
            ["Implied total", f"{overround(prices):.4f}"],
            ["Hold", f"{hold(prices):.2%}"]]},
        "notes": [f"Hold is {hold(prices):.2%}, not {overround(prices) - 1:.2%}. "
                  "Reporting the overround excess overstates every book's "
                  "margin."],
    }


def bonus_conversion(v: dict) -> dict:
    amount = _amount(v, "bonus", "The bonus bet")
    free = _price(v, "free", "The price you take with the bonus bet")
    cover = _price(v, "hedge", "The price you can bet the other side at")
    plan = bonus_bet_conversion(free, cover, amount)
    ceiling = fair_conversion_ceiling(free)
    # Whole dollars when the bonus is large enough that cents are noise, which
    # is also how the worked example prints it.
    digits = 0 if amount >= 100 else 2
    cash = plan.guaranteed  # the engine's name for what this page calls locked
    stake, locked = (f"{plan.hedge_stake:,.{digits}f}",
                     f"{cash:,.{digits}f}")
    return {
        "headline": locked,
        "caption": f"locked if both bets are accepted and stand: "
                   f"{plan.conversion:.1%} of the bonus bet",
        "table": {"head": ["Free leg", "Hedge at", "Hedge stake",
                           "Locked if both stand", "Rate"],
                  "rows": [[_american(free), _american(cover), stake, locked,
                            f"{plan.conversion:.1%}"]]},
        "notes": [f"A hedge at a fair price would convert at most "
                  f"{ceiling:.1%} at this free-leg price. The hedge stake is "
                  "cash at the second book, and it is the constraint every "
                  "guide leaves out."],
    }


def no_sweat(v: dict) -> dict:
    stake = _amount(v, "stake", "The qualifying stake")
    conversion = _percent(v, "conversion", "The bonus-bet conversion rate",
                          closed=True)
    price = _price(v, "price", "The qualifying price")
    prob = _percent(v, "prob", "The chance the qualifying bet wins")
    premium = safety_net_premium(stake, prob, conversion)
    expected = safety_net_value(stake, price, prob, conversion).expected
    return {
        "headline": f"{premium:,.2f}",
        "caption": "refund value: what the offer adds, before the margin paid "
                   "to place the qualifying bet",
        "table": {"head": ["Qualifying price", "Refund value", "EV"],
                  "rows": [[_american(price), f"{premium:,.2f}",
                            f"{expected:,.2f}"]]},
        "notes": ["The refund exists only in the branch where the bet loses, "
                  "so it cannot be hedged: a hedge pays only when the bet "
                  "wins. The conversion rate is your assumption, not a "
                  "measurement."],
    }


def profit_boost(v: dict) -> dict:
    stake = _amount(v, "stake", "The stake")
    boost = _percent(v, "boost", "The boost", 500.0, closed=True)
    price = _price(v, "price", "The price")
    prob = _percent(v, "prob", "Your win probability")
    worth = profit_boost_value(stake, price, prob, boost)
    return {
        "headline": f"${worth.headline:,.2f}",
        "caption": "added to the profit if it wins",
        "table": {"head": ["Price", "Boost adds", "EV of the boosted bet"],
                  "rows": [[_american(price), f"${worth.headline:,.2f}",
                            f"${worth.expected:,.2f}"]]},
        "notes": ["The EV carries your win probability. Move it and the EV "
                  "moves with it; the boost itself is worth more the longer "
                  "the price."],
    }


def prediction_market_odds(v: dict) -> dict:
    """A Kalshi or Polymarket US contract price, as the sportsbook odds it really pays after the venue's taker fee.
    The arithmetic is the engine's (contract.price_odds), the same the app's Fair odds card runs."""
    from overlay_engine.contract import price_odds
    from overlay_engine.odds import OddsError
    price = _raw(v, "price")
    if not price:
        raise CalcError("The price is empty.")
    contracts = int(_number(v, "contracts", "Contracts")) if _raw(v, "contracts") else 100
    try:
        r = price_odds(price, _raw(v, "venue") or "kalshi", sport=_raw(v, "sport"), contracts=contracts)
    except OddsError as exc:
        raise CalcError(str(exc)) from exc
    name, n = r["venue"], r["contracts"]
    rows = [["Price", f"{r['price'] * 100:.0f}c, a {r['price']:.0%} chance as priced"],
            [f"{name} taker fee on {n:,} contracts", f"${r['fee']:,.2f}"],
            ["Cost per contract with the fee", f"{r['cost_each'] * 100:.2f}c"],
            ["Win chance you need to break even", f"{r['breakeven']:.2%}"],
            ["Odds after the fee, decimal", f"{r['decimal']:.3f}"],
            ["Odds after the fee, American", f"{r['american']:+d}"]]
    return {
        "headline": r["headline"],
        "caption": f"the sportsbook odds a {r['price'] * 100:.0f}c {name} contract pays after its fee",
        "table": {"head": None, "rows": rows},
        "notes": r["notes"],
    }


CALCULATORS = {
    "dutching": (dutching, ("total", "prices")),
    "kelly": (kelly, ("price", "prob", "bankroll", "fraction")),
    "hedge": (hedge, ("stake", "open", "lay")),
    "arbitrage": (arbitrage, ("prices", "total")),
    "closing-line-value": (closing_line_value, ("bet", "close", "other")),
    "expected-value": (expected_value, ("price", "side", "other", "own")),
    "parlay": (parlay, ("legs", "same_game")),
    "odds-converter": (odds_converter, ("prices", "stake")),
    "breakeven": (breakeven, ("prices",)),
    "hold": (hold_calc, ("prices",)),
    "no-vig-odds": (no_vig, ("side", "other")),
    "round-robin": (round_robin, ("legs", "size", "stake", "chance")),
    "middle": (middle, ("low", "high", "total", "chance")),
    "poisson": (poisson, ("home", "away", "line")),
    "effective-bets": (effective_bets, ("bets", "rho")),
    "low-hold": (low_hold, ("first", "second", "turnover")),
    "totals-middle": (totals_middle, ("low", "over", "high", "under", "total", "sigma")),
    "deposit-match": (deposit_match, ("deposit", "bonus", "rollover", "market", "bonus_only")),
    "bonus-bet-conversion": (bonus_conversion, ("bonus", "free", "hedge")),
    "no-sweat-bet": (no_sweat, ("stake", "conversion", "price", "prob")),
    "spread-to-moneyline": (spread_to_moneyline, ("spread",)),
    "bet-and-get": (bet_and_get, ("stake", "side", "other", "bonus", "conversion", "on_win")),
    "profit-boost": (profit_boost, ("stake", "boost", "price", "prob")),
    "prediction-market-odds": (prediction_market_odds, ("price", "venue", "sport", "contracts")),
}

#: The field names each calculator reads. The page's form is checked against
#: this, so a renamed input cannot quietly stop reaching the engine.
INPUTS = {slug: names for slug, (_, names) in CALCULATORS.items()}


def run(slug: str, values: dict) -> dict:
    """One calculator, on one set of typed values. Never raises."""
    if slug not in CALCULATORS:
        return {"ok": False, "error": "This page has no calculator."}
    try:
        return dict(CALCULATORS[slug][0](values), ok=True)
    except CalcError as exc:
        return {"ok": False, "error": str(exc)}
    except (ValueError, ArithmeticError) as exc:
        return {"ok": False, "error": f"Those numbers do not work out: {exc}"}


def run_json(slug: str, values_json: str) -> str:
    """The browser's entry point: JSON in, JSON out, so nothing but strings
    crosses between JavaScript and Python."""
    return json.dumps(run(slug, json.loads(values_json)))
