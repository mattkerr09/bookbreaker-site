"""Build the BookBreaker home page and seven search answers without the network.

App claims are planned. Rival and league facts come from the dated registries.
Team scores and statistical ranges are computed from the local schedules file.
The shared page() shell supplies the existing header, footer and analytics tag.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from articles import ARTICLE_BODIES
from content import claim, cta, guide_links
from pages import SEARCH_PAGES
from stats import NFL_FILE, NFL_READ, NFL_SOURCE, example, wilson

SITE = Path(__file__).resolve().parents[1]
CHECKED = "21 November 2026"
CHECKED_ISO = "2026-11-21"
# No public date until the bake-off passes (Saban's card, 2026-11-20: the queue puts BookBreaker at wave 6, and Matthew
# said it "runs only its free data trial and bake-off until it shows a plan that can win"). A date we might miss is a claim.
LAUNCH = None
EMAIL = "matthew@kerrandcompanyholdings.com"


def e(s: str) -> str:
    return html.escape(str(s), quote=True)


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
.trend-bars{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:4px;margin:1rem 0 .4rem}
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
/* Two-way scroll reveal; content is visible without JavaScript. */
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
<meta property="og:type" content="{'article' if any(x.get('@type') == 'Article' for x in (jsonld or [])) else 'website'}">
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
<header><nav><a class="brand" href="/">{MARK}BookBreaker</a><span class="links"><a href="/#what">The plan</a><a href="/#price">Price</a><a href="/#questions">Questions</a></span></nav></header>
<main>
{body}
</main>
<footer>
<div class="foot-grid">
<div>
<p class="foot-brand">BookBreaker</p>
{claim("desktop")}
<p>Built by Matthew Kerr in Grand Rapids, MI &middot; <a href="mailto:{EMAIL}">Email</a></p>
</div>
<div>
<p class="foot-head">Site</p>
<p><a href="/">Home</a></p>
<p><a href="/privacy/">Privacy</a></p>
</div>
<div>
<p class="foot-head">Guides</p>
{guide_links()}
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



def home(x: dict) -> str:
    bars = "".join(f'<i class="{"y" if b else ""}" title="{"reached" if b else "not reached"}"></i>' for b in x["bars"])
    return f"""<section class="hero">
<h1>How often did it really happen?</h1>
<p class="lede">Start with the games behind a rate. Read how often the number was reached, how many games were counted,
and how much doubt remains. A separate check of later games can show what followed similar past rates.</p>
{cta()}
<div class="trend reveal" aria-label="An example from Detroit's 2025 season, not an app screen">
<div class="trend-top"><span class="trend-q">{x['team']}, {x['line']} or more points</span><span class="trend-n">{x['n']} games</span></div>
<div class="trend-big">{x['k']} of {x['n']}<small>{x['pct']}%</small></div>
<div class="trend-range">Wilson 95% range: {x['lo']}% to {x['hi']}%. Last 10 games: {x['last_k']} of {x['last_n']}.</div>
<div class="trend-bars" aria-hidden="true">{bars}</div>
<div class="trend-held">
<div><small>First {x['first_n']} games</small><b>{x['first_k']} of {x['first_n']} · {x['first_pct']}%</b></div>
<div><small>The {x['after_n']} games after</small><b>{x['after_k']} of {x['after_n']} · {x['after_pct']}%</b></div>
</div>
<p class="trend-src">A team example from Detroit's 2025 regular season. Computed from
<a href="{e(NFL_SOURCE)}">nflverse's schedules file</a>, read {NFL_READ}. The small split above compares the first games
with the rest of the season. It is not the held-up-later method.</p>
</div>
</section>
<section class="sec" id="what">
<div class="sec-head"><span class="kicker">The plan</span><h2>Counts, ranges and a later check</h2>
<p>BookBreaker is in development. These are planned features. The card above is built for this site from local team data.</p></div>
<div class="explain">
<div class="ex reveal"><h3>The games behind the rate</h3>{claim('counts')}</div>
<div class="ex reveal"><h3>The window you choose</h3>{claim('filters')}</div>
<div class="ex reveal"><h3>Held up later</h3>{claim('held')}</div>
</div>
{claim('leagues')}{claim('player-data')}
</section>
<section class="sec" id="yours">
<div class="sec-head"><span class="kicker">On your computer</span><h2>Your history, kept locally</h2></div>
<div class="explain">
<div class="ex reveal"><h3>No sign-in planned</h3>{claim('local')}</div>
<div class="ex reveal"><h3>The last update</h3>{claim('offline')}</div>
</div>
</section>
<section class="sec" id="price">
<div class="sec-head"><span class="kicker">Planned price</span><h2>Pay once for the app</h2>
{claim('price')}{claim('keep')}</div>
</section>
<section class="sec" id="questions">
<div class="sec-head"><span class="kicker">Questions</span><h2>Before it comes out</h2></div>
<div class="faq">
<details><summary>Can I get BookBreaker now?</summary><p>Not yet. BookBreaker is in development. There is no download and no launch date.</p></details>
<details><summary>Do I need an account?</summary>{claim('local')}</details>
<details><summary>What does held up later mean?</summary><p>It means counting later games after similar past rates, with rules that keep future scores out of the past spot choice.</p>{claim('held')}</details>
<details><summary>What happens after the first year?</summary>{claim('price')}{claim('keep')}</details>
<details><summary>Are these player results?</summary>{claim('player-data')}</details>
<details><summary>Who makes it?</summary><p>Matthew Kerr, a solo software maker in Grand Rapids, Michigan, through Kerr &amp; Company. Email <a href="mailto:{EMAIL}">{EMAIL}</a>.</p></details>
</div>
</section>
<section class="sec" id="search-pages"><div class="sec-head"><h2>Guides</h2>
<p>Start with the question you came to answer.</p></div>{guide_links(cards=True)}</section>
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
<p>BookBreaker is in development.</p>
{claim("privacy")}
<h2>Contact</h2>
<p>Questions go to Matthew Kerr at <a href="mailto:{EMAIL}">{EMAIL}</a>.</p>
<p class="trend-src">Checked {CHECKED}.</p>
</article>"""


def not_found() -> str:
    return """<article class="prose-page">
<h1>That page has gone</h1>
<p class="lede">This page has gone. BookBreaker is in development.</p>
<p><a class="btn primary" href="/">See the BookBreaker plan</a></p>
</article>"""


def llms(x: dict) -> str:
    return f"""# BookBreaker

> A planned desktop app for player and team statistics. In development for Mac and Windows.

- Planned price: $39 once, including 12 months of new games. Later new games will be an optional $19 a year.
- Planned features: game counts, Wilson ranges and a held-up-later check. History will stay on the computer, with no account.
- No download or launch date yet.
- Contact: {EMAIL}
- Checked: {CHECKED}

## Pages
- [Home](https://bookbreaker.bet/): the app plan and a computed team-points example
- [Privacy](https://bookbreaker.bet/privacy/)

## Guides and answers
""" + "".join(f"- [{p['title']}](https://bookbreaker.bet/{p['slug']}/): {p['note']}\n" for p in SEARCH_PAGES)


def article(config: dict, x: dict) -> str:
    return (f'<article><section class="hero search-hero"><h1>{e(config["title"])}</h1>'
            f'<p class="lede">{e(config["answer"])}</p>'
            f'<p class="byline">Checked {CHECKED} · By Matthew Kerr, who makes BookBreaker</p>' + cta()
            + '</section><div class="search-body">' + ARTICLE_BODIES[config['slug']](x) + '</div></article>')


def main() -> None:
    x = example()
    files = {
        "index.html": page("/", "BookBreaker: sports stats with the game count behind every trend",
                           "BookBreaker is in development for Mac and Windows. Planned player and team stats with game counts, ranges and a later-games check.",
                           home(x), "home"),
        "privacy/index.html": page("/privacy/", "Privacy: BookBreaker",
                                   "What bookbreaker.bet counts and the planned app privacy details.", privacy()),
        "404.html": page("/404.html", "Page not found: BookBreaker",
                         "BookBreaker is in development.", not_found(), index=False),
        "llms.txt": llms(x),
        "sitemap.xml": ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                        + "".join(f"<url><loc>https://bookbreaker.bet{p}</loc><lastmod>{CHECKED_ISO}</lastmod></url>\n"
                                  for p in ("/", "/privacy/", *(f"/{item['slug']}/" for item in SEARCH_PAGES)))
                        + "</urlset>\n"),
    }
    for config in SEARCH_PAGES:
        url = f"https://bookbreaker.bet/{config['slug']}/"
        schema = {"@context": "https://schema.org", "@type": "Article", "headline": config['title'],
                  "description": config['description'], "mainEntityOfPage": url,
                  "author": {"@type": "Person", "name": "Matthew Kerr"},
                  "datePublished": CHECKED_ISO, "dateModified": CHECKED_ISO}
        files[f"{config['slug']}/index.html"] = page(f"/{config['slug']}/", config['title'], config['description'],
                                                  article(config, x), "search", [schema])
    for rel, text in files.items():
        out = SITE / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    print(f"built {len(files)} files; example {x['team']} {x['k']}/{x['n']} at {x['line']}+")


if __name__ == "__main__":
    main()
