"""The shown-versus-later page, drawn directly from the player study."""
from __future__ import annotations

from content import cell, e, faq, nfl_credit, onward, table
from player_study import PLAYER_READ, PLAYER_SOURCES, study


def study_table(window: int, result: dict) -> str:
    rows = []
    for r in result['bands']:
        if not r['spots']:
            values = [cell(r['band'], True), cell(0), cell('Not reachable'), cell('No later games'), cell('No range')]
        else:
            lo, hi = r['range']
            values = [cell(r['band'], True), cell(r['spots']), cell(f"{r['shown']:.0%}"),
                      cell(f"{r['k']} of {r['n']} · {r['later']:.0%}"), cell(f'{lo:.0%} to {hi:.0%}')]
        rows.append(values)
    return table(['Past rate band', 'Spots', 'Average rate shown', 'Later count and rate', 'Wilson 95% range'],
                 rows, f'Last {window} games shown, next 5 games checked')


def study_chart(results: dict) -> str:
    parts = ['<figure class="study-chart"><svg viewBox="0 0 300 930" role="img" '
             'aria-labelledby="study-title study-desc"><title id="study-title">Shown rates beside later rates</title>'
             '<desc id="study-desc">Squares mark the average shown rate. Circles mark the later rate. '
             'Bars give the later Wilson 95% range. Both tables give the exact counts.</desc>']
    x = lambda rate: 18 + 264 * rate
    for panel, (window, result) in enumerate(results.items()):
        top = 28 + panel * 460
        parts.append(f'<text class="study-panel" x="18" y="{top}">Last {window} games</text>')
        for v in (0, .5, 1):
            parts.append(f'<text x="{x(v):.1f}" y="{top + 27}" text-anchor="'
                         f'{"start" if v == 0 else "end" if v == 1 else "middle"}">{v:.0%}</text>')
        for i, row in enumerate(result['bands']):
            y = top + 62 + i * 78
            parts.append(f'<g data-window="{window}" data-band="{e(row["band"])}">'
                         f'<text x="18" y="{y}">{e(row["band"])}</text>')
            if row['spots']:
                lo, hi = row['range']
                parts.append(f'<text x="18" y="{y + 21}">{row["shown"]:.0%} shown · {row["later"]:.0%} later</text>'
                             f'<line class="study-track" x1="18" x2="282" y1="{y + 40}" y2="{y + 40}"/>'
                             f'<line class="study-range" x1="{x(lo):.2f}" x2="{x(hi):.2f}" '
                             f'y1="{y + 40}" y2="{y + 40}"/>'
                             f'<rect x="{x(row["shown"]) - 4:.2f}" y="{y + 36}" width="8" height="8"/>'
                             f'<circle cx="{x(row["later"]):.2f}" cy="{y + 40}" r="5"/>')
            else:
                parts.append(f'<text x="18" y="{y + 24}">No spots with a last-5 rate</text>')
            parts.append('</g>')
    parts.append('</svg><figcaption>Square: average shown. Circle: later rate. Bar: Wilson 95% range. '
                 'Each panel uses a 0% to 100% scale.</figcaption></figure>')
    return ''.join(parts)


def player_body(x: dict) -> str:
    results = study()
    return f'''<h2>The gap between the display and the next games</h2>
<p>I checked player yards rather than team points. The question was simple: after a player reached his own number
in most recent games, how often did he reach that same number in the games after? The number stayed fixed throughout
the check. No 2025 result helped choose it.</p>
{study_chart(results)}
<h2>Last 5: 82% shown, 56% later in the highest band</h2>
{study_table(5, results[5])}
<p>A last-5 rate moves in steps of 20 percentage points. It cannot fall in 70 to 79%.
The highest band includes four of five and five of five. The average shown gives each spot equal weight.
The later rate divides all reaches by all later games, so a spot with five later games adds more than one with only one.</p>
<h2>Last 10: a second window on the same question</h2>
{study_table(10, results[10])}
<p>Ten games allow every band in the table. The outcome is still the next five games, rather than the next ten.
These are two checks on the same season. Their games can repeat across windows and across bands.</p>
<h2>How I chose the number and the spots</h2>
<p>The eligible group was {results[5]['players']} quarterbacks, running backs, wide receivers and tight ends.
Each had at least eight regular-season games in 2024 and a rounded-up 2024 median of at least 10 yards.
The main stat was passing yards for quarterbacks, rushing yards for running backs, and receiving yards for receivers
and tight ends. Each player and position pair had its own log.</p>
<p>For each log, I sorted the games by season and week. I took the middle 2024 yardage value, averaging the two middle
values when needed, then rounded up to a whole yard. That was the player's number for the whole study.
A game equal to the number counted as reaching it. A blank yards value in a recorded row counted as zero.</p>
<p>I then walked through 2025 in order. A spot was a game where the rate across the five or ten played games ending
there fell in a band. Early lookbacks could include the end of 2024. The outcome used only the next five recorded
games from 2025. At season end I kept fewer than five when that was all that remained. A spot with none was left out.</p>
<p>After a spot, the next spot in that player's same band was at least six games later. Its five later games could
not overlap the earlier spot's five later games. Each band ran separately. I pooled the later counts across players
and used Wilson 95% ranges with z = 1.96. Percentages and range ends are rounded to whole numbers.</p>
<h2>What the gap means</h2>
<p>The past count is right: it describes those past games. In the last-10 check, the shown rate ran above the later
rate in every band from 40% up. In the last-5 check, that held from 60% up. The exception was 40 to 59%:
40% shown became 42% later. The under-40% band ran below the later rate in both windows.</p>
<p>Part of this pattern is regression toward each player's usual level. Choosing unusually high recent counts can
select runs that include good fortune. The next games need not keep that same share. The reverse can happen after low
counts. This check does not measure how much each cause contributed.</p>
<p>That is why my plan for BookBreaker pairs the count with a range and a later-games check.
This is one season, one league and yards only. Players can share games and conditions. The pooled Wilson ranges use a
model of separate trials with a common rate; they do not account for every connection between these results.</p>
<h2>What it does not mean</h2>
<p>This makes no claim about any single player or game. It does not predict future results and gives no advice.
A pooled rate belongs to this group and these rules. It is not a personal forecast or a reason to expect the same outcome
in a different season.</p>
{faq([
    ('Did 82% turn into 56% for every player?', '<p>No. Those are group summaries. The 82% is the average shown across 199 spots. The 56% pools 482 reaches across 860 later games.</p>'),
    ('Did the 2025 games choose the number?', '<p>No. Only the 2024 regular-season yards chose each number. The 2025 rows supplied the spots and their later outcomes.</p>'),
    ('Why are there fewer than five later games per spot on average?', '<p>Spots near the end of 2025 can have one to four later games. Those shorter groups stay in the count, with their actual number of games.</p>'),
    ('Is this proof that a streak cannot continue?', '<p>No. It measures what followed these past spots. It does not settle the next result or identify a particular player.</p>'),
])}
<section class="sources"><h2>Sources</h2><ul>
<li><a href="{e(PLAYER_SOURCES[0])}">nflverse weekly player statistics, 2024 CSV</a>. Read {PLAYER_READ}.</li>
<li><a href="{e(PLAYER_SOURCES[1])}">nflverse weekly player statistics, 2025 CSV</a>. Read {PLAYER_READ}.</li>
{nfl_credit()}
</ul><p>The method above describes the calculation. Only regular-season rows and the identity, position, season,
week and three yards fields enter it. Player identities stay out of this page.</p></section>
{onward(['did-the-trend-hold-up', 'is-a-10-game-trend-reliable'])}
<p><a href="/nfl-team-scoring/">Read the separate NFL team scoring tables</a>.</p>'''
