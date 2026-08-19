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
MAX_SHINGLE_PAIRS = 11

#: A ceiling on how alike the *worst* pair may be, not just how many pairs
#: there are. Both are ratchets and both may only fall.
#:
#: The count alone is blind in a way that took a break case to expose: a pair
#: already over the line can be driven to any similarity at all — 0.57, 0.68,
#: identical — without changing the count, so the gate stays green while the
#: pages converge. The break case that renames one state page after another
#: takes ky x mo from 0.565 to 0.677 and the count never moves.
MAX_PAIR_SIMILARITY = 0.57

# The whole similarity zone, not just the headline above it.
#
# Counting only pairs over 0.5 made a 60% "improvement" that moved almost
# nothing: 442 near-duplicates became 176, and 255 pairs appeared in a
# 0.35-0.5 band that had been EMPTY. Eleven pairs actually left the zone.
# Google has no 0.5 cliff — a pair at 0.47 is not meaningfully less
# collapsible than the same pair at 0.52 — so a gate that watches one side of
# an arbitrary line rewards pushing pairs across it.
MAX_ZONE_PAIRS = 259

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


def check_every_class_is_styled(pages, fails):
    """Markup whose class the stylesheet never mentions draws nothing.

    This has now shipped three times: a data plate whose six classes did not
    exist, and two whole homepage sections that rendered as unstyled text.
    Every time the gate stayed green, because the gate reads what a page says
    and never asks whether anything makes it look like anything.

    Geometry lives in `style=""` attributes in places, which this cannot see,
    so the rule is narrow on purpose: a class used in the markup must appear
    somewhere in the stylesheet. That catches the typo and the forgotten
    block without pretending to audit the cascade.
    """
    css = (SITE / "style.css").read_text()
    styled = set(re.findall(r"\.(-?[_a-zA-Z][\w-]*)", css))
    seen: dict[str, str] = {}
    for path, markup in pages:
        for attr in re.findall(r'class="([^"]+)"', markup):
            for name in attr.split():
                if name not in styled:
                    seen.setdefault(name, path)
    for name, where in sorted(seen.items()):
        fails.append(
            f"class .{name} is used in {where} but appears nowhere in "
            f"style.css — that markup renders unstyled"
        )


def check_announced_version_is_downloadable(pages, fails, measured):
    """The version the site names must be the version it can hand over.

    Bumping the engine to 0.1.4 made every page read "Bookbreaker 0.1.4 is
    out" while the download button still served Bookbreaker-0.1.3.dmg, because
    0.1.4 had been built and not yet notarised. Every existing gate passed:
    the links resolved, the files were there, the checksums matched. The only
    false thing was the sentence beside them.
    """
    published = set()
    for path in (SITE / "releases").glob("*"):
        got = re.search(r"(\d+\.\d+\.\d+)", path.name)
        if got:
            published.add(got.group(1))
    if not published:
        return
    for path, markup in pages:
        for named in set(re.findall(r"Bookbreaker (\d+\.\d+\.\d+)",
                                    visible(markup))):
            if named not in published:
                fails.append(
                    f"{path}: announces Bookbreaker {named}, but releases/ "
                    f"holds only {', '.join(sorted(published))} — the page "
                    f"names a version it cannot give anyone"
                )


    # And the SIZE. The button said "172 KB" beside a 8,210,307-byte DMG for
    # several releases — the wheel's size rendered onto the macOS button. A
    # real number attached to the wrong artefact, which is the shape of fault
    # this whole gate family exists for, and the version check sailed past it
    # because the version was right.
    app = measured.get("release", {}).get("app", {})
    dmg = SITE / "releases" / app.get("name", "")
    if app and dmg.exists():
        actual_mb = round(dmg.stat().st_size / 1_000_000, 1)
        actual_kb = round(dmg.stat().st_size / 1000)
        if abs(actual_mb - float(app.get("mb", 0))) > 0.15:
            fails.append(
                f"measured.json says the download is {app.get('mb')} MB and "
                f"{dmg.name} is {actual_mb} MB")
        for page, markup in pages:
            for claim in re.findall(r"(\d+(?:\.\d+)?)\s*(MB|KB)\b", markup):
                size, unit = float(claim[0]), claim[1]
                as_mb = size if unit == "MB" else size / 1000
                # Only sizes sitting next to the download itself.
                if "Download free" not in markup:
                    continue
                if unit == "KB" and abs(as_mb - actual_mb) > 0.15 and size in (
                        app.get("kb"), measured["release"]["wheel"]["kb"]):
                    fails.append(
                        f"{page} advertises {size:.0f} {unit} for a download "
                        f"that is {actual_mb} MB")

def check_the_tab_and_the_page_agree(pages, fails):
    """theme-color has to be a colour the stylesheet actually uses.

    It shipped as #0B6CFF through two complete repalettes — blue, then purple,
    then amber — because it is a hex in a meta tag rather than a token, so
    nothing that repointed the palette could reach it. The browser tab
    advertised one brand while the page rendered another.
    """
    css = (SITE / "style.css").read_text().lower()
    # Not "appears anywhere": #0b6cff is STILL in the stylesheet as a dead
    # --accent override from the blue era, three passes back, so a substring
    # test passes on exactly the bug this exists to catch. The self-test
    # caught that, which is the whole reason for writing one.
    #
    # What matters is the value that wins the cascade, so take the last
    # declaration of each accent token — later rules override earlier ones —
    # and require the tab to be one of them.
    live = set()
    for token in ("--accent", "--accent-hi", "--accent-lo"):
        found = re.findall(rf"{token}\s*:\s*(#[0-9a-f]{{3,8}})", css)
        if found:
            live.add(found[-1])
    if not live:
        fails.append("style.css declares no accent token, so nothing can be "
                     "checked against the browser tab")
        return
    for path, markup in pages:
        for hexcode in re.findall(
                r'<meta name="theme-color" content="(#[0-9a-fA-F]{3,8})"',
                markup):
            if hexcode.lower() not in live:
                fails.append(
                    f"{path}: theme-color {hexcode} is not the accent the "
                    f"page ends up using ({', '.join(sorted(live))}) — the "
                    f"browser tab advertises a different brand from the page"
                )


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
    ceiling = MAX_PAIR_SIMILARITY if limit is None else 1.0
    too_alike = [p for p in all_pairs if p[0] > ceiling]
    if too_alike:
        too_alike.sort(reverse=True)
        worst = "; ".join(f"{s:.3f} {a} x {b}" for s, a, b in too_alike[:3])
        fails.append(
            f"{len(too_alike)} page pair(s) above {ceiling:.0%} similarity, "
            f"which the count-based cap cannot see because they were already "
            f"counted. Worst: {worst}")

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
    # The two gates added after a version bump advertised a file that did not
    # exist and a repalette left the browser tab on the old brand. Both are
    # exercised here because both read files off disk.
    real = sorted(
        m.group(1)
        for m in (re.search(r"(\d+\.\d+\.\d+)", f.name)
                  for f in (SITE / "releases").glob("*"))
        if m
    )
    if real:
        ahead = "9.9.9"
        bad_ver = [("x/index.html", f"<main>Bookbreaker {ahead} is out</main>")]
        ver_fails: list[str] = []
        check_announced_version_is_downloadable(bad_ver, ver_fails)
        if not ver_fails:
            print("SELF-TEST FAILED: a page announcing an unpublished version "
                  "was not flagged", file=sys.stderr)
            return 1
        ok_ver = [("x/index.html", f"<main>Bookbreaker {real[0]} is out</main>")]
        ver_clean: list[str] = []
        check_announced_version_is_downloadable(ok_ver, ver_clean)
        if ver_clean:
            print(f"SELF-TEST FAILED: a published version was flagged: "
                  f"{ver_clean}", file=sys.stderr)
            return 1

    stale = [("x/index.html",
              '<meta name="theme-color" content="#0B6CFF">')]
    tab_fails: list[str] = []
    check_the_tab_and_the_page_agree(stale, tab_fails)
    if not tab_fails:
        print("SELF-TEST FAILED: a theme-color absent from the stylesheet was "
              "not flagged", file=sys.stderr)
        return 1
    # Read the brand colour out of the stylesheet rather than hardcoding it.
    # The first version of this case named the amber hex directly and broke
    # the moment the palette moved — a value hardcoded outside the token set,
    # which is the exact defect the gate above exists to catch, sitting in the
    # test written to prove it works.
    brand = re.findall(r"--accent\s*:\s*(#[0-9a-f]{3,8})",
                       (SITE / "style.css").read_text().lower())
    if not brand:
        print("SELF-TEST FAILED: no --accent in style.css to test against",
              file=sys.stderr)
        return 1
    live = [("x/index.html",
             f'<meta name="theme-color" content="{brand[-1]}">')]
    tab_clean: list[str] = []
    check_the_tab_and_the_page_agree(live, tab_clean)
    if tab_clean:
        print(f"SELF-TEST FAILED: the real brand colour was flagged: "
              f"{tab_clean}", file=sys.stderr)
        return 1

    # The unstyled-class gate, proved both ways. This one has to be exercised
    # here rather than by a find-and-replace break, because breaking it means
    # removing a rule from a stylesheet the checker reads off disk.
    styled_page = [("x/index.html", '<main class="speed"><p class="hp">y</p></main>')]
    unstyled: list[str] = []
    _real_css = (SITE / "style.css")
    seen_css = _real_css.read_text()
    if ".speed" not in seen_css or ".hp" not in seen_css:
        print("SELF-TEST FAILED: fixture classes are not in the real "
              "stylesheet, so this case proves nothing", file=sys.stderr)
        return 1
    check_every_class_is_styled(styled_page, unstyled)
    if unstyled:
        print(f"SELF-TEST FAILED: styled classes were flagged: {unstyled}",
              file=sys.stderr)
        return 1

    ghost = [("x/index.html", '<main class="no-such-class-anywhere">y</main>')]
    ghost_fails: list[str] = []
    check_every_class_is_styled(ghost, ghost_fails)
    if not ghost_fails:
        print("SELF-TEST FAILED: a class with no rule behind it was not "
              "flagged", file=sys.stderr)
        return 1

    return 0


def check_one_palette(fails: list[str]) -> None:
    """One declaration per token per context, and no more.

    Three complete palettes accumulated in style.css — sky, then blue, then
    FanDuel — because each repalette was written as an append and the cascade
    quietly did the right thing. It was not harmless. The `theme-color` gate
    asked whether the brand hex appeared anywhere in the stylesheet and
    **passed on the exact bug it was written to catch**, because the
    superseded hex was still sitting there as a dead override.

    render.py folds the generations together now. This is what stops them
    coming back: with one declaration per token, "present in the stylesheet"
    and "actually renders" are the same question again, and a gate that greps
    for a colour cannot be fooled by a corpse.
    """
    css = (SITE / "style.css").read_text()
    contexts = (':root', ':root:not([data-theme="light"])', ':root[data-theme="dark"]')
    for context in contexts:
        seen: dict[str, int] = {}
        for m in re.finditer(re.escape(context) + r"\s*\{", css):
            if context == ":root" and css[m.start() - 1:m.start()] not in ("", "\n", "}", " ", "{"):
                continue
            end = css.find("}", m.end())
            for decl in re.finditer(r"(--[a-z0-9-]+)\s*:", css[m.end():end]):
                seen[decl.group(1)] = seen.get(decl.group(1), 0) + 1
        repeated = {t: n for t, n in seen.items() if n > 1}
        if repeated:
            fails.append(
                f"style.css declares {len(repeated)} token(s) more than once "
                f"in {context} — a superseded palette is still present, which "
                f"is what made the theme-color gate pass on its own bug: "
                f"{sorted(repeated)[:5]}")


def check_every_pass_reaches_the_stylesheet(fails: list[str]) -> None:
    """Every `/* PASS n */` written in render.py must appear in style.css.

    Twice now a block of CSS has been spliced into render.py somewhere that
    is not the stylesheet literal. The first time it landed at module level
    and Python refused to import it, which is the good failure. The second
    time it landed inside a function's **docstring**: the module imported,
    the build succeeded, every gate stayed green, and the CSS did nothing at
    all. The comment in that very patch said not to do it — the anchor was
    computed by scanning backwards for a triple-quote, and new docstrings had
    since been added between the stylesheet and the anchor.

    A comment cannot prevent that. This can: if a pass is not in the rendered
    output, it was not in the stylesheet.
    """
    render = (SITE / "_build" / "render.py").read_text()
    css = (SITE / "style.css").read_text()
    passes = re.findall(r"/\* (PASS [0-9]+)", render)
    missing = [name for name in dict.fromkeys(passes) if name not in css]
    if missing:
        fails.append(
            f"{len(missing)} CSS pass(es) written in render.py never reached "
            f"style.css — spliced outside the stylesheet literal, most likely "
            f"into a docstring, where it parses and does nothing: {missing}")


def check_media_exists(pages, fails: list[str]) -> None:
    """Every <video>, <source> and <img> the pages reference is on disk.

    A broken <img> is a small embarrassment. A <video> whose source 404s is a
    hero that renders as a black rectangle, and no other check here looks at
    binary files at all — check_internal_links follows anchors, not media.
    """
    seen: set[str] = set()
    for page, markup in pages:
        for src in re.findall(r'(?:src|poster)="(/[^"]+\.(?:mp4|webm|jpg|jpeg|png|svg|avif|gif))"', markup):
            if src in seen:
                continue
            seen.add(src)
            if not (SITE / src.lstrip("/")).exists():
                fails.append(f"{page} references {src}, which is not on disk")

    # And everything the stylesheet reaches for. A missing woff2 is invisible
    # — the text simply renders in the fallback, which is exactly the state
    # this site was in before it had a typeface at all.
    css = (SITE / "style.css").read_text()
    for url in set(re.findall(r'url\(["\']?(/[^)"\']+)["\']?\)', css)):
        if not (SITE / url.lstrip("/")).exists():
            fails.append(f"style.css references {url}, which is not on disk")

    # A font shipped without its licence is a licensing problem, not a
    # rendering one, and nothing else here would ever catch it.
    if list((SITE / "fonts").glob("*.woff2")) if (SITE / "fonts").exists() else []:
        if not any((SITE / "fonts").glob("*OFL*")) and not any((SITE / "fonts").glob("*LICEN*")):
            fails.append("fonts/ ships a woff2 with no licence file beside it")


def check_no_internal_docs_are_served(fails: list[str]) -> None:
    """Nothing internal is tracked in a repo that serves every tracked file.

    GitHub Pages with .nojekyll publishes the whole tree, so a markdown file
    committed here is a page on the marketing domain whether or not anything
    links to it. DEPLOY.md was live at bookbreaker.bet/DEPLOY.md returning
    200 — no credentials in it, but internal process notes on a public domain
    all the same, and DESIGN-BRIEF.md had already had to be purged from this
    repo's history for the same reason.

    Checked by name rather than by scanning for secrets, because "does this
    file contain a credential" is the wrong question. The right one is
    whether it was written for customers.
    """
    internal = ("DEPLOY", "AUDIT", "DO-NOT-REBREAK", "BRIEF", "ROADMAP",
                "NOTES", "TODO", "HANDOVER", "POSTMORTEM")
    for path in sorted(SITE.glob("*.md")) + sorted(SITE.glob("*.txt")):
        if path.name in ("README.md",):
            continue
        stem = path.stem.upper()
        if any(word in stem for word in internal):
            fails.append(
                f"{path.name} is tracked here, so it is served at "
                f"https://bookbreaker.bet/{path.name}. Internal documents "
                f"belong in the private app repo.")


#: Classes only ever added by JavaScript, so they never appear in the
#: rendered HTML and are not dead. Listed by name rather than detected,
#: because "does any script mention this string" matches far too much.
RUNTIME_CLASSES = {
    "own-big", "own-cap", "own-spread", "own-hint", "own-no",
    "reveal",
    # `js` goes on <html> the moment the script runs and `in` is toggled by
    # the IntersectionObserver. The d1-d3 stagger classes are NOT here: they
    # are written into the markup like any other class, and listing them
    # would have exempted them from ever being checked.
    "js", "in",
}



def check_runtime_classes_are_real(pages, fails: list[str]) -> None:
    """Every name exempted as "added by JavaScript" is still used by JavaScript.

    RUNTIME_CLASSES exists because a class a script applies never appears in
    the rendered markup, so the dead-CSS check would call it dead. That is a
    real exemption and it is also a hole: a name left in this set after its
    script is deleted silently re-permits the dead CSS it was covering.

    So the exemption has to keep being earned. Not "does any script mention
    this string" as the whole test — the set is still by name — but each name
    must appear in some script on the site, or it has gone stale.
    """
    scripts = "\n".join(
        m for _, markup in pages
        for m in re.findall(r"<script[^>]*>(.*?)</script>", markup, re.S))
    stale = sorted(
        name for name in RUNTIME_CLASSES
        if not re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", scripts))
    if stale:
        fails.append(
            f"{len(stale)} name(s) in RUNTIME_CLASSES are not used by any "
            f"script on the site — the exemption is stale and is now hiding "
            f"dead CSS rather than explaining it: {stale}")


def check_no_dead_css(pages, fails: list[str]) -> None:
    """Every class the stylesheet targets exists somewhere in the site.

    CSS that matches nothing renders exactly like CSS that was never
    written, which is why this keeps happening: a rule for `.hero h1 .lit`
    when no element has that class, a `.win-big b` left behind when the hero
    became a video, a whole `.win-*` family orphaned by one markup change.
    Four times now, and each one was found by hand or not at all.

    The mirror of check_every_class_is_styled: that one catches markup with
    no rules, this catches rules with no markup. Together they mean the
    stylesheet and the pages describe the same site.
    """
    css = (SITE / "style.css").read_text()
    # Strip comments first. The prose in this stylesheet mentions avo.bet and
    # fanduel.com, and a naive scan reads those as `.bet` and `.com` — the
    # same fault as a guard that once tripped on `--violet` written inside
    # its own explanatory comment.
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    targeted: set[str] = set()
    for block in re.finditer(r"(?m)^([^{}@][^{}]*?)\{", css):
        for selector in block.group(1).split(","):
            targeted.update(re.findall(r"\.([a-zA-Z][\w-]*)", selector))

    used: set[str] = set()
    for _, markup in pages:
        for attr in re.findall(r'class="([^"]+)"', markup):
            used.update(attr.split())

    # A selector matches only if EVERY class in it exists: `.app-bar .dot`
    # needs an `.app-bar` however many `.dot`s there are. Checking that any
    # one class is missing — rather than all of them — is the difference
    # between catching a dead family and catching none of it.
    dead = sorted(targeted - used - RUNTIME_CLASSES)
    if dead:
        fails.append(
            f"style.css styles {len(dead)} class(es) that appear on no page. "
            f"Dead CSS is invisible — it renders identically to CSS that was "
            f"never written: {dead[:12]}")


def check_hero_video_matches_the_app(fails: list[str], app_repo: Path) -> None:
    """The hero video shows the window that ships today, not one that used to.

    Taken from the portfolio site, which learned it the expensive way: a
    product screenshot that drifted 2.2% from the live site, and three more
    that declared the wrong height. A picture of a product is a claim about
    the product, and it rots silently — nothing renders differently when it
    goes stale, which is exactly why it needs a gate rather than a habit.

    Ours is a recording rather than a still, and the failure is worse: a
    visitor watches a tab that no longer exists being clicked. The manifest
    records the tabs and panel questions as they were when the take was made;
    this compares them to `ui/src/index.html` as it stands now.
    """
    manifest_path = SITE / "media" / "app-video.json"
    if not manifest_path.exists():
        fails.append("media/app-video.json is missing — nothing records which "
                     "version of the window the hero video shows")
        return
    manifest = json.loads(manifest_path.read_text())

    # render.py's extractor, imported rather than reimplemented. A second
    # parser of ui/src/index.html would drift from the first, which is
    # precisely the class of bug this gate exists to catch.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_render", SITE / "_build" / "render.py")
    render = importlib.util.module_from_spec(spec)
    sys.modules["_render"] = render
    spec.loader.exec_module(render)
    now = render.read_app_window(app_repo)
    for field in ("tabs", "heads"):
        was, is_now = manifest.get(field), now.get(field)
        if was != is_now:
            fails.append(
                f"the hero video was recorded when the window's {field} were "
                f"{was}, and they are now {is_now}. The video shows a product "
                f"that no longer exists; re-record it and update "
                f"media/app-video.json.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-repo", default="../arb betting aqpp")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--only", default=None,
                        help="run one check by name, so a break case can\nprove which gate caught it")
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

    # Named, so `--only` can address one of them and so the break harness can
    # assert that every check here has a case proving it can fail. A check
    # nobody has watched fail is indistinguishable from a check that cannot.
    registry = {
        "check_render_is_fresh":
            lambda: check_render_is_fresh(
                measured, fails, Path(args.app_repo).expanduser().resolve()),
        "check_redirects": lambda: check_redirects(redirects, fails),
        "check_indexnow_key": lambda: check_indexnow_key(fails),
        "check_numbers_are_measured":
            lambda: check_numbers_are_measured(pages, measured, fails),
        "check_competitor_claims": lambda: check_competitor_claims(pages, fails),
        "check_every_competitor_row_is_sourced":
            lambda: check_every_competitor_row_is_sourced(pages, fails),
        "check_head": lambda: check_head(pages, fails),
        "check_every_class_is_styled":
            lambda: check_every_class_is_styled(pages, fails),
        "check_announced_version_is_downloadable":
            lambda: check_announced_version_is_downloadable(
                pages, fails, measured),
        "check_the_tab_and_the_page_agree":
            lambda: check_the_tab_and_the_page_agree(pages, fails),
        "check_internal_links": lambda: check_internal_links(pages, fails),
        "check_sitemap": lambda: check_sitemap(pages, fails),
        "check_not_machine_made": lambda: check_not_machine_made(pages, fails),
        "check_shingle_duplication":
            lambda: check_shingle_duplication(pages, fails),
        "check_responsible_gambling":
            lambda: check_responsible_gambling(pages, fails),
        "check_media_exists": lambda: check_media_exists(pages, fails),
        "check_no_internal_docs_are_served":
            lambda: check_no_internal_docs_are_served(fails),
        "check_hero_video_matches_the_app":
            lambda: check_hero_video_matches_the_app(
                fails, Path(args.app_repo).expanduser().resolve()),
        "check_no_dead_css": lambda: check_no_dead_css(pages, fails),
        "check_runtime_classes_are_real":
            lambda: check_runtime_classes_are_real(pages, fails),
        "check_one_palette": lambda: check_one_palette(fails),
        "check_every_pass_reaches_the_stylesheet":
            lambda: check_every_pass_reaches_the_stylesheet(fails),
    }

    # Every check defined in this file must be wired into the registry, or
    # `--only` silently reports a green board for a check that never ran.
    defined = {name for name in globals()
               if name.startswith("check_") and callable(globals()[name])}
    missing = defined - set(registry)
    if missing:
        print(f"checks defined but never run: {sorted(missing)}", file=sys.stderr)
        return 2

    if args.only:
        if args.only not in registry:
            print(f"no such check: {args.only}", file=sys.stderr)
            return 2
        registry[args.only]()
    else:
        for run_check in registry.values():
            run_check()

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
