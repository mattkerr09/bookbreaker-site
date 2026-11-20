"""Build bookbreaker.bet as a sports STATISTICS site (phase 1, written 2026-11-20).

Why this replaced _build/render.py: BookBreaker stopped being a betting tool. Matthew restarted it on 2026-11-20 as a sports
statistics and research app (no wagers, no sportsbook prices, no tips, no prizes, no sportsbook links or deals, ever;
~/ops/research/new-business/handover/BOOKBREAKER-HANDOVER-2026-11-20.md). The old generator and its 120 pages were all
about the old product, and the site has to say the new one before Dodo's product form is read. Phase 1 is a short, true
pre-launch page. Phase 2 is the full SITE-BAR build, once real app screens exist.

Built by hand by the BookBreaker chat, not by Codex: an urgent removal of pages that no longer describe what we sell, with
Codex's 5-hour window at 82% and its BookBreaker slot busy with the plan red team (JOB-CARDS floor 11 allows this, said in
the commit).

Every figure on the page comes from computing it here, from a public file read on a stated date. Nothing is typed in.
"""
from __future__ import annotations

import csv
import html
import json
import math
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
CHECKED = "20 November 2026"
CHECKED_ISO = "2026-11-20"
LAUNCH = "18 December 2026"
EMAIL = "matthew@kerrandcompanyholdings.com"
NFL_FILE = Path("/Users/matthewkerr/bb-lab/research/nfl/data/games.csv")
NFL_SOURCE = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
NFL_READ = "22 October 2026"          # the local file's own date (stat), the day it was downloaded


def e(s: str) -> str:
    return html.escape(str(s), quote=True)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def example() -> dict:
    """A real trend card: Detroit's 2025 regular season, points scored, from nflverse's public schedules file."""
    team, line = "DET", 24
    rows = [r for r in csv.DictReader(open(NFL_FILE)) if r["season"] == "2025" and r["game_type"] == "REG"
            and r["result"] not in ("", "NA")]
    scores = []
    for r in sorted(rows, key=lambda r: r["gameday"]):
        if r["home_team"] == team:
            scores.append(int(r["home_score"]))
        elif r["away_team"] == team:
            scores.append(int(r["away_score"]))
    n = len(scores)
    k = sum(s >= line for s in scores)
    last = scores[-10:]
    lo, hi = wilson(k, n)
    first, after = scores[:8], scores[8:]
    return {"team": "Detroit", "line": line, "n": n, "k": k, "pct": round(100 * k / n),
            "last_k": sum(s >= line for s in last), "last_n": len(last),
            "lo": round(100 * lo), "hi": round(100 * hi),
            "first_k": sum(s >= line for s in first), "first_n": len(first),
            "first_pct": round(100 * sum(s >= line for s in first) / len(first)),
            "after_k": sum(s >= line for s in after), "after_n": len(after),
            "after_pct": round(100 * sum(s >= line for s in after) / len(after)),
            "bars": [s >= line for s in scores]}


MARK = ('<svg class="mark" viewBox="0 0 64 64" aria-hidden="true"><defs><linearGradient id="bbTile" x1="0" y1="0" x2="1"'
        ' y2="1"><stop offset="0" stop-color="#8b89ff"/><stop offset="1" stop-color="#4341e6"/></linearGradient></defs>'
        '<rect width="64" height="64" rx="14" fill="url(#bbTile)"/><path d="M22 9h14a11 11 0 010 22H22z" fill="#fff"/>'
        '<path d="M17 34h17a11 11 0 010 22H17z" fill="#fff"/></svg>')

EXTRA_CSS = """
.trend{max-width:30rem;margin:2.2rem auto 0;text-align:left;background:var(--card);border:1px solid var(--rule);
  border-radius:var(--r);padding:1.25rem 1.35rem;box-shadow:0 20px 60px -30px var(--glow)}
.trend-top{display:flex;justify-content:space-between;align-items:baseline;gap:1rem}
.trend-q{font-weight:600;font-size:1.02rem;color:var(--ink)}
.trend-n{font-family:var(--mono);font-size:var(--t-2);color:var(--ink-3)}
.trend-big{font-size:2.6rem;font-weight:650;letter-spacing:-.03em;margin:.35rem 0 .1rem;color:var(--ink)}
.trend-big small{font-size:1rem;font-weight:500;color:var(--ink-2);margin-left:.4rem;letter-spacing:0}
.trend-range{font-size:var(--t-3);color:var(--ink-2)}
.trend-bars{display:grid;grid-template-columns:repeat(17,1fr);gap:4px;margin:1rem 0 .4rem}
.trend-bars i{display:block;height:28px;border-radius:4px;background:rgba(255,255,255,.08)}
.trend-bars i.y{background:linear-gradient(180deg,#8b89ff,#4f4dff)}
.trend-held{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:.9rem}
.trend-held div{background:var(--card-2);border-radius:var(--r-sm);padding:.7rem .8rem}
.trend-held small{display:block;font-size:var(--t-1);color:var(--ink-3);text-transform:uppercase;letter-spacing:.08em}
.trend-held b{font-size:1.15rem;color:var(--ink)}
.trend-src{font-size:var(--t-1);color:var(--ink-3);margin-top:.8rem}
.soon{display:inline-block;margin-bottom:1rem;padding:.35rem .8rem;border-radius:999px;font-size:.82rem;font-weight:600;
  color:var(--accent-hi);background:rgba(91,91,255,.12);border:1px solid rgba(139,137,255,.3)}
.price-plain{max-width:34rem;margin:1.4rem auto 0;font-size:1rem;color:var(--ink-2)}
.prose-page{max-width:var(--measure-page);margin:0 auto;padding:3rem 0}
.prose-page h1{font-size:clamp(2rem,4.6vw,3rem);letter-spacing:-.035em}
.prose-page h2{margin-top:2rem;font-size:1.3rem}
"""

REVEAL = """<script>
/* Scroll reveal, the same behaviour as the Outlier and Crisp sites: two-way, and nothing is hidden without JS. */
(function () {
  var root = document.documentElement; root.classList.add('js');
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var els = document.querySelectorAll('.reveal');
  if (reduce || !('IntersectionObserver' in window)) { for (var i = 0; i < els.length; i++) els[i].classList.add('in'); return; }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (x) { x.target.classList.toggle('in', x.isIntersecting); });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
  for (var j = 0; j < els.length; j++) io.observe(els[j]);
})();
</script>"""


def page(path: str, title: str, description: str, body: str, body_class: str = "", jsonld: list | None = None,
         index: bool = True) -> str:
    url = "https://bookbreaker.bet" + path
    ld = "".join(f'<script type="application/ld+json">{json.dumps(x)}</script>\n' for x in (jsonld or []))
    robots = "" if index else '<meta name="robots" content="noindex">\n'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="msvalidate.01" content="34D102FD9C044A2BDA597B176842725B" />
{robots}<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{e(url)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="BookBreaker">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:url" content="{e(url)}">
<meta name="twitter:card" content="summary">
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preload" href="/fonts/geist.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/style.css">
<style>{EXTRA_CSS}</style>
<script defer data-domain="bookbreaker.bet" src="https://plausible.io/js/script.js"></script>
{ld}</head>
<body class="{e(body_class)}">
<header><nav><a class="brand" href="/">{MARK}BookBreaker</a><span class="links"><a href="/#what">What it shows</a><a href="/#price">Price</a><a href="/#questions">Questions</a></span></nav></header>
<main>
{body}
</main>
<footer>
<div class="foot-grid">
<div>
<p class="foot-brand">BookBreaker</p>
<p>Player and team stats for the NBA, NFL, MLB and NHL, for Mac and Windows. Coming {LAUNCH}.</p>
<p>Built by Matthew Kerr in Grand Rapids, MI &middot; <a href="mailto:{EMAIL}">Email</a></p>
</div>
<div>
<p class="foot-head">Site</p>
<p><a href="/">Home</a></p>
<p><a href="/privacy/">Privacy</a></p>
</div>
<div>
<p class="foot-head">Company</p>
<p><a href="https://kerrandcompanyholdings.com/">Made by Kerr &amp; Company</a></p>
</div>
</div>
<p class="foot-fine">Not affiliated with the NBA, NFL, MLB or NHL, or with any team. Names and statistics only. Checked
<time datetime="{CHECKED_ISO}">{CHECKED}</time>.</p>
</footer>
{REVEAL}
</body>
</html>
"""


FAQ = [
    ("Can I get BookBreaker now?",
     f"Not yet. It comes out on {LAUNCH}, for Mac and Windows. This page will have the download and the price on it that day."),
    ("Which sports does it cover?",
     "The NBA, NFL, MLB and NHL: player and team stats, game by game, with home and away, opponent and date filters."),
    ("What does “held up later” mean?",
     "When a trend is spotted, BookBreaker keeps checking it in the games that come after. For each kind of trend, it shows "
     "how often trends like that kept holding, checked game by game through the season and never with hindsight."),
    ("Why does every number say how many games it rests on?",
     "Because 7 of 10 and 70 of 100 are not the same thing. Over 10 games the true rate could be a long way from 70%, so "
     "BookBreaker shows the game count and the range the rate could really sit in, next to every number."),
    ("Do I need an account?",
     "No. There's no sign-in. The app downloads one shared stats file, keeps your history on your own computer, and works "
     "offline on the last update it has."),
    ("What happens after the first year?",
     "The $39 includes 12 months of new games. After that, new games are an optional $19 a year. Without it, the app keeps "
     "every stat and tool it already has; only new games stop arriving."),
    ("Who makes it?",
     "Matthew Kerr, a solo software maker in Grand Rapids, Michigan, through Kerr & Company. You can email him at "
     f"{EMAIL}."),
]


def home(x: dict) -> str:
    bars = "".join(f'<i class="{"y" if b else ""}" title="{"reached" if b else "not reached"}"></i>' for b in x["bars"])
    faq = "\n".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in FAQ)
    return f"""<section class="hero">
<span class="soon">Coming {LAUNCH} &middot; Mac and Windows</span>
<h1>How often did it really happen?</h1>
<p class="lede">Type a number, like 25 points. BookBreaker shows how often the player or team reached it, out of how many
games, and whether trends like that kept holding in the games after.</p>
<p class="price-plain">$39 once, with 12 months of new games included. After that, new games are an optional $19 a year.</p>
<div class="trend reveal" aria-label="An example trend card, from Detroit's 2025 season">
<div class="trend-top"><span class="trend-q">{x['team']}, {x['line']} or more points</span><span class="trend-n">{x['n']} games</span></div>
<div class="trend-big">{x['k']} of {x['n']}<small>{x['pct']}%</small></div>
<div class="trend-range">With {x['n']} games, the real rate could be anywhere from {x['lo']}% to {x['hi']}%. Last 10 games: {x['last_k']} of {x['last_n']}.</div>
<div class="trend-bars" aria-hidden="true">{bars}</div>
<div class="trend-held">
<div><small>First {x['first_n']} games</small><b>{x['first_k']} of {x['first_n']} &middot; {x['first_pct']}%</b></div>
<div><small>The {x['after_n']} games after</small><b>{x['after_k']} of {x['after_n']} &middot; {x['after_pct']}%</b></div>
</div>
<p class="trend-src">A real example: Detroit's 2025 regular season, worked out from nflverse's public schedules file
(<a href="{e(NFL_SOURCE)}" rel="nofollow">source</a>, read {NFL_READ}). The app's own screens come with the launch.</p>
</div>
</section>

<section class="sec" id="what">
<div class="sec-head"><span class="kicker">What every trend shows</span><h2>The number, how many games it rests on, and whether it lasted</h2>
<p>Most stat sites show a percentage and stop. BookBreaker shows what that percentage is worth.</p></div>
<div class="explain">
<div class="ex reveal"><h3>The game count</h3><p>Every rate says how many games it comes from. 7 of 10 and 70 of 100 look the
same as a percentage. They aren't the same.</p></div>
<div class="ex reveal"><h3>A range, not one number</h3><p>With only a few games, the true rate could be far from what they show.
Each trend shows the range it could really sit in, so a small sample looks small.</p></div>
<div class="ex reveal"><h3>Held up later</h3><p>For each kind of trend, BookBreaker checks how often it kept holding in the games
after it was spotted, game by game through the season, never with hindsight.</p></div>
</div>
</section>

<section class="sec" id="yours">
<div class="sec-head"><span class="kicker">On your computer</span><h2>No account, and your history never disappears</h2></div>
<div class="explain">
<div class="ex reveal"><h3>No sign-in</h3><p>The app downloads one shared stats file, the same file for everyone. There's no
profile to fill in and nothing to log in to.</p></div>
<div class="ex reveal"><h3>Works offline</h3><p>Everything runs on your Mac or PC, on the last update it has. Each update shows its
date, so you always know how fresh the stats are.</p></div>
<div class="ex reveal"><h3>Kept for good</h3><p>Past seasons and past games stay on your computer. A stat you looked at last month
is still there next month.</p></div>
</div>
</section>

<section class="sec" id="price">
<div class="sec-head"><span class="kicker">Price</span><h2>$39 once, with a year of new games</h2>
<p>The app is $39 once, for Mac and Windows, with 12 months of new games included. After that, new games are an optional $19 a
year. Skip it and the app keeps every stat and tool it already has; only new games stop arriving. It comes out on {LAUNCH}.</p></div>
</section>

<section class="sec" id="questions">
<div class="sec-head"><span class="kicker">Questions</span><h2>Before it comes out</h2></div>
<div class="faq">
{faq}
</div>
</section>
"""


def privacy() -> str:
    return f"""<article class="prose-page">
<h1>Privacy</h1>
<p class="lede">This site counts visits without cookies, and the app, when it comes out, won't need an account.</p>
<h2>This website</h2>
<p>bookbreaker.bet uses Plausible Analytics to count page visits. Plausible sets no cookies and stores no personal data: it
counts pages, where visitors came from and which country, and nothing that identifies you. The site has no forms and asks
for nothing.</p>
<h2>The app</h2>
<p>BookBreaker comes out on {LAUNCH}. It has no account and no sign-in. Its full privacy details, including exactly what it
sends and when, will be published here before it can be downloaded.</p>
<h2>Contact</h2>
<p>Questions go to Matthew Kerr at <a href="mailto:{EMAIL}">{EMAIL}</a>.</p>
<p class="trend-src">Checked {CHECKED}.</p>
</article>"""


def not_found() -> str:
    return """<article class="prose-page">
<h1>That page has gone</h1>
<p class="lede">BookBreaker is now a sports statistics app, and the pages this site used to have are no longer here.</p>
<p><a class="btn primary" href="/">See what BookBreaker does</a></p>
</article>"""


def llms(x: dict) -> str:
    return f"""# BookBreaker

> A desktop app for player and team statistics in the NBA, NFL, MLB and NHL, for Mac and Windows. Every trend shows how many
> games it rests on, the range the rate could really sit in, and how often trends like it held up in later games.

- Status: not out yet. Release date {LAUNCH}.
- Price: $39 once, including 12 months of new games. After that, new games are an optional $19 a year. Without it, the app
  keeps all its stats and tools.
- Platforms: Mac and Windows.
- Account: none. The app downloads one shared stats file and keeps history on the user's computer. It works offline.
- What it shows: stats and trends only. Names and statistics; no league or team logos.
- Maker: Matthew Kerr, Grand Rapids, Michigan, through Kerr & Company (https://kerrandcompanyholdings.com/).
- Contact: {EMAIL}
- Checked: {CHECKED}

## Pages
- [Home](https://bookbreaker.bet/): what the app shows, the price and the questions people ask
- [Privacy](https://bookbreaker.bet/privacy/)
"""


def main() -> None:
    x = example()
    org = {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": "BookBreaker",
           "operatingSystem": "macOS, Windows", "applicationCategory": "SportsApplication",
           "description": "Player and team statistics for the NBA, NFL, MLB and NHL, with the game count behind every trend.",
           "author": {"@type": "Person", "name": "Matthew Kerr"},
           "publisher": {"@type": "Organization", "name": "Kerr & Company", "url": "https://kerrandcompanyholdings.com/"}}
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQ]}
    files = {
        "index.html": page("/", "BookBreaker: sports stats with the game count behind every trend",
                           "Player and team stats for the NBA, NFL, MLB and NHL. See how often a player or team reached a number, "
                           f"out of how many games, and whether it held up. Mac and Windows, {LAUNCH}.",
                           home(x), "home", [org, faq_ld]),
        "privacy/index.html": page("/privacy/", "Privacy: BookBreaker",
                                   "What bookbreaker.bet counts (no cookies, no personal data) and what the app will need (no account).",
                                   privacy()),
        "404.html": page("/404.html", "Page not found: BookBreaker",
                         "BookBreaker is now a sports statistics app.", not_found(), index=False),
        "llms.txt": llms(x),
        "robots.txt": "User-agent: *\nAllow: /\n\nSitemap: https://bookbreaker.bet/sitemap.xml\n",
        "sitemap.xml": ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                        + "".join(f"<url><loc>https://bookbreaker.bet{p}</loc><lastmod>{CHECKED_ISO}</lastmod></url>\n"
                                  for p in ("/", "/privacy/")) + "</urlset>\n"),
    }
    for rel, text in files.items():
        out = SITE / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    print(f"built {len(files)} files; example {x['team']} {x['k']}/{x['n']} at {x['line']}+")


if __name__ == "__main__":
    main()
