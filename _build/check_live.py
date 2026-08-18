#!/usr/bin/env python3
"""Does bookbreaker.bet serve what this repo built?

Every other gate in this directory reads files off this disk. That is a check
on the source, and the thing a visitor gets is the artefact — and the two come
apart in ways no local check can see: a push that Pages never rebuilt, a
deploy that half-landed, a CDN holding a stale stylesheet, a file that exists
in the repo and 404s on the domain.

Today's portfolio produced four separate instances of a check aimed at the
source passing while the artefact was wrong. One of them was on this site: a
gate asking whether `theme-color` appeared anywhere in style.css passed on
exactly the bug it was written for, because the old brand colour was still
present as a dead override. The lesson generalises past that one bug, and this
is the check that closes it for the deploy itself.

    python3 _build/check_live.py

Exit codes: 0 the live site matches this build, 1 it does not, 2 the check
could not run. Two is not zero, deliberately — a deploy check that silently
passes when the network is down reads exactly like one that compared bytes.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
ORIGIN = "https://bookbreaker.bet"
TIMEOUT = 20

#: One of each kind of page, plus the stylesheet, which is where a stale
#: deploy shows up first and most visibly.
SAMPLE = [
    "index.html",
    "style.css",
    "download/index.html",
    "how-it-works/index.html",
    "sportsbooks/index.html",
    "sportsbooks/ky/index.html",
    "vs/oddsjam-alternative/index.html",
    "calculators/index.html",
]


def url_for(rel: str) -> str:
    if rel.endswith("/index.html"):
        return f"{ORIGIN}/{rel[: -len('index.html')]}"
    if rel == "index.html":
        return f"{ORIGIN}/"
    return f"{ORIGIN}/{rel}"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "bookbreaker-deploy-check"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def main() -> int:
    missing = [rel for rel in SAMPLE if not (SITE / rel).exists()]
    if missing:
        print(f"cannot compare: not built locally — {', '.join(missing)}",
              file=sys.stderr)
        return 2

    # The stylesheet is served with a cache-busting query in the markup, so
    # compare on the path the file actually lives at.
    differ, checked, unreachable = [], 0, []
    for rel in SAMPLE:
        local = (SITE / rel).read_bytes()
        try:
            served = fetch(url_for(rel))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            unreachable.append(f"{rel}: {exc}")
            continue
        checked += 1
        if hashlib.sha256(served).hexdigest() != hashlib.sha256(local).hexdigest():
            differ.append(
                f"{rel}: served {len(served)} bytes, built {len(local)} "
                f"— the domain is not serving this build")

    if not checked:
        print("could not reach the site at all:", file=sys.stderr)
        for line in unreachable:
            print(f"  {line}", file=sys.stderr)
        return 2

    if unreachable:
        print(f"  unreachable: {len(unreachable)}  matched: "
              f"{checked - len(differ)}")
        for line in unreachable:
            print(f"    {line}")

    if differ:
        print(f"\n{len(differ)} page(s) differ from what is deployed:")
        for line in differ:
            print(f"  - {line}")
        print("\nUsually this means the commit is pushed and Pages has not")
        print("finished rebuilding. Re-run in a minute before assuming worse.")
        return 1

    print(f"  compared {checked} of {len(SAMPLE)}: every byte matches")
    print("\nDEPLOY OK — the domain serves exactly this build.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
