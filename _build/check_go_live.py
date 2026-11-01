#!/usr/bin/env python3
"""Does every /go/<key>/ page the app can open answer on the live domain?

The app's shell opens https://bookbreaker.bet/go/<key>/?state=..&src=app-.. for each key in GO_BOOKS (main.rs), from
Open this offer and from Open <book> on a play. check.py holds that each page exists in this repo; this asks the
domain, because a page in the repo that Pages does not serve is still a 404 to the person who pressed the button.

    python3 _build/check_go_live.py [--app-repo PATH]

Exit codes, as check_sources.py: 0 every page answered below 400, 1 at least one answered 4xx or 5xx, 2 the check
could not run (no network). Two is never a pass.
"""
import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check import app_go_books  # noqa: E402

TIMEOUT = 20


def status(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "bookbreaker-go-check"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-repo", default=os.environ.get("APP_REPO", "../arb betting aqpp"))
    args = ap.parse_args()
    keys = app_go_books(Path(args.app_repo).expanduser().resolve())
    if not keys:
        print("could not read GO_BOOKS from the app, so nothing was checked")
        return 2
    bad, unreachable = [], 0
    for key in keys:
        code = status(f"https://bookbreaker.bet/go/{key}/?state=MI&src=app-board")
        if code is None:
            unreachable += 1
        elif code >= 400:
            bad.append(f"/go/{key}/ answered {code}")
    if unreachable == len(keys):
        print("no /go/ page answered at all: this looks like no network, not a broken site. Not a pass.")
        return 2
    if bad:
        for line in bad:
            print(f"  {line}")
        print(f"{len(bad)} page(s) the app can open do not answer: a button in the app lands on an error.")
        return 1
    print(f"GO PAGES OK: all {len(keys) - unreachable} of {len(keys)} pages the app can open answered"
          + (f" ({unreachable} unreachable)" if unreachable else "") + ".")
    return 1 if unreachable else 0


if __name__ == "__main__":
    sys.exit(main())
