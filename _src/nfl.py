"""Team scoring pages. All arithmetic uses the shared statistics functions."""
from __future__ import annotations

import math
from statistics import median

from content import cell, cta, e, faq, sources, table
from pages import NFL_INDEX, SITE_CHECKED, TEAM_PAGES
from stats import BANDS, NFL_READ, band, held_up, rate

TEAM_BY_CODE = {team['abbreviation']: team for team in TEAM_PAGES}


def team_link(code: str) -> str:
    team = TEAM_BY_CODE[code]
    return f'<a href="/{team["slug"]}/">{e(team["name"])}</a>'


def rivals(games: list[dict]) -> list[str]:
    """Two most recently faced distinct division opponents in the displayed season."""
    codes = []
    for game in reversed(games):
        if game['division'] and game['opponent'] not in codes:
            codes.append(game['opponent'])
    return codes[:2]


def team_report(games: list[dict], previous: list[dict]) -> dict:
    scores = [g['points'] for g in games]
    threshold = math.ceil(median(scores))
    last = rate(scores[-10:], threshold)
    target = band(last['k'], last['n'])
    later = held_up({'team': previous + games}, threshold, 10)[target]
    splits = {label: rate([g['points'] for g in games if predicate(g)], threshold)
              for label, predicate in (
                  ('Home', lambda g: g['site'] == 'home'),
                  ('Away', lambda g: g['site'] == 'away'),
                  ('Division', lambda g: g['division']),
                  ('Other opponents', lambda g: not g['division']))}
    longest, running = 0, 0
    for score in scores:
        running = running + 1 if score >= threshold else 0
        longest = max(longest, running)
    return {'games': games, 'scores': scores, 'threshold': threshold, 'last': last,
            'season': rate(scores, threshold), 'at24': rate(scores, 24),
            'ppg': sum(scores) / len(scores), 'points': sum(scores), 'later': later,
            'splits': splits, 'longest': longest, 'ending': running}


def count_text(row: dict) -> str:
    return f"{row['k']} of {row['n']}"


def interval(row: dict) -> str:
    return f"{row['lo']}% to {row['hi']}%"


def answer(team: dict, r: dict) -> str:
    return (f"The {team['name']} scored {r['points']} points across {len(r['games'])} games in the 2025 regular season, "
            f"an average of {r['ppg']:.1f} per game. They reached 24 points in {count_text(r['at24'])} games. "
            f"Their median score was {r['threshold']} points. At that mark, the last 10 count was "
            f"{count_text(r['last'])}, beside {count_text(r['season'])} for the season.")


def observation(team: dict, r: dict) -> str:
    games, t = r['games'], r['threshold']
    home = [g['points'] for g in games if g['site'] == 'home']
    away = [g['points'] for g in games if g['site'] == 'away']
    gap = sum(home) / len(home) - sum(away) / len(away)
    first = rate(r['scores'][:10], t)
    name = team['name']
    if abs(gap) >= 4:
        side, larger, smaller = ('home', home, away) if gap > 0 else ('away', away, home)
        return (f"{name} averaged {sum(larger) / len(larger):.1f} points {('at home' if side == 'home' else 'away')}, "
                f"compared with {sum(smaller) / len(smaller):.1f} in the other setting. "
                f"The gap was {abs(gap):.1f} points per game across unequal sets of opponents.")
    if band(first['k'], first['n']) != band(r['last']['k'], r['last']['n']):
        return (f"For {name}, {t} points appeared in {count_text(first)} opening games and "
                f"{count_text(r['last'])} closing games. The rate band moved from "
                f"{BANDS[band(first['k'], first['n'])].lower()} to {BANDS[band(r['last']['k'], r['last']['n'])].lower()}. "
                "Those two windows share games.")
    if r['ending'] >= 2:
        return (f"{name} finished with {r['ending']} straight games at {t} points or more. "
                f"Their longest such run across the season lasted {r['longest']} games.")
    return (f"The longest run at {t} points or more for {name} lasted {r['longest']} games. "
            f"Their first 10 count was {count_text(first)}; the final 10 gave {count_text(r['last'])}. "
            f"Both fell in the {BANDS[band(first['k'], first['n'])].lower()} band.")


def chart(team: dict, r: dict) -> str:
    games = r['games']
    top = math.ceil(max(r['scores']) / 10) * 10
    x = lambda week: 40 + (week - 1) * 30
    y = lambda points: 178 - points / top * 140
    grid = ''.join(f'<line x1="40" x2="550" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text x="30" y="{y(v) + 4:.1f}" text-anchor="end">{v}</text>'
                   for v in (0, top // 2, top))
    ticks = ''.join(f'<text x="{x(w)}" y="200" text-anchor="middle">{w}</text>' for w in (1, 5, 10, 15, 18))
    points = ' '.join(f"{x(g['week'])},{y(g['points']):.1f}" for g in games)
    dots = ''.join(f'<circle cx="{x(g["week"])}" cy="{y(g["points"]):.1f}" r="3">'
                   f'<title>Week {g["week"]}: {g["points"]} points, {e(TEAM_BY_CODE[g["opponent"]]["name"])}</title>'
                   '</circle>' for g in games)
    return (f'<figure class="score-chart"><svg viewBox="0 0 580 224" role="img" '
            f'aria-labelledby="score-title score-desc"><title id="score-title">{e(team["name"])} points by week</title>'
            '<desc id="score-desc">Points scored in each played week. The game table gives every exact score.</desc>'
            f'<g class="chart-grid">{grid}{ticks}<text x="295" y="220" text-anchor="middle">Week</text></g>'
            f'<polyline points="{points}"/>{dots}</svg>'
            f'<figcaption>{e(team["name"])} · {len(games)} played weeks · Points scored</figcaption></figure>')


def held_line(r: dict) -> str:
    later = r['later']
    context = (f"{r['threshold']}+ points · last 10 band: {later['band'].lower()} · "
               f"Past spots with later games: {later['spots']} · Later games: {later['n']}. "
               "Search: 2024 and 2025 regular seasons. Horizon: 5 played games.")
    if later['too_few']:
        result = ('<strong>too few past spots to tell</strong>. '
                  'Fewer than 15 later games means the score and range are withheld.')
    else:
        result = (f'<strong>{count_text(later)}</strong> reached {r["threshold"]}+ points. '
                  f'Wilson 95% range: {interval(later)}.')
    return f'<section class="held-card"><h2>Held up later</h2><p>{result}</p><p>{e(context)}</p></section>'


def team_body(team: dict, r: dict, players_html: str = "") -> str:
    name, games, t = team['name'], r['games'], r['threshold']
    game_rows = [[cell(g['week'], True), cell(g['date']), f'<td>{e(TEAM_BY_CODE[g["opponent"]]["name"])}</td>',
                  cell(g['site'].capitalize()), cell(g['points']), cell(g['allowed']),
                  cell('Yes' if g['overtime'] else 'No')] for g in games]
    cards = []
    for threshold in (t - 7, t, t + 7):
        rows = []
        for label, scores in (('Last 5', r['scores'][-5:]), ('Last 10', r['scores'][-10:]), ('Season', r['scores'])):
            result = rate(scores, threshold)
            rows.append([cell(label, True), cell(count_text(result)), cell(result['n']), cell(interval(result))])
        cards.append(f'<section class="ex trend-card" data-threshold="{threshold}"><h3>{threshold}+ points</h3>' +
                     table(['Window', 'Reached', 'Games', 'Wilson 95% range'], rows,
                           f'{name}: {threshold} or more points') + '</section>')
    split_rows = [[cell(label, True), cell(count_text(result)), cell(interval(result))]
                  for label, result in r['splits'].items()]
    low, high = min(r['scores']), max(r['scores'])
    high_games = ', '.join(f"week {g['week']} against {TEAM_BY_CODE[g['opponent']]['name']}"
                           for g in games if g['points'] == high)
    low_games = ', '.join(f"week {g['week']} against {TEAM_BY_CODE[g['opponent']]['name']}"
                          for g in games if g['points'] == low)
    ot = [g for g in games if g['overtime']]
    ot_text = ('; '.join(f"Week {g['week']}: {g['points']} scored, {g['allowed']} allowed" for g in ot)
               if ot else 'No games in this log went to overtime')
    ending = (f'They finished with {r["ending"]} straight games at that mark.' if r['ending'] > 1 else
              f'Their final score was {r["scores"][-1]} points, '
              f'{"at or above" if r["ending"] else "below"} {t}.')
    faqs = [
        (f'What were the high and low scores for {name}?',
         f'<p>The high was {high} points in {e(high_games)}. The low was {low} in {e(low_games)}.</p>'),
        (f'How many {name} games went to overtime?', f'<p>{len(ot)} of {len(games)} games. {e(ot_text)}.</p>'),
        (f'How long was the run at {t}+ points?',
         f'<p>{name} reached {t}+ points in {r["longest"]} straight games, their longest run. {ending}</p>'),
    ]
    links = ''.join(f'<li>{team_link(code)}</li>' for code in rivals(games))
    return (f'<article><section class="hero search-hero"><h1>{e(team["title"])}</h1>'
            f'<p class="lede">{e(answer(team, r))}</p>'
            f'<p class="byline">Checked {SITE_CHECKED} · By Matthew Kerr, who makes BookBreaker</p>' + cta() +
            '</section><div class="search-body team-body">' + chart(team, r) +
            f'<p class="team-observation">{e(observation(team, r))}</p><h2>Every {name} game</h2>' +
            table(['Week', 'Date', 'Opponent', 'Home or away', 'Points scored', 'Points allowed', 'Overtime'],
                  game_rows, f'{name}: 2025 regular-season game log') +
            f'<h2>Three scoring thresholds</h2><p>Rule: the season median rounded up, with 7 points either side. '
            f'For {name}: {t - 7}, {t} and {t + 7}. '
            '<a href="/nfl-team-scoring/#method">Count and range rules</a>.</p>' +
            '<div class="threshold-grid">' + ''.join(cards) + '</div>' +
            f'<h2>{name} splits at {t}+ points</h2>' +
            table(['2025 split', f'Reached {t}+', 'Wilson 95% range'], split_rows, f'{name}: separate game counts') +
            held_line(r) + faq(faqs) + sources(['method-spots']) +
            '<section class="onward"><h2>Read next</h2><ul>'
            '<li><a href="/nfl-team-scoring/">All NFL team scoring pages</a></li>' + links +
            '<li><a href="/did-the-trend-hold-up/">Did the trend hold up in later games?</a></li>'
            '<li><a href="/is-a-10-game-trend-reliable/">Is a 10-game trend reliable?</a></li>'
            '</ul></section>' + players_html + '</div></article>')


SORT_SCRIPT = '''<script>
(function () {
  var table = document.getElementById('team-scores');
  var headers = table.querySelectorAll('thead th');
  table.querySelectorAll('thead button').forEach(function (button, column) {
    button.addEventListener('click', function () {
      var ascending = headers[column].getAttribute('aria-sort') !== 'ascending';
      var rows = Array.from(table.tBodies[0].rows);
      rows.sort(function (a, b) {
        var left = a.cells[column].dataset.sort, right = b.cells[column].dataset.sort;
        var compared = column === 0 ? left.localeCompare(right) : Number(left) - Number(right);
        return (ascending ? 1 : -1) * compared || a.cells[0].textContent.localeCompare(b.cells[0].textContent);
      });
      headers.forEach(function (header) { header.removeAttribute('aria-sort'); });
      headers[column].setAttribute('aria-sort', ascending ? 'ascending' : 'descending');
      rows.forEach(function (row) { table.tBodies[0].appendChild(row); });
    });
  });
})();
</script>'''


def index_body(reports: dict) -> str:
    rows = []
    for team in sorted(TEAM_PAGES, key=lambda t: t['name']):
        r = reports[team['abbreviation']]
        at24 = r['at24']
        values = [(team['name'], team_link(team['abbreviation'])), (len(r['games']), str(len(r['games']))),
                  (r['ppg'], f'{r["ppg"]:.1f}'), (at24['k'], count_text(at24)),
                  (at24['lo'], interval(at24))]
        cells = []
        for i, (value, label) in enumerate(values):
            tag, scope = ('th', ' scope="row"') if i == 0 else ('td', '')
            cells.append(f'<{tag}{scope} data-sort="{e(value)}">{label}</{tag}>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')
    headers = ['Team', 'Games', 'Points per game', 'Games with 24+', 'Wilson 95% range']
    head = ''.join(f'<th scope="col"{sort}><button type="button">{label}</button></th>'
                   for label, sort in zip(headers, [' aria-sort="ascending"', '', '', '', '']))
    return (f'<article><section class="hero search-hero"><h1>{e(NFL_INDEX["title"])}</h1>'
            '<p class="lede">Read every team’s 2025 regular-season scores, points per game and counts at three scoring '
            'thresholds. Each team page pairs its game log with Wilson ranges, home and away splits, and a check of '
            'what followed similar past rates. The table below compares all teams at the same 24-point mark.</p>'
            f'<p class="byline">Checked {SITE_CHECKED} · By Matthew Kerr, who makes BookBreaker</p>' + cta() +
            '</section><div class="search-body"><h2>All 32 teams</h2>'
            '<p>Sorted by team name. Use a column button to change the order. The range column sorts by its lower end. '
            'Points per game sorts by the unrounded average.</p>'
            '<div class="scroll" role="region" tabindex="0" aria-label="NFL team scoring comparison">'
            '<table id="team-scores"><caption>2025 regular-season team scoring</caption><thead><tr>' + head +
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
            '<h2 id="method">How these pages count games</h2>'
            '<p>I built these tables from completed regular-season games, ordered by date and game ID. '
            'Each played game appears once for each team. Postseason games are left out. '
            'The season label is the season year, so January dates can belong to the prior year’s season.</p>'
            '<p>At or above includes a score equal to the threshold. Each team’s three thresholds use its own season '
            'median rounded up, then 7 points below and above it. Last 5 and last 10 use the final played games. '
            'Splits use that median threshold and count each filtered group separately. Home and away are the file’s '
            'designated sides, including at neutral venues. Overtime points stay in the final score.</p>'
            '<p>The Wilson 95% range uses z = 1.96 and rounds endpoints to whole percentages. It estimates uncertainty '
            'about a common underlying rate under a model of separate trials. Related games and changing conditions '
            'limit that model. <a href="/is-a-10-game-trend-reliable/">Read the range calculation and its limits</a>.</p>'
            '<h2>The later-games check</h2>'
            '<p>Each team’s median threshold and final last-10 rate band set the question. The past search joins only '
            'that team’s 2024 and 2025 regular seasons. It starts after a full 10 played games. A spot uses only the '
            '10 games ending there. The next 5 played games supply the later count, with partial groups kept at the '
            'end. After selecting a spot, the next spot starts no earlier than the end of those 5 games. '
            'No later game counts twice within that team’s check.</p>'
            '<p>A final-game spot adds no later games. With fewer than 15 later games, the page says '
            '“too few past spots to tell” and withholds the score and range. Counts are pooled within one team, '
            'rather than across the league. This is a description of these stored seasons. The threshold itself '
            'comes from the full 2025 season, so this is not a test of a threshold chosen before that season. '
            '<a href="/did-the-trend-hold-up/">See the method applied in the worked study</a>.</p>'
            '<p>The two division links on each page go to its two most recently faced distinct division opponents '
            'in the displayed log.</p>'
            f'<p>The schedules file was read {NFL_READ}. Its 2026 season rows stop at that read date, so the 2026 '
            'season is not used anywhere in these calculations.</p>' + faq([
                ('Are these player statistics?', '<p>These are team scores. There are no player logs in this dataset batch.</p>'),
                ('Can I compare the median thresholds across teams?', '<p>The thresholds differ by team. Use the index’s 24-point column for a shared scoring mark.</p>'),
                ('Where are the source rows?', '<p>Each team page has every included 2025 game. The Sources list names the schedules file and the dated method notes.</p>'),
            ]) + sources(['method-spots']) + '</div></article>' + SORT_SCRIPT)
