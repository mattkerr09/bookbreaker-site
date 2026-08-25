#!/usr/bin/env python3
"""Notice when the world moves and this site does not.

Two kinds of claim on bookbreaker.bet rot on their own, without anybody
touching the repo:

**What competitors do and charge.** The /vs/ pages state nine rivals' prices
and features with a read date beside each one. OddsJam adding a tool, or AVO
moving off $88, makes a page here wrong while every gate stays green — the
page is internally consistent and externally stale, which is the failure mode
no check that only reads this disk can ever see.

**What regulators say.** Twenty-nine statute and regulator links back the
state pages. `check_sources.py` already asks whether they still resolve. This
asks the harder question: whether they still *say the same thing*. A live URL
whose content changed is more dangerous than a dead one, because a 404 is
visible and a quietly-amended tax rate is not.

Both are the same mechanism — fingerprint the visible text, compare against a
recorded baseline, report what moved and by how much. Deliberately not a
gate that fails the build: someone else's marketing page changing is news,
not a defect on our side. It exits 1 so a loop can surface it, and 2 when it
could not run at all, which must never be mistaken for "nothing changed".

    python3 _build/watch.py                 # report drift
    python3 _build/watch.py --accept        # record the current world as the baseline
"""

from __future__ import annotations

import argparse
import csv
import difflib
import html
import json
import re
import subprocess
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
BASELINE = SITE / "_data" / "watch_baseline.json"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0 Safari/537.36")

#: Below this, a page changed a timestamp or rotated a testimonial. Above it,
#: something was said differently. Tuned to be quiet enough that a report
#: means read me — a watcher that cries every night gets muted, and a muted
#: watcher is worse than none because it looks like coverage.
DRIFT = 0.03

#: Dollars, pounds and euros. Dollar-only missed RebelBetting's £89/mo and
#: BetBurger's €79.99/mo entirely — two of the nine prices this site states —
#: so the watcher was blind to drift on exactly the claims hardest to keep
#: current, and reported "(none found)" as though the page had no prices.
PRICE = re.compile(
    r"([$£€])\s?([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:/|\s*per\s*)?\s*"
    r"(mo|month|monthly|yr|year)?", re.I)


def fetch_pdf(url: str, timeout: int = 45) -> str | None:
    """Text out of a PDF.

    Four of the twenty-four regulator sources are PDFs — Arkansas, Arizona,
    Indiana and Missouri all publish their rules that way. Chrome's
    --dump-dom returns the PDF *viewer shell* for these, a few hundred
    characters of chrome UI with none of the document in it, so they were
    reported unreachable every single run. They answer 200 to curl; the
    fetcher was the broken part, not the sites.
    """
    from urllib.request import Request, urlopen

    try:
        request = Request(url, headers={"User-Agent": UA})
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read()
    except Exception:                                        # noqa: BLE001
        return None
    try:
        import io

        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(raw))
        return " ".join((page.extract_text() or "") for page in reader.pages)
    except Exception:                                        # noqa: BLE001
        return None


def fetch_plain(url: str, timeout: int = 45) -> str | None:
    """Markup over urllib, for HTML that headless Chrome will not serve.

    Some state sites refuse the headless user agent and answer a normal one
    fine — Florida's statute pages among them.
    """
    from urllib.request import Request, urlopen

    try:
        request = Request(url, headers={"User-Agent": UA,
                                        "Accept": "text/html,*/*"})
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.read().decode("utf-8", "replace")
    except Exception:                                        # noqa: BLE001
        return None


def content_type(url: str, timeout: int = 20) -> str:
    from urllib.request import Request, urlopen

    try:
        request = Request(url, method="HEAD", headers={"User-Agent": UA})
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            return (response.headers.get("Content-Type") or "").lower()
    except Exception:                                        # noqa: BLE001
        return ""


def fetch(url: str, timeout: int = 45) -> str | None:
    """Rendered text. Chrome, because every competitor here is a JS app.

    urllib returns an empty shell for most of these — the first version of
    this used it and reported 100% drift on six sites at once, which is what
    a broken fetcher looks like from the outside.

    But Chrome is wrong for PDFs and for the handful of state sites that
    refuse a headless agent, so both have fallbacks. Six of thirty-eight
    pages were permanently unreachable before they existed, and this file's
    own rule is that unreachable is not the same as unchanged.
    """
    kind = content_type(url)
    if "pdf" in kind or url.lower().endswith(".pdf"):
        text = fetch_pdf(url, timeout)
        return f"<pdf>{text}</pdf>" if text and len(text) > 200 else None
    try:
        done = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
             f"--virtual-time-budget={timeout * 400}", "--dump-dom", url],
            capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # A Chrome timeout used to return here, which skipped the urllib
        # fallback entirely — Florida's statute page answers urllib in a
        # second and was reported unreachable on every run because Chrome
        # hung on it first.
        plain = fetch_plain(url, timeout)
        return plain if plain and len(plain) >= 500 else None
    if done.returncode == 0 and len(done.stdout) >= 500:
        return done.stdout
    plain = fetch_plain(url, timeout)
    return plain if plain and len(plain) >= 500 else None


#: Things that differ on every request and mean nothing. Every one of these
#: fired on the watcher's first real run against live regulator sites:
#: Colorado changed a CloudFront request id, Kentucky an Akamai cache token,
#: and Virginia its lottery countdown from "05 hr : 15 mins" to "05 hr : 53
#: mins". Three pages reported as drifted, none of which had said anything
#: different. A watcher that fires daily on noise gets muted, and a muted
#: watcher is worse than none because it still looks like coverage.
VOLATILE = (
    # CDN request ids and cache tokens: long unbroken runs of hex/base64.
    re.compile(r"\b[0-9a-f]{16,}\b", re.I),
    re.compile(r"\b[a-z0-9_\-]{24,}={0,2}\b", re.I),
    # Countdown timers and clock times.
    re.compile(r"\b\d{1,2}\s*hr\s*:\s*\d{1,2}\s*mins?\b", re.I),
    re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\s*(am|pm)?\b", re.I),
    # Dates in any of the forms these sites print them.
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}t?\d{0,6}z?\b", re.I),
    # Cache-buster query strings on assets.
    re.compile(r"[?&](v|ver|t|ts|cb|rev)=[0-9a-z._-]+", re.I),
)


#: What a WAF says when it refuses us. These pages are 200s with real
#: markup, so every size check passed and they were fingerprinted as though
#: they were the source. Colorado, Kentucky and New York were all being
#: "watched" this way: the only thing that changes on a block page is the
#: request id, which is exactly the "drift" reported on the first run and
#: which the volatile-token filter then silenced. The filter was right; the
#: conclusion drawn from it was not.
BLOCKED = (
    "request is blocked", "request blocked", "access denied",
    "attention required", "you have been blocked", "403 error",
    "could not be satisfied", "service unavailable",
    "enable cookies", "are you a robot", "verify you are human",
    "checking your browser", "cf-ray",
)

#: Below this much visible text there is no page here worth comparing. A
#: statute section runs to a couple of thousand characters; a block page
#: renders to a few dozen.
MIN_TEXT = 700


def looks_blocked(text: str) -> bool:
    head = text[:1200]
    return any(phrase in head for phrase in BLOCKED)


def visible(markup: str) -> str:
    """Just the words, with the per-request noise taken out.

    A rebuild hash, a rotated asset URL, a request id or a ticking clock is
    not the page saying something different.
    """
    body = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ",
                  markup, flags=re.S | re.I)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body)).lower()
    for pattern in VOLATILE:
        text = pattern.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def prices(text: str) -> list[str]:
    """Every money figure on the page. NOT the same thing as its prices.

    Called out separately because a price is the claim on our /vs/ pages most
    likely to be both wrong and consequential, and it can move without
    shifting text similarity by one percent.

    But this cannot tell a subscription price from an earnings claim, and it
    should never be read as though it can. RebelBetting's page yields
    "€1,760/mo", which is what their marketing says a customer makes, not
    what they charge — we state £89/mo for them and both can be true at once.
    The field is money-shaped strings, and its job is to say GO AND LOOK when
    the set changes. Anything that treats it as a price oracle will publish a
    wrong number with a citation attached, which is worse than publishing
    nothing.
    """
    out = []
    for m in PRICE.finditer(text):
        unit = (m.group(3) or "").lower()
        out.append(f"{m.group(1)}{m.group(2)}" + (f"/{unit[:2]}" if unit else ""))
    return sorted(set(out))


#: Where a price actually lives. Watching only the homepage found prices on
#: three of nine competitors — the rest keep them one click away, which is
#: exactly the page whose change matters most to the /vs/ tables here.
PRICING_PATHS = ("pricing", "plans", "price", "subscribe", "membership")


def with_pricing_page(url: str) -> list[str]:
    """The homepage, then the likeliest pricing paths under it."""
    root = url.rstrip("/")
    return [url] + [f"{root}/{path}" for path in PRICING_PATHS]


def targets() -> list[dict]:
    """Everything whose change would make a page here wrong."""
    found: list[dict] = []
    comp = SITE / "_data" / "competitors.csv"
    if comp.exists():
        with comp.open() as fh:
            for row in csv.DictReader(fh):
                if row.get("url"):
                    found.append({"kind": "competitor", "id": row["slug"],
                                  "name": row["name"], "url": row["url"],
                                  "claimed_price": row.get("price", "")})
    juris = SITE / "_data" / "jurisdictions.csv"
    if juris.exists():
        seen = set()
        with juris.open() as fh:
            for row in csv.DictReader(fh):
                url = (row.get("source") or "").strip()
                if url.startswith("http") and url not in seen:
                    seen.add(url)
                    found.append({"kind": "source", "id": row["code"],
                                  "name": f"{row['code']} regulator",
                                  "url": url, "claimed_price": ""})
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--accept", action="store_true",
                    help="record the world as it is now")
    ap.add_argument("--only", default=None, help="competitor|source")
    args = ap.parse_args()

    base = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    watch = [t for t in targets()
             if not args.only or t["kind"] == args.only]
    if not watch:
        print("nothing to watch — no competitors.csv or jurisdictions.csv",
              file=sys.stderr)
        return 2

    fresh, drifted, unreachable = {}, [], []
    for t in watch:
        markup, got_from = None, t["url"]
        # A competitor's prices are usually one click from the homepage. Try
        # the homepage first, then the likely pricing paths, and keep the
        # first page that actually quotes money — that is the page whose
        # change would make our /vs/ table wrong.
        candidates = (with_pricing_page(t["url"]) if t["kind"] == "competitor"
                      else [t["url"]])
        for candidate in candidates:
            page = fetch(candidate)
            if page is None:
                continue
            if markup is None:
                markup, got_from = page, candidate
            if prices(visible(page)):
                markup, got_from = page, candidate
                break
        if markup is None:
            unreachable.append(t)
            # Carry the old fingerprint forward so one unreachable page does
            # not erase what we knew about it.
            if t["id"] in base:
                fresh[t["id"]] = base[t["id"]]
            continue
        text = visible(markup)
        # A 200 carrying a WAF challenge is not the page. Treating it as one
        # made three regulator sources look watched while nothing was being
        # compared but an error message.
        if looks_blocked(text) or len(text) < MIN_TEXT:
            why = "blocked" if looks_blocked(text) else f"only {len(text)} chars"
            unreachable.append(dict(t, why=why))
            if t["id"] in base:
                fresh[t["id"]] = base[t["id"]]
            continue

        record = {"url": got_from, "name": t["name"], "kind": t["kind"],
                  "words": len(text.split()), "prices": prices(text),
                  "text": text[:120000]}
        fresh[t["id"]] = record

        was = base.get(t["id"])
        if not was:
            drifted.append((t, 1.0, "new — nothing recorded before"))
            continue
        # Arkansas publishes a 963,000-character PDF. A 20,000-character
        # window compared 2% of it and would have called the other 98%
        # unchanged without ever reading it.
        ratio = difflib.SequenceMatcher(None, was.get("text", ""),
                                        record["text"]).quick_ratio()
        moved = 1.0 - ratio
        price_change = set(was.get("prices", [])) != set(record["prices"])
        if price_change:
            gone = sorted(set(was.get("prices", [])) - set(record["prices"]))
            new = sorted(set(record["prices"]) - set(was.get("prices", [])))
            drifted.append((t, moved,
                            f"MONEY FIGURES changed  -{gone[:4]} +{new[:4]}"))
        elif moved >= DRIFT:
            drifted.append((t, moved, f"{moved:.0%} of the text changed"))

    if args.accept:
        BASELINE.write_text(json.dumps(fresh, indent=1, sort_keys=True) + "\n")
        print(f"baseline recorded: {len(fresh)} page(s)")
        return 0

    print(f"watched {len(watch)} page(s), {len(unreachable)} unreachable\n")
    for t, moved, why in drifted:
        print(f"  {t['kind']:<11} {t['name'][:28]:<30} {why}")
        if t["claimed_price"]:
            print(f"{'':>13}this site states {t['claimed_price']!r} — verify "
                  f"by hand; these figures include earnings claims")
    if unreachable:
        print(f"\n  {len(unreachable)} not readable:")
        for t in unreachable:
            print(f"    {t['name'][:30]:<32} {t.get('why', 'no response')}")

    if not BASELINE.exists():
        print("\nno baseline yet — run with --accept to record one")
        return 2
    if unreachable and not drifted:
        print("\nnothing changed among the pages that answered, but "
              f"{len(unreachable)} did not. That is not the same as clean.")
        return 2
    if drifted:
        print(f"\n{len(drifted)} page(s) moved. Read them, then update "
              f"_data/competitors.csv and re-run with --accept.")
        return 1
    print("nothing moved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
