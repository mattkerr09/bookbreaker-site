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

from overlay_engine.arb import arb_margin, ideal_stakes, stake_arb
from overlay_engine.clv import closing_fair, implied_clv
from overlay_engine.devig import devig_all
from overlay_engine.ev import breakeven_prob, ev_per_unit
from overlay_engine.kelly import MAX_SINGLE, size_bet
from overlay_engine.odds import (
    decimal_to_american, decimal_to_prob, hold, overround, parse_odds)
from overlay_engine.parlay import correlation_note, value as parlay_value
from overlay_engine.promo import (
    bonus_bet_conversion, fair_conversion_ceiling, profit_boost_value,
    safety_net_premium, safety_net_value)


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
        notes.append(
            "That is under 100%, so this is an arbitrage: the profit is locked "
            f"if {_stand(len(prices))}.")
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
            "notes": ["That understates the real edge by the closing margin. "
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
    notes = ["Each leg is assumed fairly priced against a mirror of itself, "
             "which is the generous assumption: the hold shown is a floor on "
             "the real one."]
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
    rows = [[_american(d), f"{d:.3f}", f"{decimal_to_prob(d):.2%}"] for d in prices]
    return {
        "table": {"head": ["American", "Decimal", "Implied"], "rows": rows},
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


CALCULATORS = {
    "dutching": (dutching, ("total", "prices")),
    "kelly": (kelly, ("price", "prob", "bankroll", "fraction")),
    "hedge": (hedge, ("stake", "open", "lay")),
    "arbitrage": (arbitrage, ("prices", "total")),
    "closing-line-value": (closing_line_value, ("bet", "close", "other")),
    "expected-value": (expected_value, ("price", "side", "other", "own")),
    "parlay": (parlay, ("legs", "same_game")),
    "odds-converter": (odds_converter, ("prices",)),
    "breakeven": (breakeven, ("prices",)),
    "hold": (hold_calc, ("prices",)),
    "bonus-bet-conversion": (bonus_conversion, ("bonus", "free", "hedge")),
    "no-sweat-bet": (no_sweat, ("stake", "conversion", "price", "prob")),
    "profit-boost": (profit_boost, ("stake", "boost", "price", "prob")),
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
