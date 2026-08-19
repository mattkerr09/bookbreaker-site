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

import json
import re
import subprocess
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]

def announced_version() -> str:
    """Whatever the site currently says is out, read from the build's own
    measurements rather than typed here."""
    data = json.loads((SITE / "_build" / "measured.json").read_text())
    return data["release"]["version"]


ANNOUNCED = announced_version()



# (label, check that MUST catch it, file, find, replace)
#
# The check name is the part that was missing. Without it a case passes when
# the board goes red for any reason at all, so a case aimed at one gate can be
# satisfied by a different one tripping — and a gate with no case is never
# watched to fail at all. All 15 checks here were in that position this
# morning: proven by nothing, indistinguishable from checks that cannot fail.
CASES = [
    (
        "a hand-typed figure on a page",
        "check_numbers_are_measured",
        "index.html",
        "<h2>Same market, four defensible methods</h2>",
        "<h2>Same market, four defensible methods</h2>\n<p>Users average 12.7% ROI.</p>",
    ),
    (
        "a competitor's price with the date stripped",
        "check_competitor_claims",
        "vs/index.html",
        "read 2026-08-17",
        "read recently",
    ),
    (
        "a competitor claim with no source link",
        "check_every_competitor_row_is_sourced",
        "vs/index.html",
        '<a href="https://xclsvmedia.com/oddsjam-review-2026-is-this-199-month-betting-tool-worth-it/">source</a>',
        "source",
    ),
    (
        "an internal link that goes nowhere",
        "check_internal_links",
        "index.html",
        'href="/how-it-works/"',
        'href="/pricing/"',
    ),
    (
        "a missing meta description",
        "check_head",
        "index.html",
        '<meta name="description"',
        '<meta name="ignored"',
    ),
    (
        "the problem-gambling helpline removed",
        "check_responsible_gambling",
        "index.html",
        "call 1-800-GAMBLER",
        "see the FAQ",
    ),
    (
        "the responsible-gambling notice removed",
        "check_responsible_gambling",
        "index.html",
        "21+ and present in a state where betting is legal.",
        "Have fun out there.",
    ),
    (
        "the IndexNow key rotated without re-rendering",
        "check_indexnow_key",
        "_build/indexnow.key",
        "1d72346274f3ba1a3957eb72beea0f75",
        "0" * 32,
    ),
    (
        "a stale render published against a changed engine",
        "check_render_is_fresh",
        "_build/measured.json",
        '"engine_fingerprint"',
        '"engine_fingerprint_was"',
    ),
    (
        "a redirect stub losing its canonical",
        "check_redirects",
        "sportsbooks/not-covered/index.html",
        '<link rel="canonical" href="https://bookbreaker.bet/sportsbooks/in-person-only/">',
        "<!-- canonical removed -->",
    ),
    (
        # A single duplicated heading does not make two pages near-duplicates,
        # and this case used to plant one and call the gate proven. The board
        # went red — `check_not_machine_made` caught the repeated heading —
        # and `check_shingle_duplication` was never exercised at all. Thirteen
        # green runs said otherwise.
        #
        # This turns one state page into a copy of another, which is the
        # actual failure mode: programmatic pages that differ only by name.
        "a state page rewritten as a copy of another state's",
        "check_shingle_duplication",
        "sportsbooks/mo/index.html",
        "Missouri",
        "Kentucky",
        -1,
    ),
    (
        "two pages sharing a heading",
        "check_not_machine_made",
        "vs/index.html",
        "<h1>Compared</h1>",
        "<h1>Find your edge,<br>with the error bar.</h1>",
    ),
    (
        "a class with no rule behind it",
        "check_every_class_is_styled",
        "index.html",
        'class="hp"',
        'class="hp bb-break-case-unstyled"',
    ),
    (
        # The anchor is derived, not typed. Written first as a literal
        # "Bookbreaker 0.1.4 is out", which went stale the moment 0.1.5
        # shipped — a fixture carrying the value it is meant to track is the
        # same fault as the theme-color self-test that hardcoded the brand
        # hex it existed to check.
        "the site announcing a version it cannot hand over",
        "check_announced_version_is_downloadable",
        "index.html",
        f"Bookbreaker {ANNOUNCED} is out",
        "Bookbreaker 9.9.9 is out",
    ),
    (
        "the browser tab on last season's brand",
        "check_the_tab_and_the_page_agree",
        "index.html",
        '<meta name="theme-color" content="#1493FF">',
        '<meta name="theme-color" content="#F5A524">',
    ),
    (
        "a page missing from the sitemap",
        "check_sitemap",
        "sitemap.xml",
        "<loc>https://bookbreaker.bet/download/</loc>",
        "",
    ),
    (
        "a CSS pass that never reached the stylesheet",
        "check_every_pass_reaches_the_stylesheet",
        "style.css",
        "PASS 14",
        "PASS-FOURTEEN-NEVER-RENDERED",
    ),
    (
        "a typeface referenced but not shipped",
        "check_media_exists",
        "style.css",
        "/fonts/geist.woff2",
        "/fonts/geist-not-shipped.woff2",
    ),
    (
        "a hero video whose file is not there",
        "check_media_exists",
        "index.html",
        '/media/app.mp4',
        '/media/app-that-does-not-exist.mp4',
    ),
    (
        "a rule for a class that appears on no page",
        "check_no_dead_css",
        "style.css",
        ".own-in input:hover{",
        ".bb-class-that-exists-nowhere:hover{",
    ),
    (
        "the hero video showing a window that no longer exists",
        "check_hero_video_matches_the_app",
        "media/app-video.json",
        '"De-vig"',
        '"De-vig (renamed since the take)"',
    ),
    (
        "a runtime-class exemption left behind after its script went",
        "check_runtime_classes_are_real",
        # The defect is a stale ENTRY, so the case plants one. Removing a
        # reference from one page is not stale — the exemption is site-wide
        # and every page carries the reveal script, which is why the two
        # earlier versions of this case caught nothing.
        "_build/check.py",
        '    "reveal",',
        '    "reveal", "class-whose-script-was-deleted",',
    ),
    (
        "the download button advertising the wrong artefact's size",
        "check_announced_version_is_downloadable",
        "_build/measured.json",
        '"mb": 8.2',
        '"mb": 0.2',
    ),
    (
        "a superseded palette left in the stylesheet",
        "check_one_palette",
        "style.css",
        ":root{",
        ":root{--accent:#f5a524;",
    ),
]


# (label, check, path to create, contents)
CREATE_CASES = [
    (
        "an internal document tracked in the public site repo",
        "check_no_internal_docs_are_served",
        "DEPLOY.md",
        "# internal deploy notes planted by the break harness\n",
    ),
]


APP_REPO = "/Users/matthewkerr/arb betting aqpp"


def gate_is_clean(only: str | None = None) -> bool:
    result = subprocess.run(
        [sys.executable, str(SITE / "_build" / "check.py"),
         "--app-repo", APP_REPO] + (["--only", only] if only else []),
        cwd=SITE, capture_output=True, text=True,
    )
    return result.returncode == 0


def registered_checks() -> set[str]:
    """The checks check.py actually runs, straight from its registry."""
    source = (SITE / "_build" / "check.py").read_text()
    block = source[source.index("registry = {"):source.index("# Every check defined")]
    return set(re.findall(r'"(check_[a-z_]+)"', block))


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

    # Every check must have a case. A check with none has never been watched
    # to fail, which is not distinguishable from a check that cannot.
    unproven = (registered_checks()
                - {case[1] for case in CASES}
                - {case[1] for case in CREATE_CASES})
    if unproven:
        for name in sorted(unproven):
            print(f"  UNPROVEN  {name} — no break case aims at it")
        failures.append(f"{len(unproven)} check(s) have no break case: "
                        f"{sorted(unproven)}")

    # Cases whose defect is a file existing at all, rather than a file
    # containing the wrong thing. Written first as a find/replace that
    # replaced a string with itself — a case that cannot fail, which is the
    # exact fault this harness exists to catch.
    for label, check, rel, body in CREATE_CASES:
        path = SITE / rel
        if path.exists():
            failures.append(f"{label}: {rel} already exists — case is stale")
            continue
        path.write_text(body)
        try:
            board_red = not gate_is_clean()
            named_red = not gate_is_clean(only=check)
        finally:
            path.unlink()
            if path.exists():
                print(f"RESTORE FAILED: {rel} still there", file=sys.stderr)
                return 2
        caught = board_red and named_red
        print(f"  {'caught ' if caught else 'MISSED '}  {label}  ({check})")
        if not caught:
            failures.append(
                f"{label}: {check} did not catch a file it should refuse")

    for case in CASES:
        label, check, rel, find, replace = case[:5]
        times = case[5] if len(case) > 5 else 1
        path = SITE / rel
        original = path.read_text()
        if find not in original:
            failures.append(f"{label}: anchor text not found in {rel} — case is stale")
            continue

        path.write_text(original.replace(find, replace, times))
        try:
            board_red = not gate_is_clean()
            named_red = not gate_is_clean(only=check)
        finally:
            path.write_text(original)
            if path.read_text() != original:
                print(f"RESTORE FAILED for {rel}", file=sys.stderr)
                return 2

        caught = board_red and named_red
        print(f"  {'caught ' if caught else 'MISSED '}  {label}  ({check})")
        if not board_red:
            failures.append(f"{label}: the gate passed against a broken page")
        elif not named_red:
            failures.append(
                f"{label}: the board went red but {check} stayed green — "
                f"a different check caught it, so {check} is still unproven")

    failures += run_source_cases()

    print()
    if failures:
        print(f"{len(failures)} of {len(CASES) + len(SOURCE_CASES) + len(CREATE_CASES)} breaks went undetected:")
        for problem in failures:
            print(f"  - {problem}")
        return 1
    print(f"all {len(CASES) + len(SOURCE_CASES) + len(CREATE_CASES)} breaks caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
