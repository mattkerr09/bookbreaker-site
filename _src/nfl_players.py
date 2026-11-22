"""Player game logs, measured observations and HTML for the NFL player batch."""
from __future__ import annotations

import math
from collections import defaultdict

from content import cell, cta, e, faq, nfl_credit, table
from nfl import TEAM_BY_CODE, count_text, interval, team_link
from pages import PLAYER_INDEX, PLAYER_PAGES
from player_data import (PLAYER_2026_READ, PLAYER_2026_SOURCE, PLAYER_READ, PLAYER_SOURCES, read_2026_rows,
                         read_player_rows, thresholds)
from stats import (BANDS, NFL_READ, NFL_READ_2026, NFL_SOURCE, band, current_season_scores, held_up, rate,
                   season_scores)

POSITION_FIELDS = {
    'QB': (('completions', 'Completions'), ('attempts', 'Attempts'), ('passing_yards', 'Passing yards'),
           ('passing_tds', 'Passing TDs'), ('passing_interceptions', 'Interceptions'), ('rushing_yards', 'Rushing yards')),
    'RB': (('carries', 'Carries'), ('rushing_yards', 'Rushing yards'), ('rushing_tds', 'Rushing TDs'),
           ('receptions', 'Receptions'), ('receiving_yards', 'Receiving yards')),
    'WR': (('targets', 'Targets'), ('receptions', 'Receptions'), ('receiving_yards', 'Receiving yards'),
           ('receiving_tds', 'Receiving TDs')),
}
POSITION_FIELDS['TE'] = POSITION_FIELDS['WR']


def join_games(rows: list[dict], schedule: dict, p: dict) -> list[dict]:
    joined = []
    for row in rows:
        game = schedule.get((row['team'], row['game_id']))
        if game is None or game['opponent'] != row['opponent_team'] or game['week'] != int(row['week']):
            raise ValueError(f"unmatched player game: {row['game_id']}")
        fields = {key: int(float(row[key] or 0)) for key, label in POSITION_FIELDS[p['position']]}
        joined.append(dict(game, **fields, team=row['team'], yards=int(float(row[p['stat']] or 0))))
    joined.sort(key=lambda g: (g['date'], g['id']))
    if len({g['id'] for g in joined}) != len(joined):
        raise ValueError('duplicate player game')
    return joined


def player_reports(rows: list[dict] | None = None, players: list[dict] = PLAYER_PAGES,
                   rows_2026: list[dict] | None = None) -> dict:
    schedules = {season: {(code, g['id']): g for code, games in season_scores(season=season).items()
                          for g in games} for season in (2024, 2025)}
    schedule_2026 = {(code, g['id']): g for code, games in current_season_scores().items() for g in games}
    through = max(g['date'] for g in schedule_2026.values())
    logs, logs_2026 = defaultdict(list), defaultdict(list)
    for row in read_player_rows() if rows is None else rows:
        if row['season_type'] == 'REG' and row['season'] in ('2024', '2025'):
            logs[row['player_id']].append(row)
    for row in read_2026_rows() if rows_2026 is None else rows_2026:
        if row['season_type'] == 'REG' and row['season'] == '2026':
            logs_2026[row['player_id']].append(row)
    reports = {}
    for p in players:
        joined = []
        for season in (2024, 2025):
            joined += join_games([row for row in logs[p['player_id']] if row['season'] == str(season)],
                                 schedules[season], p)
        joined.sort(key=lambda g: (g['date'], g['id']))
        now = join_games(logs_2026[p['player_id']], schedule_2026, p)
        current = [g for g in joined if g['season'] == 2025]
        scores = [g['yards'] for g in current]
        lines = thresholds(p['median'])
        t = lines[1]
        last = rate(scores[-10:], t)
        later = held_up({'player': [dict(points=g['yards']) for g in joined]}, t, 10)[band(last['k'], last['n'])]
        split_groups = [('Home', [g for g in current if g['site'] == 'home']),
                        ('Away', [g for g in current if g['site'] == 'away']),
                        ('Division', [g for g in current if g['division']]),
                        ('Other opponents', [g for g in current if not g['division']])]
        splits = {label: rate([g['yards'] for g in games], t) if games else None for label, games in split_groups}
        longest = running = 0
        for value in scores:
            running = running + 1 if value >= t else 0
            longest = max(longest, running)
        reports[p['player_id']] = dict(games=current, scores=scores, threshold=t, thresholds=lines,
                                       last=last, season=rate(scores, t), later=later, splits=splits,
                                       longest=longest, total=sum(scores), now=now, through=through,
                                       now_rate=rate([g['yards'] for g in now], t) if now else None)
    return reports


def player_link(p: dict) -> str:
    return f'<a href="/{p["slug"]}/">{e(p["name"])}</a>'


def team_players(code: str, players: list[dict] = PLAYER_PAGES) -> str:
    matches = [p for p in players if code in p['teams']]
    return ('<section class="team-players"><h2>Players</h2><ul>' + ''.join(
        f'<li>{player_link(p)} · {p["position"]}</li>' for p in matches) + '</ul></section>')


def player_answer(p: dict, r: dict) -> str:
    stat = p['stat'].replace('_', ' ')
    return (f"{p['name']} recorded {sum(r['scores'][-10:]):,} {stat} in his last {r['last']['n']} played games "
            f"of the 2025 regular season. At {r['threshold']} yards, the rounded median mark, he reached it in "
            f"{count_text(r['last'])}, with a Wilson 95% range of {interval(r['last'])}. Across the season, "
            f"he recorded {r['total']:,} yards in {len(r['games'])} games and reached that mark in {count_text(r['season'])}.")



def observation(p: dict, r: dict) -> str:
    name, t, games = p['name'], r['threshold'], r['games']
    home = [g['yards'] for g in games if g['site'] == 'home']
    away = [g['yards'] for g in games if g['site'] == 'away']
    cut = len(games) // 2
    first, second = rate(r['scores'][:cut], t), rate(r['scores'][cut:], t)
    if home and away and abs(sum(home) / len(home) - sum(away) / len(away)) >= 15:
        side, high, low = ('home', home, away) if sum(home) / len(home) > sum(away) / len(away) else ('away', away, home)
        return (f"{name}'s larger yardage average came {('at home' if side == 'home' else 'away')}: "
                f"{sum(high) / len(high):.1f} yards across {len(high)} games, beside {sum(low) / len(low):.1f} "
                f"across {len(low)} in the other setting. The gap was {abs(sum(high) / len(high) - sum(low) / len(low)):.1f} "
                'yards per played game. The two groups faced different opponents.')
    if band(first['k'], first['n']) != band(second['k'], second['n']):
        return (f"{name} reached {t} yards in {count_text(first)} games in the opening half of his log, "
                f"then {count_text(second)} in the closing half. Those separate halves fell in the "
                f"{BANDS[band(first['k'], first['n'])].lower()} and {BANDS[band(second['k'], second['n'])].lower()} "
                f"rate bands. The split falls after week {games[cut - 1]['week']}.")
    return (f"{name}'s longest run at {t} yards or more lasted {r['longest']} played games. "
            f"The opening half recorded {count_text(first)} reaches, and the closing half recorded {count_text(second)}. "
            f"Both halves fell in the {BANDS[band(first['k'], first['n'])].lower()} band. "
            f"The season contained {len(games) - r['season']['k']} games below {t} yards.")


def player_chart(p: dict, r: dict) -> str:
    top = max(10, math.ceil(max(r['scores'] + [p['median']]) / 50) * 50)
    x = lambda week: 40 + (week - 1) * 30
    y = lambda value: 178 - value / top * 140
    grid = ''.join(f'<line x1="40" x2="550" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text x="30" y="{y(v) + 4:.1f}" text-anchor="end">{v:g}</text>' for v in (0, top / 2, top))
    ticks = ''.join(f'<text x="{x(w)}" y="200" text-anchor="middle">{w}</text>' for w in (1, 5, 10, 15, 18))
    points = ' '.join(f"{x(g['week'])},{y(g['yards']):.1f}" for g in r['games'])
    dots = ''.join(f'<circle cx="{x(g["week"])}" cy="{y(g["yards"]):.1f}" r="3">'
                   f'<title>Week {g["week"]}: {g["yards"]} yards, {e(TEAM_BY_CODE[g["opponent"]]["name"])}</title>'
                   '</circle>' for g in r['games'])
    return (f'<figure class="score-chart player-chart"><svg viewBox="0 0 580 224" role="img" '
            'aria-labelledby="player-title player-desc">'
            f'<title id="player-title">{e(p["name"])} {p["stat"].replace("_", " ")} by week</title>'
            '<desc id="player-desc">Dots mark recorded games. The dashed line marks the exact season median. '
            'The game log gives each value.</desc><g class="chart-grid">' + grid + ticks +
            '<text x="295" y="220" text-anchor="middle">Week</text></g>'
            f'<line class="median-line" x1="40" x2="550" y1="{y(p["median"]):.1f}" y2="{y(p["median"]):.1f}"/>'
            f'<polyline points="{points}"/>{dots}</svg><figcaption>{e(p["name"])} · '
            f'{p["stat"].replace("_", " ").capitalize()} · Dashed median: {p["median"]:g} yards</figcaption></figure>')


def long_date(iso: str) -> str:
    year, month, day = iso.split('-')
    months = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
              'November', 'December')
    return f'{int(day)} {months[int(month) - 1]} {year}'


def now_section(p: dict, r: dict) -> str:
    """The 2026 games so far, measured against the mark and band fixed at the end of 2025."""
    name, stat, t, now = p['name'], p['stat'].replace('_', ' '), r['threshold'], r['now']
    through = long_date(r['through'])
    head = f'<section class="now-card"><h2>{e(name)} in 2026 so far</h2>'
    if not now:
        return (head + f'<p>No 2026 regular-season game for {e(name)} appears in the nflverse file, which holds games '
                f'completed by {through}. Missing weeks add no game and no zero, so this page has no 2026 count.</p>'
                '</section>')
    last, now_rate = r['last'], r['now_rate']
    rows = [[cell(g['week'], True), cell(g['date']), cell(TEAM_BY_CODE[g['opponent']]['name']),
             cell(g['site'].capitalize()), cell(g['yards']), cell('Yes' if g['yards'] >= t else 'No')] for g in now]
    return (head + f'<p>Through games completed by {through}, {e(name)} recorded {len(now)} regular-season '
            f'{"game" if len(now) == 1 else "games"} in 2026 and reached {t}+ {stat} in {count_text(now_rate)}. '
            f'Wilson 95% range: {interval(now_rate)}. His last {last["n"]} games of 2025 reached the same mark in '
            f'{count_text(last)}, the {BANDS[band(last["k"], last["n"])].lower()} band. The mark and that band were '
            'settled before any 2026 game, so these games are later games in the plain sense.</p>' +
            table(['Week', 'Date', 'Opponent', 'Home or away', stat.capitalize(), f'Reached {t}+'], rows,
                  f'{name}: 2026 regular-season games so far') + '</section>')


def player_sources() -> str:
    return ('<section class="sources"><h2>Sources</h2><ul>' + ''.join(
        f'<li><a href="{e(url)}">nflverse weekly player statistics, {year} CSV</a>. Read {PLAYER_READ}.</li>'
        for year, url in zip((2024, 2025), PLAYER_SOURCES)) +
        f'<li><a href="{e(PLAYER_2026_SOURCE)}">nflverse weekly player statistics, 2026 CSV</a>. '
        f'Read {PLAYER_2026_READ}.</li>'
        f'<li><a href="{e(NFL_SOURCE)}">nflverse games.csv</a>. Read {NFL_READ} for 2024 and 2025, and '
        f'{NFL_READ_2026} for 2026. Dates and designated sides.</li>'
        '<li>PLAN-FIXES.md, section 1. Read 2026-11-21. '
        '<a href="/nfl-player-stats/#method">Player page method</a>.</li>' + nfl_credit() + '</ul></section>')


def player_body(p: dict, r: dict) -> str:
    name, stat, t = p['name'], p['stat'].replace('_', ' '), r['threshold']
    fields = POSITION_FIELDS[p['position']]
    rows = [[cell(g['week'], True), cell(g['date']), cell(TEAM_BY_CODE[g['opponent']]['name']),
             cell(g['site'].capitalize()), *[cell(g[key]) for key, label in fields]] for g in r['games']]
    cards = []
    for label, line in zip(('Lower', 'Median', 'Upper'), r['thresholds']):
        counts = []
        for window, values in (('Last 5', r['scores'][-5:]), ('Last 10', r['scores'][-10:]), ('Season', r['scores'])):
            result = rate(values, line)
            counts.append([cell(window, True), cell(count_text(result)), cell(result['n']), cell(interval(result))])
        cards.append(f'<section class="ex trend-card" data-threshold="{line}"><h3>{label}: {line}+ yards</h3>' +
                     table(['Window', 'Reached', 'Games', 'Wilson 95% range'], counts,
                           f'{name}: {line}+ {stat}') + '</section>')
    split_rows = [[cell(label, True), cell(count_text(row) if row else 'No played games'),
                   cell(interval(row) if row else 'No range')] for label, row in r['splits'].items()]
    later = r['later']
    held = ('<strong>too few past spots to tell</strong>.' if later['too_few'] else
            f'<strong>{count_text(later)}</strong> reached {t}+ yards. Wilson 95% range: {interval(later)}.')
    high, low = max(r['games'], key=lambda g: g['yards']), min(r['games'], key=lambda g: g['yards'])
    team_links = ', '.join(team_link(code) for code in p['teams'])
    peers = [other for other in PLAYER_PAGES if other['player_id'] != p['player_id']
             and other['position'] == p['position'] and set(p['teams']) & set(other['teams'])][:2]
    faqs = [
        (f"How many {stat} did {name} record in his last 10 games?",
         f"<p>The last {r['last']['n']} played games contained {sum(r['scores'][-10:]):,} {stat}. "
         f"He reached {t} yards in {count_text(r['last'])} games. The range was {interval(r['last'])}.</p>"),
        (f"What was {name}'s highest yardage game in 2025?",
         f"<p>His high was {high['yards']} {stat}, week {high['week']} against {e(TEAM_BY_CODE[high['opponent']]['name'])} "
         f"on {high['date']}. His low was {low['yards']} yards, week {low['week']}. "
         f"The season total was {r['total']:,} yards in {len(r['games'])} played games.</p>"),
        (f"How long was {name}'s run at {t} yards?",
         f"<p>The longest run at that mark lasted {r['longest']} played games. "
         f"He reached {t} yards in {count_text(r['season'])} games across the season. "
         f"The season range was {interval(r['season'])}.</p>"),
    ]
    return (f'<article><section class="hero search-hero"><h1>{e(p["title"])}</h1>'
            f'<p class="lede">{e(player_answer(p, r))}</p>'
            f'<p class="byline">Checked {p["checked"]} · By Matthew Kerr, who makes BookBreaker</p>' + cta(True) +
            '</section><div class="search-body player-body">'
            f'<p class="player-team">{e(name)} · {p["position"]} · 2025 teams: {team_links}.</p>' +
            player_chart(p, r) + f'<p class="player-observation">{e(observation(p, r))}</p>'
            f'<h2>{e(name)} game log</h2>' +
            table(['Week', 'Date', 'Opponent', 'Home or away', *[label for key, label in fields]], rows,
                  f'{name}: 2025 regular-season games played') +
            f'<h2>{e(name)} at three yardage marks</h2>'
            f'<p>Rounded median: {t} yards. Lower: {r["thresholds"][0]}. Upper: {r["thresholds"][2]}. '
            '<a href="/nfl-player-stats/#method">Threshold rule, game counts and ranges</a>.</p>'
            '<div class="threshold-grid">' + ''.join(cards) + '</div>' +
            f'<h2>{e(name)} splits at {t}+ yards</h2>' +
            table(['2025 split', f'Reached {t}+', 'Wilson 95% range'], split_rows, f'{name}: separate groups of played games') +
            f'<section class="held-card"><h2>Held up later for {e(name)}</h2><p>{held}</p>'
            f'<p>{t}+ {stat} · Last-10 band: {later["band"].lower()} · '
            f'Past spots with later games: {later["spots"]} · Later games: {later["n"]}. '
            '2024 and 2025 regular seasons · Horizon: 5 played games.</p>'
            '<p><a href="/nfl-player-stats/#later">Rules for this individual check</a>. '
            '<a href="/does-a-player-streak-hold-up/">The separate pooled player study</a>.</p></section>' +
            now_section(p, r) + faq(faqs) + player_sources() +
            '<section class="onward"><h2>More player stats</h2><ul>'
            '<li><a href="/nfl-player-stats/">All eligible NFL player logs</a></li>' +
            ''.join(f'<li>{team_link(code)} scoring</li>' for code in p['teams']) +
            ''.join(f'<li>{player_link(other)} · {other["position"]}</li>' for other in peers) +
            '<li><a href="/does-a-player-streak-hold-up/">Player yards shown versus later</a></li>'
            '<li><a href="/is-a-10-game-trend-reliable/">Reading a short-window range</a></li>'
            '</ul></section></div></article>')


def carry_rows(reports: dict) -> list[dict]:
    """Pool 2026 games by each player's final 2025 last-10 band at his own 2025 mark."""
    pooled = [dict(band=label, players=0, shown_k=0, shown_n=0, k=0, n=0) for label in BANDS]
    for p in PLAYER_PAGES:
        r = reports[p['player_id']]
        if not r['now']:
            continue
        row = pooled[band(r['last']['k'], r['last']['n'])]
        row['players'] += 1
        row['shown_k'] += r['last']['k']
        row['shown_n'] += r['last']['n']
        row['k'] += r['now_rate']['k']
        row['n'] += r['now_rate']['n']
    return [row for row in pooled if row['n']]


def carry_section(reports: dict) -> str:
    rows = [[cell(row['band'], True), cell(row['players']), cell(f"{round(100 * row['shown_k'] / row['shown_n'])}%"),
             cell(f"{row['k']} of {row['n']}"), cell(interval(rate([1] * row['k'] + [0] * (row['n'] - row['k']), 1)))]
            for row in carry_rows(reports)]
    through = long_date(next(iter(reports.values()))['through'])
    return ('<h2 id="carry">Did the 2025 rate carry into 2026?</h2>'
            '<p>Each player keeps his own 2025 mark and the band of his last 10 games of 2025. The 2026 columns count '
            f'his regular-season games completed by {through} at that same mark. Players with no 2026 game are left out. '
            'Nothing from 2026 chose a mark or a band.</p>' +
            table(['Last 10 of 2025', 'Players', 'Average shown', 'Reached in 2026', 'Wilson 95% range'], rows,
                  '2025 last-10 bands and the same marks in 2026'))


def player_index_body(reports: dict) -> str:
    sections = []
    for position, label in (('QB', 'Quarterbacks'), ('RB', 'Running backs'), ('WR', 'Wide receivers'), ('TE', 'Tight ends')):
        players = [p for p in PLAYER_PAGES if p['position'] == position]
        rows = []
        for p in players:
            r = reports[p['player_id']]
            rows.append([f'<th scope="row">{player_link(p)}</th>', cell(', '.join(p['teams'])), cell(len(r['games'])),
                         cell(f'{p["median"]:g}'), cell(r['threshold']), cell(count_text(r['last'])), cell(interval(r['last']))])
        sections.append(f'<h2 id="{position.lower()}">{label}: {len(players)} players</h2>' +
                        table(['Player', '2025 team', 'Games', 'Median yards', 'Rounded mark', 'Last 10 at mark',
                               'Wilson 95% range'], rows, f'2025 {label.lower()}: main yards stat'))
    return (f'<article><section class="hero search-hero"><h1>{PLAYER_INDEX["title"]}</h1>'
            f'<p class="lede">These {len(PLAYER_PAGES)} NFL player logs show passing, rushing or receiving yards from the '
            '2025 regular season. Read each played game, the last 10 count and its Wilson range. Each player page adds '
            'three yardage marks, home and away splits, a count of later games after similar past rates, and his 2026 '
            'games so far at the same mark.</p>'
            f'<p class="byline">Checked {PLAYER_INDEX["checked"]} · By Matthew Kerr, who makes BookBreaker</p>' + cta(True) +
            '</section><div class="search-body player-body"><nav class="position-nav" aria-label="Player positions">'
            '<a href="#qb">QB</a><a href="#rb">RB</a><a href="#wr">WR</a><a href="#te">TE</a></nav>' + ''.join(sections) + carry_section(reports) +
            '<h2 id="method">Which players and games are here?</h2>'
            '<p>I kept quarterbacks, running backs, wide receivers and tight ends with at least 8 recorded games '
            'in the 2025 regular season and an exact median of at least 10 yards in their main stat. '
            'That stat is passing yards for QB, rushing yards for RB, and receiving yards for WR and TE. '
            'The median averages the two middle values when the game count is even.</p>'
            '<p>A CSV row means a game played. Missing weeks add no game and no zero. A blank stat within a recorded '
            'row counts as zero. Only regular-season rows enter the calculations. January 2026 dates in these tables '
            'belong to the 2025 season. 2026 rows appear only in the 2026 sections and the carry table, and never '
            'change a 2025 mark, count or later check.</p>'
            '<p>The last 5 and last 10 mean the final played games, with fewer than 10 when the log is shorter. '
            'Each count includes a value equal to the mark. Games column n and reaches k appear together. '
            'For the three card thresholds, take the exact 2025 median, round upward to a whole yard, then multiply '
            'by 0.75, 1 and 1.25. Round each result to the nearest 5 yards, with halfway values rounded upward. '
            'Small medians can give two cards the same threshold. The middle card is the rounded median mark used '
            'by splits and the later check. The chart line marks the exact median.</p>'
            '<p>Home and away mean designated sides from games.csv, including neutral venues. Division means the '
            'opponents were division rivals in that recorded game. A player with more than one team keeps all his '
            'recorded games. Team lists name every team in his 2025 log. Empty split groups have no rate or range.</p>'
            '<p>Wilson 95% ranges use z = 1.96 and endpoints rounded to whole percentages. They describe sampling '
            'doubt under a model of separate trials with a common rate. Shared opponents and changing conditions '
            'limit that model. <a href="/is-a-10-game-trend-reliable/">Read the range calculation</a>.</p>'
            '<h2 id="later">What held up later counts</h2>'
            '<p>The rounded 2025 median mark and the final last-10 rate band set each player’s question. '
            'Across his 2024 and 2025 regular-season games in date order, each past spot uses only the 10 played '
            'games ending there. The bands are under 40%, 40 to 59%, 60 to 69%, 70 to 79%, and 80% and over. '
            'A spot in the same band contributes up to 5 games played after it. The next spot is at least '
            '5 played games later. Those later groups never overlap within a player’s check. Partial groups '
            'at the end stay in the count.</p>'
            '<p>With fewer than 15 later games, the page says “too few past spots to tell” and hides the score '
            'and range. Otherwise it gives x of y and the Wilson range. The mark comes from the full 2025 season. '
            'This describes stored results; it is not a test of a number fixed before 2025.</p>'
            '<p><a href="/does-a-player-streak-hold-up/">The pooled player study</a> uses a different question: '
            'a 2024 mark, 2025 spots and outcomes, and a six-game step between spots in the same band. '
            'Its group results are separate from these individual checks.</p>' + faq([
                ('Why are some players absent?', '<p>They had fewer than 8 recorded 2025 games, a main-stat median below 10 yards, or a position outside QB, RB, WR and TE.</p>'),
                ('Do missed games count as zero?', '<p>No. Only recorded played games count. A player with 8 games has a last-10 count out of 8.</p>'),
                ('What does each index row compare?', '<p>Each row uses that player’s own rounded median mark. Players have different marks, listed beside the counts.</p>'),
            ]) + player_sources() + '</div></article>')
