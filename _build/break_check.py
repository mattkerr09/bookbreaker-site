#!/usr/bin/env python3
"""Break the site on purpose and confirm `check.py` catches it.

The engine repo learned this the hard way: a gate that has never been watched
to fail is worth nothing, and two of its gates turned out to pass against
deliberately broken code. This site's gate is the only thing standing between a
hand-typed number and a public page, so it gets the same treatment.

Each case edits a rendered page, runs the gate, and restores. The restore is
verified by re-reading the file, because a silent restore failure leaves a
broken page on disk and the next green run means nothing.

    python _build/break_check.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]

CASES = [
    (
        "a hand-typed figure on a page",
        "index.html",
        "<h2>Same market, four defensible methods</h2>",
        "<h2>Same market, four defensible methods</h2>\n<p>Users average 12.7% ROI.</p>",
    ),
    (
        "a competitor's price with the date stripped",
        "vs/index.html",
        "read 2026-08-17",
        "read recently",
    ),
    (
        "a competitor claim with no source link",
        "vs/index.html",
        '<a href="https://xclsvmedia.com/oddsjam-review-2026-is-this-199-month-betting-tool-worth-it/">source</a>',
        "source",
    ),
    (
        "an internal link that goes nowhere",
        "index.html",
        'href="/how-it-works/"',
        'href="/pricing/"',
    ),
    (
        "a missing meta description",
        "index.html",
        '<meta name="description"',
        '<meta name="ignored"',
    ),
    (
        "the problem-gambling helpline removed",
        "index.html",
        "call 1-800-GAMBLER",
        "see the FAQ",
    ),
    (
        "the responsible-gambling notice removed",
        "index.html",
        "21+ and present in a state where betting is legal.",
        "Have fun out there.",
    ),
    (
        "the IndexNow key rotated without re-rendering",
        "_build/indexnow.key",
        "1d72346274f3ba1a3957eb72beea0f75",
        "0" * 32,
    ),
    (
        "a stale render published against a changed engine",
        "_build/measured.json",
        '"engine_fingerprint"',
        '"engine_fingerprint_was"',
    ),
    (
        "a redirect stub losing its canonical",
        "sportsbooks/not-covered/index.html",
        '<link rel="canonical" href="https://bookbreaker.bet/sportsbooks/in-person-only/">',
        "<!-- canonical removed -->",
    ),
    (
        "a duplicated <h2> across two pages",
        "account-longevity/index.html",
        "<h2>What a stake gives away</h2>",
        "<h2>What stays out of the product</h2>",
    ),
    (
        "two pages sharing a heading",
        "vs/index.html",
        "<h1>Compared</h1>",
        "<h1>Find your edge,<br>with the error bar.</h1>",
    ),
]


APP_REPO = "/Users/matthewkerr/arb betting aqpp"


def gate_is_clean() -> bool:
    result = subprocess.run(
        [sys.executable, str(SITE / "_build" / "check.py"),
         "--app-repo", APP_REPO],
        cwd=SITE, capture_output=True, text=True,
    )
    return result.returncode == 0


# The source check is a separate script over a separate input, so it gets a
# separate case. Its whole job is to stand behind the numbers `check.py`
# deliberately exempts, which means "it runs" and "it can fail" are two
# different claims — and today has been a catalogue of checks that ran, passed,
# and measured nothing anyone cared about.
SOURCE_CASES = [
    (
        "a cited source that 404s",
        "https://gaming.ny.gov/sports-wagering",
        "https://gaming.ny.gov/bookbreaker-break-test-does-not-exist",
    ),
]


def source_gate_is_clean() -> bool:
    run = subprocess.run([sys.executable, "_build/check_sources.py"],
                         cwd=SITE, capture_output=True, text=True, timeout=600)
    if run.returncode == 2:
        print("  SKIP     source check could not run (no network?) — "
              "this case verified nothing", file=sys.stderr)
        raise RuntimeError("source check unavailable")
    return run.returncode == 0


def run_source_cases() -> list[str]:
    """Returns the list of failures. A case that could not run is a failure,
    not a pass — the distinction this whole harness exists for."""
    failures = []
    data = SITE / "_data" / "jurisdictions.csv"
    for label, find, replace in SOURCE_CASES:
        original = data.read_text()
        if find not in original:
            failures.append(f"{label}: anchor URL not in jurisdictions.csv — stale")
            continue
        data.write_text(original.replace(find, replace, 1))
        try:
            caught = not source_gate_is_clean()
        except RuntimeError:
            failures.append(f"{label}: source check unavailable, nothing verified")
            caught = None
        finally:
            data.write_text(original)
            if data.read_text() != original:
                print("RESTORE FAILED for jurisdictions.csv", file=sys.stderr)
                raise SystemExit(2)
        if caught is not None:
            print(f"  {'caught ' if caught else 'MISSED '}  {label}")
            if not caught:
                failures.append(f"{label}: the source check passed a dead citation")
    return failures


def main() -> int:
    if not gate_is_clean():
        print("the gate is already failing — fix that before breaking anything",
              file=sys.stderr)
        return 2

    failures = []
    for label, rel, find, replace in CASES:
        path = SITE / rel
        original = path.read_text()
        if find not in original:
            failures.append(f"{label}: anchor text not found in {rel} — case is stale")
            continue

        path.write_text(original.replace(find, replace, 1))
        try:
            caught = not gate_is_clean()
        finally:
            path.write_text(original)
            if path.read_text() != original:
                print(f"RESTORE FAILED for {rel}", file=sys.stderr)
                return 2

        print(f"  {'caught ' if caught else 'MISSED '}  {label}")
        if not caught:
            failures.append(f"{label}: the gate passed against a broken page")

    failures += run_source_cases()

    print()
    if failures:
        print(f"{len(failures)} of {len(CASES) + len(SOURCE_CASES)} breaks went undetected:")
        for problem in failures:
            print(f"  - {problem}")
        return 1
    print(f"all {len(CASES) + len(SOURCE_CASES)} breaks caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
