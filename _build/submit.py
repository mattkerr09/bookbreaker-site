#!/usr/bin/env python3
"""Tell the search engines the site changed.

One POST to IndexNow reaches Bing, Yandex, Seznam and Naver. Google dropped its
sitemap ping endpoint in 2023 and takes submissions only through Search
Console, which needs an account — so this covers four engines and not the fifth,
and says so rather than implying it covered them all.

**It refuses to run against a site that is not serving the current pages.**
IndexNow verifies ownership by fetching a key file from the host, so a
submission made before the deploy finishes is rejected — and a rejected batch
that looks like a success is worse than not running at all. The check cannot
distinguish "not deployed yet" from "broken", which is exactly why the order in
DEPLOY.md is render, gate, commit, push, *wait*, submit.

    python3 _build/submit.py
    python3 _build/submit.py --dry-run

Exit 0 when every endpoint accepted, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
HOST = "bookbreaker.bet"
ORIGIN = f"https://{HOST}"

# api.indexnow.org fans out to every participating engine; bing is listed
# separately because it is the one that actually drives traffic here and a
# partial outage should be visible rather than averaged away.
ENDPOINTS = (
    "https://api.indexnow.org/indexnow",
    "https://www.bing.com/indexnow",
)

# IndexNow's documented success codes. 200 is "accepted", 202 is "accepted,
# key validation pending" — both mean the batch was taken.
ACCEPTED = (200, 202)

TIMEOUT = 30


def read_key() -> str:
    path = SITE / "_build" / "indexnow.key"
    if not path.exists():
        raise SystemExit(f"no key at {path}")
    key = path.read_text().strip()
    if not re.fullmatch(r"[0-9a-fA-F]{8,128}", key):
        raise SystemExit(
            f"key must be 8-128 hex characters, got {len(key)} characters"
        )
    return key


def sitemap_urls() -> list[str]:
    path = SITE / "sitemap.xml"
    if not path.exists():
        raise SystemExit("no sitemap.xml — run render.py first")
    urls = re.findall(r"<loc>([^<]+)</loc>", path.read_text())
    off_host = [u for u in urls if not u.startswith(ORIGIN)]
    if off_host:
        raise SystemExit(
            f"sitemap contains URLs off {HOST}: {off_host[:3]} — IndexNow "
            "rejects a batch whose URLs do not all match the host"
        )
    return urls


def fetch(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "bookbreaker"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")
    except Exception as exc:  # network down, DNS, TLS
        return 0, str(exc)


def live_key_matches(key: str) -> tuple[bool, str]:
    """Whether the deployed site serves the key file we are about to claim.

    This is the whole safety of the script. Without it a submission fired
    before the Pages build finishes is rejected for a reason nobody sees, and
    the run looks identical to a successful one.
    """
    status, body = fetch(f"{ORIGIN}/{key}.txt")
    if status != 200:
        return False, f"{ORIGIN}/{key}.txt returned {status or 'no response'}"
    if body.strip() != key:
        return False, "the key file is served but does not contain the key"
    return True, "key file served and matching"


def live_serves(urls: list[str], sample: int = 3) -> tuple[bool, str]:
    """Spot-check that the live site is serving the pages being submitted."""
    for url in urls[:sample]:
        status, _ = fetch(url)
        if status != 200:
            return False, f"{url} returned {status or 'no response'}"
    return True, f"{min(sample, len(urls))} pages checked, all 200"


def submit(endpoint: str, payload: dict) -> tuple[int, str]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent": "bookbreaker"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")[:200]
    except Exception as exc:
        return 0, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="run every check but post nothing")
    args = parser.parse_args()

    key = read_key()
    urls = sitemap_urls()
    print(f"{len(urls)} URLs from sitemap.xml")

    ok, why = live_key_matches(key)
    print(f"  key file: {why}")
    if not ok:
        print("\nRefusing to submit. IndexNow verifies ownership by fetching",
              file=sys.stderr)
        print("that file, so this batch would be rejected — and a rejected",
              file=sys.stderr)
        print("batch that looks like a success is worse than not running.",
              file=sys.stderr)
        print("If you have just pushed, wait for the Pages build to report",
              file=sys.stderr)
        print("the pushed commit and try again.", file=sys.stderr)
        return 1

    ok, why = live_serves(urls)
    print(f"  live pages: {why}")
    if not ok:
        print("\nRefusing to submit: the site is not serving the pages being",
              file=sys.stderr)
        print("submitted.", file=sys.stderr)
        return 1

    payload = {
        "host": HOST,
        "key": key,
        "keyLocation": f"{ORIGIN}/{key}.txt",
        "urlList": urls,
    }

    if args.dry_run:
        print(f"\ndry run — would POST {len(urls)} URLs to "
              f"{len(ENDPOINTS)} endpoints")
        return 0

    print()
    failed = []
    for endpoint in ENDPOINTS:
        status, body = submit(endpoint, payload)
        verdict = "accepted" if status in ACCEPTED else "REJECTED"
        print(f"  {verdict:<9} {status:<4} {endpoint}")
        if status not in ACCEPTED:
            failed.append(f"{endpoint}: {status} {body.strip()[:120]}")

    print()
    if failed:
        print(f"{len(failed)} endpoint(s) rejected the batch:")
        for problem in failed:
            print(f"  - {problem}")
        return 1

    print(f"{len(urls)} URLs submitted to Bing, Yandex, Seznam and Naver.")
    print("Google is not covered — it dropped sitemap ping in 2023 and takes")
    print("submissions only through Search Console.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
