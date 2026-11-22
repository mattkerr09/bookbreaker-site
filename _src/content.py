"""Small HTML helpers. Facts and planned claims always come from their registries."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from pages import NFL_INDEX, PLAYER_INDEX, SEARCH_PAGES
from stats import NFL_READ, NFL_SOURCE

NFL_LICENSE = "https://creativecommons.org/licenses/by/4.0/"
DATA = Path(__file__).resolve().parent / "data"
FACTS = {item["id"]: item for item in json.loads((DATA / "facts.json").read_text())}
CLAIMS = {item["id"]: item for item in json.loads((DATA / "claims.json").read_text())}


def e(value: object) -> str:
    return html.escape(str(value), quote=True)


def fact(key: str, tag: str = "p", code: str | None = None) -> str:
    scope = ' scope="row"' if tag == 'th' else ''
    text = e(FACTS[key]["text"])
    if code:
        text = text.replace(e(code), f"<code>{e(code)}</code>")
    return f'<{tag}{scope} data-fact="{e(key)}">{text}</{tag}>'


def claim(key: str, tag: str = "p") -> str:
    scope = ' scope="row"' if tag == 'th' else ''
    return (f'<{tag}{scope} data-claim="{e(key)}"><span class="coming">Coming</span> '
            f'<span class="claim-text">{e(CLAIMS[key]["text"])}</span></{tag}>')


def cta(player_study: bool = False) -> str:
    description = ('<p>BookBreaker is a sports statistics app in development for Mac and Windows.</p>'
                   if player_study else claim("desktop"))
    return ('<aside class="ex development" aria-label="BookBreaker in development">'
            '<p class="soon">In development · Mac and Windows</p>' + description +
            '<p>No download yet. Check this site for progress.</p>'
            '<a class="btn primary" href="/#what">See the app plan</a></aside>')


def table(headers: list[str], rows: list[list[str]], caption: str) -> str:
    return ('<div class="scroll" role="region" tabindex="0" aria-label="' + e(caption) + '"><table><caption>'
            + e(caption) + '</caption><thead><tr>' + ''.join(f'<th scope="col">{e(h)}</th>' for h in headers)
            + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(row) + '</tr>' for row in rows)
            + '</tbody></table></div>')


def cell(text: object, heading: bool = False) -> str:
    return f'<th scope="row">{e(text)}</th>' if heading else f'<td>{e(text)}</td>'


def faq(items: list[tuple[str, str]]) -> str:
    return ('<section class="search-faq"><h2>Questions</h2><div class="faq">' +
            ''.join(f'<details><summary>{e(q)}</summary>{a}</details>' for q, a in items) + '</div></section>')


def nfl_credit() -> str:
    return ('<li>NFL data: <a href="https://github.com/nflverse/nflverse-data">nflverse</a>, licensed '
            f'<a href="{NFL_LICENSE}">CC BY 4.0</a>. Counts and ranges computed by BookBreaker.</li>')


# Rival betting-research apps and sites are named and dated, never linked.
NO_LINK_HOSTS = {"apps.apple.com", "www.dimers.com", "www.propsmadness.com"}
# Internal working files are cited by what they are, not by file name.
PUBLIC_SOURCE = {
    "PLAN-FIXES.md, section 1": '<a href="/nfl-player-stats/#method">BookBreaker method</a>',
    "PLAN-FIXES.md, section 2": "BookBreaker browser test of the league game-log pages",
}


def source_linked(url: str) -> bool:
    return url.startswith("https://") and urlsplit(url).hostname not in NO_LINK_HOSTS


def source_shown(url: str) -> str:
    """The plain words a reader sees for a source."""
    if url in PUBLIC_SOURCE:
        return re.sub(r"<[^>]+>", "", PUBLIC_SOURCE[url])
    return url.removeprefix("https://") if urlsplit(url).hostname in NO_LINK_HOSTS else url


def sources(keys: list[str], extra: list[str] = ()) -> str:
    reads = sorted({(FACTS[key]["source"], FACTS[key]["readAt"]) for key in keys})
    entries = []
    for url, date in reads:
        label = (PUBLIC_SOURCE[url] if url in PUBLIC_SOURCE else
                 f'<a href="{e(url)}">{e(url)}</a>' if source_linked(url) else e(source_shown(url)))
        entries.append(f'<li>{label}. Read {e(date)}.</li>')
    entries.append(f'<li><a href="{e(NFL_SOURCE)}">{e(NFL_SOURCE)}</a>. Data file read {NFL_READ}.</li>')
    entries.extend(extra)
    return '<section class="sources"><h2>Sources</h2><ul>' + ''.join(entries) + nfl_credit() + '</ul></section>'


def onward(slugs: list[str]) -> str:
    return '<section class="onward"><h2>Read next</h2><ul>' + ''.join(
        f'<li><a href="/{p["slug"]}/">{e(p["title"])}</a></li>' for p in SEARCH_PAGES if p["slug"] in slugs
    ) + '</ul></section>'


def guide_links(cards: bool = False) -> str:
    item_class = ' class="card"' if cards else ''
    items = ''.join(f'<li{item_class}><a href="/{p["slug"]}/">'
                    f'{e(p.get("link_title", p["title"]))}</a></li>' for p in SEARCH_PAGES)
    items += f'<li{item_class}><a href="/{NFL_INDEX["slug"]}/">NFL team scoring</a></li>'
    items += f'<li{item_class}><a href="/{PLAYER_INDEX["slug"]}/">NFL player stats</a></li>'
    items += f'<li{item_class}><a href="/streak-checker/">Free NFL streak checker</a></li>'
    return f'<ul class="{"cards" if cards else "guide-links"}" aria-label="Guides">{items}</ul>'
