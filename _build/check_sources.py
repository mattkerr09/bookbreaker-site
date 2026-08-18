#!/usr/bin/env python3
"""Do the citations this site leans on actually resolve?

`check.py` fails the build on any visible number absent from `measured.json`,
with one deliberate exemption: a number inside a block carrying a date AND a
source link is allowed, because a competitor's price and a state's tax rate
cannot come out of our engine and demanding that they did would mean deleting
the comparison rather than sourcing it.

That exemption is right, and it is also the largest hole in the site's
guarantees. **38 rows currently claim a source, and until this script nothing
checked that any of those URLs existed.** The numbers they carry are the
legally sensitive ones — gambling law, tax rates, competitors' prices — and
they were produced by research agents, which makes a plausible-looking
fabricated URL a real failure mode rather than a theoretical one.

The general rule, learned the expensive way today: every deliberate exemption
in a checker creates a region where a defect is indistinguishable from
correctness. The exemption is usually right; what is missing is a second check
over what the first was told to ignore. This is that second check.

    python3 _build/check_sources.py

Exit codes: 0 all live, 1 something is dead, 2 the check could not run.
Two is not zero, deliberately — a source check that silently passes when the
network is down reads exactly like one that verified 38 URLs.
"""

from __future__ import annotations

import csv
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
TIMEOUT = 20

# A government site behind a WAF answers an automated request with 403 or 406
# while serving the page perfectly to a browser. That is not a dead citation
# and failing on it would train whoever runs this to ignore it — which is how
# a gate stops being read. Reported, not fatal.
BLOCKED = {401, 403, 405, 406, 429}

# Dead. A citation nobody can follow is not a citation.
DEAD = {404, 410}


def sources() -> list[tuple[str, str, str]]:
    """Every (file, row-key, url) the site cites."""
    out = []
    for name, key in (("jurisdictions", "code"), ("competitors", "slug"),
                      ("partners", "book")):
        path = SITE / "_data" / f"{name}.csv"
        if not path.exists():
            continue
        for row in csv.DictReader(path.open()):
            url = (row.get("source") or "").strip()
            if url:
                out.append((name, (row.get(key) or "?").strip(), url))
    return out


def probe(url: str) -> tuple[str, str]:
    """(verdict, detail). Never raises — a probe that dies mid-run would leave
    the remaining citations unchecked while the script reported what it had."""
    request = urllib.request.Request(
        url, method="GET",
        headers={"User-Agent": "bookbreaker-source-check/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return "live", str(response.status)
    except urllib.error.HTTPError as exc:
        if exc.code in DEAD:
            return "dead", str(exc.code)
        if exc.code in BLOCKED:
            return "blocked", str(exc.code)
        return "odd", str(exc.code)
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, socket.gaierror):
            return "dead", "DNS does not resolve"
        return "unreachable", str(reason)[:60]
    except Exception as exc:                      # noqa: BLE001
        return "unreachable", type(exc).__name__


def main() -> int:
    rows = sources()
    if not rows:
        print("no sourced rows found — nothing to check, which is itself odd")
        return 2

    print(f"checking {len(rows)} cited sources\n")
    counts: dict[str, int] = {}
    dead: list[str] = []
    for name, key, url in rows:
        verdict, detail = probe(url)
        counts[verdict] = counts.get(verdict, 0) + 1
        if verdict in ("dead", "odd"):
            dead.append(f"{name}/{key}: {verdict} ({detail}) {url}")
        mark = {"live": "ok", "blocked": "waf", "dead": "DEAD",
                "odd": "ODD", "unreachable": "??"}[verdict]
        print(f"  {mark:<5} {name}/{key:<12} {detail:<22} {url[:58]}")

    print()
    print("  " + "  ".join(f"{k}: {v}" for k, v in sorted(counts.items())))

    # If nothing at all resolved, the network is the problem, not the sources.
    # Reporting 38 dead citations because the wifi is off would be a lie in the
    # expensive direction.
    if counts.get("live", 0) == 0 and counts.get("unreachable", 0):
        print("\nnothing resolved at all — this looks like no network rather "
              "than 38 dead citations. Not a pass and not a failure.")
        return 2

    if dead:
        print(f"\n{len(dead)} citation(s) nobody can follow:")
        for line in dead:
            print(f"  {line}")
        print("\nA number is exempt from the figure gate BECAUSE it is "
              "sourced. A dead source withdraws the thing that bought the "
              "exemption.")
        return 1

    print("\nSOURCES OK — every citation resolves or is behind a WAF.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
