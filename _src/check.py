"""The gate for bookbreaker.bet as a sports STATISTICS site. Exit 0 only when every check passes.

Why each check exists:
- BANNED: the site is read by Dodo before its product form decides the matter (CEO, 2026-11-20), and BookBreaker never shows
  wagers, sportsbook prices, tips or prizes, or links to sportsbooks. The CEO named odds, picks, bets, edge, +EV and
  arbitrage; the rest are the same vocabulary. The domain name is the one allowed use of ".bet".
- LINKS: every internal link must resolve to a built file, and outbound links are limited to the company site (once per
  page, RULES 52), the analytics script and cited data sources. Anything else, above all a sportsbook, fails.
- LEFTOVERS: no directory or file from the old product may survive into the published tree.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

SITE = Path(__file__).resolve().parents[1]
from pages import PUBLISHED
from content import NFL_LICENSE
# README.md is listed because GitHub Pages copies it to /README.md as it is.
BANNED = re.compile(
    r"\bodds\b|\bpicks?\b|\bbets?\b|\bbetting\b|\bbettors?\b|\bedge\b|\+\s*EV\b|\bEV\b|\barbitrage\b|\barbs?\b|\bwagers?\b"
    r"|\bwagering\b|sportsbook|\bgambl|\bparlays?\b|\bprops?\b|\blocks?\b|\bbonus|\bpromo|\bpayouts?\b|\bjuice\b|\bvig\b"
    r"|\bspreads?\b|\bmoneyline|\bunderdog|\bfavou?rites?\b|\bhandicap|\btouts?\b|\bwin more\b|\bguarantee", re.I)
DOMAIN = re.compile(r"bookbreaker\.bet", re.I)
ALLOWED_HOSTS = {"kerrandcompanyholdings.com", "plausible.io", "github.com", "schema.org", "www.sitemaps.org"}
LEFTOVERS = ["guides", "sportsbooks", "calculators", "go", "promo-codes", "vs", "for", "best", "what-your-record-proves",
             "responsible-gambling", "offers", "how-we-are-paid", "how-it-works", "download", "ask", "ai-assistants",
             "account-longevity", "releases", "data", "media", "terms", "updater.json", "calc.js", "calc.py", "og.png",
             "_build", "_data", "_drafts"]


def allowed_hosts() -> set[str]:
    facts = json.loads((SITE / "_src/data/facts.json").read_text())
    return ALLOWED_HOSTS | {urlsplit(fact["source"]).hostname for fact in [*facts, {"source": NFL_LICENSE}]
                            if urlsplit(fact["source"]).scheme in ("http", "https")
                            and urlsplit(fact["source"]).hostname}


def main() -> int:
    fails: list[str] = []
    hosts = allowed_hosts()
    for rel in PUBLISHED:
        p = SITE / rel
        if not p.exists():
            fails.append(f"missing {rel}")
            continue
        text = p.read_text()
        visible = DOMAIN.sub("", re.sub(r"<script[^>]*src=\"[^\"]*\"", "", text))
        for m in BANNED.finditer(visible):
            line = visible.count("\n", 0, m.start()) + 1
            fails.append(f"{rel}:{line}: banned word {m.group(0)!r}")
        if rel.endswith(".html"):
            for href in re.findall(r'href="([^"]+)"', text):
                if href.startswith(("mailto:", "#")):
                    continue
                if href.startswith("/"):
                    path = href.split("#")[0].split("?")[0]
                    target = SITE / path.lstrip("/")
                    if path.endswith("/"):
                        target = target / "index.html"
                    if not (target.exists() or (SITE / (path.lstrip("/") or "index.html")).exists()):
                        fails.append(f"{rel}: internal link {href} has no file")
                    continue
                host = re.sub(r"^https?://", "", href).split("/")[0].lower()
                if host == "bookbreaker.bet":
                    continue
                if host not in hosts:
                    fails.append(f"{rel}: outbound link to {host} is not allowed")
            if text.count("https://kerrandcompanyholdings.com/") > 1 + text.count('"url": "https://kerrandcompanyholdings.com/"'):
                fails.append(f"{rel}: more than one company link (RULES 52)")
    for name in LEFTOVERS:
        if (SITE / name).exists():
            fails.append(f"leftover from the old product: {name}")
    for p in SITE.rglob("*.html"):
        rel = str(p.relative_to(SITE))
        if not rel.startswith("_src") and not any(part.startswith(".") for part in p.relative_to(SITE).parts) \
                and rel not in PUBLISHED:
            fails.append(f"unexpected page in the published tree: {rel}")
    for f in fails:
        print("FAIL", f)
    print("SITE GREEN" if not fails else f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
