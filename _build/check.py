#!/usr/bin/env python3
"""The publish gate. Nothing goes out unless this is clean.

Three failure modes, each of which has actually happened in a sibling project:

**A number nobody measured.** A cost table was published in AdPlaybook's README
labelled "measured on a real run", from a run that never happened, and it
propagated into a billing page headed for payment-processor onboarding. This
site's whole claim is that other tools print numbers more certain than they
are, so a hand-typed figure here is not a small error — it is the product's
argument turned on itself. Every figure on a page must appear in
`measured.json`, which `render.py` writes from the engine's actual output.

**An undated claim about someone else.** Docket's README asserted a
competitor's yearly price with no date and no source; the price was already
wrong and the vendor did not publish yearly totals at all. Naming a competitor
is fine. Stating their price or capability without a date and a link is not.

**A page that reads as machine-made.** Same skeleton, same opening, same
headings across a generated set is what a thin-content penalty is.

    python _build/check.py

Exit 0 when clean, 1 otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]

# Numbers that are structure rather than measurement: years, viewport widths,
# the legal age, HTTP-ish tokens. Everything else must be traceable.
STRUCTURAL = {
    "1", "21", "2026", "0", "9", "0.9", "1.0", "3", "7", "200", "220.5",
    "30", "100", "2",
}

# Two generated pages may not exceed this overlap in body text. Set from
# measurement, not taste: after merging the states that shared an answer, the
# closest surviving pair sits at 0.960, and the pairs this is meant to catch —
# states with byte-identical venue lists — measured 0.973 and 0.984 before they
# were merged. 0.97 sits in the gap between the two populations.
MAX_FAMILY_SIMILARITY = 0.97

# The portfolio's own gate measures 5-word shingles, not word sets, and holds
# every other site to zero pairs at 0.5. This site scored 442 while passing its
# own check, because a word-set comparison is far too forgiving: two pages can
# share a vocabulary and score low while sharing whole paragraphs. Shingles
# catch reused phrasing, which is what a search engine collapses.
#
# The bar is a ratchet, not an aspiration. It is set to what the site currently
# achieves so a regression fails the build, and it is lowered as pages get more
# genuinely different — never raised to accommodate one that got worse.
SHINGLE_SIMILARITY = 0.5
WATCH_SIMILARITY = 0.35
MAX_SHINGLE_PAIRS = 19

# The whole similarity zone, not just the headline above it.
#
# Counting only pairs over 0.5 made a 60% "improvement" that moved almost
# nothing: 442 near-duplicates became 176, and 255 pairs appeared in a
# 0.35-0.5 band that had been EMPTY. Eleven pairs actually left the zone.
# Google has no 0.5 cliff — a pair at 0.47 is not meaningfully less
# collapsible than the same pair at 0.52 — so a gate that watches one side of
# an arbitrary line rewards pushing pairs across it.
MAX_ZONE_PAIRS = 365

# Words that turn naming a competitor into asserting something about them.
ASSERTIVE = re.compile(
    r"\b(costs?|charges?|prices?|priced|per month|/mo|does not|cannot|"
    r"fails? to|lacks?|only offers?|limited to|delay)\b", re.I)


def visible(markup: str) -> str:
    markup = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", markup)
    return re.sub(r"\s+", " ",
                  html.unescape(re.sub(r"<[^>]+>", " ", markup))).strip()


def numbers_in(text: str) -> set[str]:
    """Every numeric token on a page, normalised for comparison."""
    found = set()
    for raw in re.findall(r"[-+]?\d[\d,]*\.?\d*", text):
        token = raw.replace(",", "").lstrip("+")
        token = token.rstrip(".") or "0"
        if token.startswith("-"):
            token = token[1:]
        # Drop trailing zeros so 90.91 and 90.910 compare equal.
        if "." in token:
            token = token.rstrip("0").rstrip(".") or "0"
        found.add(token)
    return found


def measured_numbers(data) -> set[str]:
    """Every number `render.py` recorded, flattened."""
    out: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, bool):
            return
        elif isinstance(node, (int, float)):
            out.update(numbers_in(f"{node}"))
        elif isinstance(node, str):
            out.update(numbers_in(node))

    walk(data)
    return out


SOURCE_LINK = re.compile(r'<a href="https?://[^"]+"[^>]*>\s*source\s*</a>', re.I)


def has_source(block: str) -> bool:
    """Whether a block carries an explicit source link.

    Not merely *a* link. Every competitor row also links the vendor's own
    homepage, and a homepage is not a source for a claim about that vendor's
    price — the break harness caught this by stripping the source link and
    watching the gate pass on the strength of the name link beside it.
    """
    return bool(SOURCE_LINK.search(block))


def sourced_rows(markup: str) -> list[str]:
    """Blocks carrying both a date and a source link — the only place a number
    this engine cannot compute is allowed to appear.

    A competitor's price is a fact about someone else's product. It cannot come
    out of our engine, and demanding that it did would mean deleting the
    comparison rather than sourcing it. So such a number is permitted exactly
    where it is dated and linked, and nowhere else. The carve-out is scoped to
    the row, not the page, so an unsourced claim two rows down is still caught.
    """
    blocks = (re.findall(r"(?s)<tr>.*?</tr>", markup)
              + re.findall(r"(?s)<p[^>]*>.*?</p>", markup)
              + re.findall(r"(?s)<li>.*?</li>", markup))
    return [
        block for block in blocks
        if re.search(r"\b20\d\d-\d\d-\d\d\b", block) and has_source(block)
    ]


def check_numbers_are_measured(pages, measured, fails):
    """Every figure on a page must be traceable to the engine's output, or to
    a dated and linked third-party source."""
    allowed = measured_numbers(measured) | STRUCTURAL
    for path, markup in pages:
        exempt: set[str] = set()
        for row in sourced_rows(markup):
            exempt |= numbers_in(visible(row))

        page_numbers = numbers_in(visible(markup))
        for token in page_numbers - allowed - exempt:
            fails.append(
                f"{path}: the figure {token} appears on the page but not in "
                "measured.json — either compute it in render.py, or put it in "
                "a row carrying a date and a source link"
            )


def check_competitor_claims(pages, fails):
    """Naming a competitor is fine; asserting their price or policy is not,
    unless the claim carries a date and a source.

    Checked per table row and per paragraph, not per sentence. Flattening a
    table to text runs every row together, so a sentence-level check reported
    a properly-dated row as undated — the gate was wrong, not the page.
    """
    names = [c["name"] for c in json.loads(
        (SITE / "_build" / "competitors.json").read_text())]

    for path, markup in pages:
        blocks = re.findall(r"(?s)<tr>.*?</tr>", markup)
        blocks += re.findall(r"(?s)<p[^>]*>.*?</p>", markup)
        blocks += re.findall(r"(?s)<li>.*?</li>", markup)

        for block in blocks:
            text = visible(block)
            hit = next((n for n in names if n in text), None)
            if not hit or not ASSERTIVE.search(text):
                continue
            if not re.search(r"\b20\d\d-\d\d-\d\d\b", text):
                fails.append(
                    f"{path}: asserts something about {hit} without a date: "
                    f"{text[:110]!r}"
                )
            elif not has_source(block):
                fails.append(
                    f"{path}: dated claim about {hit} with no source link: "
                    f"{text[:110]!r}"
                )


def check_every_competitor_row_is_sourced(pages, fails):
    """Each row of the comparison table must carry a date and a link.

    Separate from the claim check because a row can name no competitor by an
    assertive verb and still be a table of their prices.
    """
    for path, markup in pages:
        if "vs/" not in path:
            continue
        rows = re.findall(r"(?s)<tr>.*?</tr>", markup)[1:]
        for row in rows:
            if not re.search(r"\b20\d\d-\d\d-\d\d\b", row):
                fails.append(f"{path}: comparison row with no date: "
                             f"{visible(row)[:80]!r}")
            elif not has_source(row):
                fails.append(f"{path}: comparison row with no source link: "
                             f"{visible(row)[:80]!r}")


def check_render_is_fresh(measured, fails, app_repo: Path):
    """Refuse to publish a render made against an older engine.

    `render.py` chooses which figures to compute, so an engine change that
    alters a number leaves the site quietly showing the old one and nothing
    about the page looks wrong. The roadmap named this as the thing most likely
    to go stale; a fingerprint over the engine source turns it into a failure
    rather than a slow drift.
    """
    recorded = measured.get("engine_fingerprint")
    if not recorded:
        fails.append("measured.json has no engine fingerprint — re-run render.py")
        return

    root = app_repo / "backend" / "overlay_engine"
    if not root.exists():
        fails.append(
            f"cannot verify the render is current: no engine at {root}. "
            "Pass --app-repo, because publishing without being able to check "
            "freshness is the failure this gate exists for."
        )
        return

    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    current = digest.hexdigest()[:16]

    if current != recorded:
        fails.append(
            f"the engine has changed since this render ({recorded} -> "
            f"{current}) — re-run render.py before publishing"
        )


def check_indexnow_key(fails):
    """The key file must exist at the site root and contain the key.

    `submit.py` refuses to post without it, so a missing key file turns every
    future submission into a no-op that reports success at the shell. Catching
    it here means the failure lands at build time instead.
    """
    key_path = SITE / "_build" / "indexnow.key"
    if not key_path.exists():
        return  # no key configured; submission is simply not set up

    key = key_path.read_text().strip()
    served = SITE / f"{key}.txt"
    if not served.exists():
        fails.append(
            f"the IndexNow key file {key}.txt is not in the site root — "
            "re-run render.py, which writes it"
        )
    elif served.read_text().strip() != key:
        fails.append(f"{key}.txt does not contain the key it is named for")


REDIRECT = re.compile(r'http-equiv="refresh"[^>]*url=([^"]+)"', re.I)


def is_redirect(markup: str) -> bool:
    return bool(REDIRECT.search(markup))


def check_redirects(redirects, fails):
    """A redirect stub needs a target and a canonical, and nothing else.

    Checked rather than skipped. A stub with no canonical leaves the old URL
    competing with the new one in the index, and a stub whose refresh target is
    itself is a loop that only a reader discovers.
    """
    for path, markup in redirects:
        target = REDIRECT.search(markup)
        if not target:
            fails.append(f"{path}: looks like a redirect but has no target")
            continue
        destination = target.group(1)
        if not destination.startswith("/"):
            fails.append(f"{path}: redirect target {destination!r} is not a "
                         "site-relative path")
        if f'rel="canonical" href="https://bookbreaker.bet{destination}"' not in markup:
            fails.append(
                f"{path}: redirect to {destination} without a canonical "
                "pointing there — the old URL keeps competing with the new one"
            )
        if path.rsplit("/", 1)[0] == destination.strip("/"):
            fails.append(f"{path}: redirects to itself")


def check_head(pages, fails):
    for path, markup in pages:
        for tag, pattern in (
            ("title", r"<title>([^<]{10,70})</title>"),
            ("description", r'name="description" content="([^"]{50,160})"'),
            ("canonical", r'rel="canonical" href="https://bookbreaker\.bet'),
        ):
            if not re.search(pattern, markup):
                fails.append(f"{path}: missing or malformed {tag}")


def check_internal_links(pages, fails):
    for path, markup in pages:
        for raw in re.findall(r'href="(/[^"#]*)"', markup):
            # Strip the cache-busting query. A versioned asset URL is an
            # ordinary thing and resolving it as a literal path reported every
            # page on the site as linking to a file that does not exist.
            href = raw.split("?", 1)[0]
            target = SITE / href.strip("/") if href != "/" else SITE
            if href.endswith((".css", ".xml", ".txt")):
                target = SITE / href.lstrip("/")
            elif target.is_dir() or href.endswith("/") or href == "/":
                target = target / "index.html"
            if not target.exists():
                fails.append(f"{path}: link to {href} goes nowhere")


def check_sitemap(pages, fails):
    listed = set(re.findall(r"<loc>https://bookbreaker\.bet([^<]*)</loc>",
                            (SITE / "sitemap.xml").read_text()))
    on_disk = set()
    for path, _ in pages:
        on_disk.add("/" if path == "index.html"
                    else "/" + path.rsplit("/", 1)[0] + "/")
    if listed != on_disk:
        fails.append(
            f"sitemap lists {sorted(listed)} but the site has {sorted(on_disk)}"
        )


def body_words(markup: str) -> set[str]:
    main = re.search(r"(?s)<main>(.*?)</main>", markup)
    return set(visible(main.group(1) if main else markup).lower().split())


def shingles(markup: str, n: int = 3) -> set:
    """Trigrams over body text, matching `~/ops/bin/similarity-gate.py` exactly.

    Both halves of this were wrong on the first attempt and the difference
    mattered: 5-word shingles scoped to `<main>` reported 28 where the
    portfolio gate reported 176 on the same pages. Trigrams are far more
    permissive — they catch reused *phrasing* rather than reused sentences —
    and the portfolio strips only the chrome tags rather than keeping `<main>`,
    so a disclosure or a caveat outside `<main>` still counts as shared text.

    A local gate that disagrees with the portfolio gate is worse than no local
    gate: it reports green on a site the authoritative tool is failing. So this
    is a copy, not an improvement.
    """
    raw = re.sub(r"<(script|style|head|nav|footer|header)[^>]*>.*?</\1>", " ",
                 markup, flags=re.S | re.I)
    raw = re.sub(r"<!--.*?-->", " ", raw, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    words = re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split()
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def check_shingle_duplication(pages, fails, limit=None):
    """Count near-duplicate pairs the way the portfolio gate does.

    Reported as a total rather than per page: the failure is a cluster that
    duplicates itself, and naming 442 individual pairs buries that.
    """
    body = {path: shingles(markup) for path, markup in pages}
    body = {k: v for k, v in body.items() if len(v) >= 40}
    paths = sorted(body)
    pairs, all_pairs = [], []
    for i, a in enumerate(paths):
        for b in paths[i + 1:]:
            union = body[a] | body[b]
            if not union:
                continue
            overlap = len(body[a] & body[b]) / len(union)
            all_pairs.append((overlap, a, b))
            if overlap >= SHINGLE_SIMILARITY:
                pairs.append((overlap, a, b))
    cap = MAX_SHINGLE_PAIRS if limit is None else limit
    zone = [p for p in all_pairs if p[0] >= WATCH_SIMILARITY]
    zone_cap = MAX_ZONE_PAIRS if limit is None else max(limit, 0)
    if len(zone) > zone_cap:
        fails.append(
            f"{len(zone)} page pairs in the similarity zone (>= "
            f"{WATCH_SIMILARITY:.0%}), above the {zone_cap} this site is held "
            "to. Pushing pairs from above 0.5 to just below it is not an "
            "improvement; this is the count that says whether they moved or "
            "changed.")
    if len(pairs) > cap:
        pairs.sort(reverse=True)
        worst = "; ".join(f"{s:.2f} {a} x {b}" for s, a, b in pairs[:3])
        fails.append(
            f"{len(pairs)} near-duplicate page pairs at "
            f"{SHINGLE_SIMILARITY:.0%} similarity, above the "
            f"{cap} this site is held to. Worst: {worst}")


def check_not_machine_made(pages, fails):
    """Distinct openings, and no two pages in a generated family that say the
    same thing.

    The heading check alone missed this entirely. Fifty state pages carry no
    `<h2>` at all, so a check that only compared headings examined none of
    them — and fifty near-identical pages is precisely what a thin-content
    penalty is. Pages sharing a path prefix are now compared on their actual
    body text.
    """
    hand_written = [(p, m) for p, m in pages if "/" not in p.replace("/index.html", "")]
    openings, headings = [], []
    for _, markup in hand_written:
        h1 = re.search(r"<h1>(.*?)</h1>", markup, re.S)
        if h1:
            openings.append(visible(h1.group(1)))
        headings += [visible(h) for h in re.findall(r"<h2>(.*?)</h2>", markup, re.S)]
    for label, values in (("<h1>", openings), ("<h2>", headings)):
        seen: dict[str, int] = {}
        for value in values:
            seen[value] = seen.get(value, 0) + 1
        for value, count in seen.items():
            if count > 1:
                fails.append(
                    f"the {label} {value!r} appears on {count} pages — name "
                    "the offender, not just the fault"
                )

    families: dict[str, list] = {}
    for path, markup in pages:
        parts = path.split("/")
        if len(parts) > 2:
            families.setdefault(parts[0], []).append((path, markup))

    for family, members in families.items():
        titles = [re.search(r"<h1>(.*?)</h1>", m, re.S) for _, m in members]
        seen = [visible(t.group(1)) for t in titles if t]
        if len(set(seen)) != len(seen):
            fails.append(f"{family}/: two pages share an <h1>")

        # No two pages in a family may be near-copies of each other.
        #
        # The first version of this asked for a *unique word*, which is a bad
        # proxy: Virginia's page failed only because "Virginia" is a substring
        # of "West Virginia", while eleven genuinely identical pages passed.
        # Similarity is the thing actually being asked about, so it is what is
        # measured.
        words = {path: body_words(markup) for path, markup in members}
        for path, mine in words.items():
            worst, twin = 0.0, ""
            for other_path, theirs in words.items():
                if other_path == path:
                    continue
                overlap = len(mine & theirs) / len(mine | theirs)
                if overlap > worst:
                    worst, twin = overlap, other_path
            if worst > MAX_FAMILY_SIMILARITY:
                fails.append(
                    f"{path}: {worst:.1%} the same as {twin} — merge them or "
                    "give each something the other does not say"
                )


def check_responsible_gambling(pages, fails):
    """The age notice, the help link, and the number.

    The helpline was added to the footer and nothing checked it, so a break
    case that deleted it passed — the notice could keep its wording and lose
    the one line a reader in trouble actually needs. On a site that sends
    people to sportsbooks, that is the check least worth being lax about.
    """
    for path, markup in pages:
        text = visible(markup)
        if "21+" not in text or "ncpgambling.org" not in markup:
            fails.append(f"{path}: missing the 21+ notice or the help link")
        if "1-800-GAMBLER" not in markup:
            fails.append(f"{path}: missing the problem-gambling helpline")


def self_test() -> int:
    """Plant a duplicate page and confirm the similarity check fires.

    `break_check.py` cannot express this one: making two pages near-identical
    is not a single find-and-replace, and a break that only adds an HTML
    comment leaves the visible text — and therefore the similarity — unchanged.
    It passed against a build with the check deleted, which is exactly the kind
    of false green this project keeps finding.

    So the check is exercised directly, on synthetic pages, the way Docket's
    visual probes prove themselves.
    """
    # Realistic length matters. A first version used seven-word pages, where a
    # single differing word drops similarity to 0.75 and nothing could ever
    # trip a 0.97 threshold — the self-test failed and was right to. Real pages
    # run to hundreds of words, so one differing word moves the ratio by well
    # under a percent, which is precisely why near-duplicates are hard to spot
    # by eye and worth a gate.
    shared = " ".join(f"word{i}" for i in range(400))
    body = "<main><h1>{}</h1><p>" + shared + "</p></main>"
    twins = [("family/a/index.html", body.format("Alpha")),
             ("family/b/index.html", body.format("Beta"))]
    distinct = [
        ("family/a/index.html", body.format("Alpha")),
        ("family/b/index.html", "<main><h1>Beta</h1><p>"
         + " ".join(f"other{i}" for i in range(400)) + "</p></main>"),
    ]

    fails: list[str] = []
    check_not_machine_made(twins, fails)
    if not fails:
        print("SELF-TEST FAILED: two identical pages were not flagged",
              file=sys.stderr)
        return 1

    clean: list[str] = []
    check_not_machine_made(distinct, clean)
    if clean:
        print(f"SELF-TEST FAILED: distinct pages were flagged: {clean}",
              file=sys.stderr)
        return 1

    # The shingle counter, proved the same way. A find-and-replace break case
    # cannot express "make these two pages alike", so the check is exercised
    # directly on synthetic pages instead — the same reason the word-set check
    # above is tested here rather than in break_check.py.
    many_twins = [(f"family/{i}/index.html", body.format(f"Name{i}"))
                  for i in range(12)]
    shingle_fails: list[str] = []
    check_shingle_duplication(many_twins, shingle_fails, limit=0)
    if not shingle_fails:
        print("SELF-TEST FAILED: 66 identical pairs did not trip the "
              "shingle counter", file=sys.stderr)
        return 1

    varied = [(f"family/{i}/index.html",
               "<main><h1>Name%d</h1><p>" % i
               + " ".join(f"w{i}x{k}" for k in range(400)) + "</p></main>")
              for i in range(12)]
    shingle_clean: list[str] = []
    check_shingle_duplication(varied, shingle_clean, limit=0)
    if shingle_clean:
        print(f"SELF-TEST FAILED: distinct pages tripped the shingle "
              f"counter: {shingle_clean}", file=sys.stderr)
        return 1

    print(f"self-test passed: duplicates flagged, distinct pages not "
          f"(word-set {MAX_FAMILY_SIMILARITY}, shingles "
          f"{SHINGLE_SIMILARITY} over {MAX_SHINGLE_PAIRS} pairs)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-repo", default="../arb betting aqpp")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    measured_path = SITE / "_build" / "measured.json"
    if not measured_path.exists():
        print("no measured.json — run render.py first", file=sys.stderr)
        return 1
    measured = json.loads(measured_path.read_text())

    everything = [
        (str(p.relative_to(SITE)), p.read_text())
        for p in sorted(SITE.rglob("*.html"))
        if "_build" not in p.parts
    ]
    redirects = [(p, m) for p, m in everything if is_redirect(m)]
    pages = [(p, m) for p, m in everything if not is_redirect(m)]
    if not pages:
        print("no pages — run render.py first", file=sys.stderr)
        return 1

    fails: list[str] = []
    check_render_is_fresh(measured, fails,
                          Path(args.app_repo).expanduser().resolve())
    check_redirects(redirects, fails)
    check_indexnow_key(fails)
    check_numbers_are_measured(pages, measured, fails)
    check_competitor_claims(pages, fails)
    check_every_competitor_row_is_sourced(pages, fails)
    check_head(pages, fails)
    check_internal_links(pages, fails)
    check_sitemap(pages, fails)
    check_not_machine_made(pages, fails)
    check_shingle_duplication(pages, fails)
    check_responsible_gambling(pages, fails)

    print(f"checked {len(pages)} pages against "
          f"{len(measured_numbers(measured))} measured figures"
          + (f", plus {len(redirects)} redirect(s)" if redirects else ""))
    if fails:
        print(f"\n{len(fails)} problem(s):")
        for problem in fails:
            print(f"  - {problem}")
        return 1
    print("SITE GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
