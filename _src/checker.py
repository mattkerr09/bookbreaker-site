"""The free "did the streak hold?" checker: one data file of NFL player yards and a small script that runs in the browser.

Every QB, RB, WR and TE with at least 5 regular-season games from 2024 to the current 2026 read. The visitor chooses a
player, a yardage number and the last 5 or 10 games. The script counts reaches in that window with a Wilson range, then
walks the player's own past games for spots in the same rate band and counts the next 5 games after each, the same rule
as the player pages (stats.spots, horizon 5, under 15 later games shows "too few past spots to tell"). Nothing is sent
anywhere; there is no form.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date

from content import cta, e, faq, nfl_credit
from nfl import TEAM_BY_CODE
from player_data import (MAIN_STAT, PLAYER_2026_READ, PLAYER_2026_SOURCE, PLAYER_READ, PLAYER_SOURCES, read_2026_rows,
                         read_player_rows)
from stats import NFL_READ, NFL_READ_2026, NFL_SOURCE, current_season_scores, season_scores

SLUG = 'streak-checker'
TITLE = 'Did the streak hold? A free NFL player streak checker'
DESCRIPTION = ('Choose an NFL player and a yardage number. See how often he reached it in his last 5 or 10 games, with a '
               'range, and how his similar past runs did in the next 5 games.')
EPOCH = date(2024, 1, 1)
MIN_GAMES = 5


def checker_data(rows: list[dict] | None = None, rows_2026: list[dict] | None = None) -> dict:
    """Players with their main-stat values in date order, as compact [day, opponent index, value] triples."""
    schedule = {}
    for season in (2024, 2025):
        for code, games in season_scores(season=season).items():
            for g in games:
                schedule[(code, g['id'])] = g
    for code, games in current_season_scores().items():
        for g in games:
            schedule[(code, g['id'])] = g
    logs = defaultdict(list)
    for row in [*(read_player_rows() if rows is None else rows), *(read_2026_rows() if rows_2026 is None else rows_2026)]:
        if row['season_type'] == 'REG' and row['position'] in MAIN_STAT:
            logs[row['player_id']].append(row)
    teams = sorted(TEAM_BY_CODE)
    players = []
    for identity, log in logs.items():
        log.sort(key=lambda r: (int(r['season']), int(r['week'])))
        last = log[-1]
        stat = MAIN_STAT[last['position']]
        games = []
        for row in log:
            game = schedule.get((row['team'], row['game_id']))
            if game is None or game['opponent'] != row['opponent_team'] or game['week'] != int(row['week']):
                raise ValueError(f"unmatched player game: {row['game_id']}")
            day = (date.fromisoformat(game['date']) - EPOCH).days
            games.append([day, teams.index(row['opponent_team']), int(float(row[stat] or 0))])
        games.sort()
        if len({g[0] for g in games}) != len(games):
            raise ValueError(f'two games on one day for {identity}')
        if len(games) < MIN_GAMES:
            continue
        values = sorted(g[2] for g in games[-17:])
        mid = (values[(len(values) - 1) // 2] + values[len(values) // 2]) / 2
        players.append({'n': last['player_display_name'], 'p': last['position'], 't': last['team'],
                        's': stat.replace('_', ' '), 'm': max(5, 5 * round(math.ceil(mid) / 5)), 'g': games})
    players.sort(key=lambda p: (p['n'], p['p'], p['t']))
    return {'epoch': EPOCH.isoformat(), 'teams': [TEAM_BY_CODE[code]['name'] for code in teams],
            'read': PLAYER_2026_READ, 'players': players}


SCRIPT = r"""(function () {
  'use strict';
  var BANDS = ['under 40%', '40 to 59%', '60 to 69%', '70 to 79%', '80% and over'];
  var HORIZON = 5, MIN_LATER = 15;
  function band(k, n) {
    var limits = [40, 60, 70, 80];
    for (var i = 0; i < limits.length; i++) { if (100 * k < limits[i] * n) return i; }
    return 4;
  }
  function wilson(k, n) {
    var z = 1.96, p = k / n, d = 1 + z * z / n;
    var c = (p + z * z / (2 * n)) / d;
    var h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d;
    return [Math.max(0, c - h), Math.min(1, c + h)];
  }
  function pct(x) { return Math.round(100 * x) + '%'; }
  function range(k, n) { var w = wilson(k, n); return pct(w[0]) + ' to ' + pct(w[1]); }
  // The same rule as the player pages: spots chosen from the window ending at each game, never from later games;
  // after a spot, the next one waits until its 5 later games have passed; partial groups at the end still count.
  function heldUp(values, threshold, window) {
    var recent = values.slice(-window), k = 0;
    recent.forEach(function (v) { if (v >= threshold) k++; });
    var target = band(k, recent.length), x = 0, y = 0, spots = 0, next = window - 1;
    for (var d = window - 1; d < values.length; d++) {
      if (d < next) continue;
      var hits = 0;
      for (var i = d - window + 1; i <= d; i++) { if (values[i] >= threshold) hits++; }
      if (band(hits, window) === target) {
        var later = values.slice(d + 1, d + 1 + HORIZON);
        if (later.length) spots++;
        later.forEach(function (v) { y++; if (v >= threshold) x++; });
        next = d + HORIZON;
      }
    }
    return {k: k, n: recent.length, band: target, x: x, y: y, spots: spots, tooFew: y < MIN_LATER};
  }
  function check(player, threshold, window) {
    return heldUp(player.g.map(function (g) { return g[2]; }), threshold, Math.min(window, player.g.length));
  }
  if (typeof module !== 'undefined') { module.exports = {band: band, wilson: wilson, heldUp: heldUp, check: check}; return; }

  var root = document.getElementById('checker');
  var data = null;
  var form = root.querySelector('form');
  var who = root.querySelector('#who'), line = root.querySelector('#line'), win = root.querySelector('#win');
  var out = root.querySelector('#result'), list = root.querySelector('#players');
  function label(p) { return p.n + ' · ' + p.p + ' · ' + p.t; }
  function find() {
    var text = who.value.trim().toLowerCase();
    if (!data || !text) return null;
    var exact = data.players.filter(function (p) { return label(p).toLowerCase() === text; });
    if (exact.length) return exact[0];
    var named = data.players.filter(function (p) { return p.n.toLowerCase() === text; });
    return named.length ? named[named.length - 1] : null;
  }
  function day(n) {
    var d = new Date(data.epoch + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }
  function render() {
    var p = find();
    if (!p) { out.innerHTML = '<p>Choose a player from the list.</p>'; return; }
    if (document.activeElement !== line && !line.dataset.touched) line.value = p.m;
    var t = parseInt(line.value, 10);
    if (!(t >= 0)) { out.innerHTML = '<p>Type a whole number of yards, 0 or more.</p>'; return; }
    var w = parseInt(win.value, 10), r = check(p, t, w);
    var rows = p.g.slice(-r.n).map(function (g) {
      return '<tr><td>' + day(g[0]) + '</td><td>' + esc(data.teams[g[1]]) + '</td><td>' + g[2] + '</td><td>' +
        (g[2] >= t ? 'Yes' : 'No') + '</td></tr>';
    }).join('');
    var held = r.tooFew
      ? '<p><strong>Too few past spots to tell.</strong> His past runs in the ' + BANDS[r.band] + ' band were followed by ' +
        r.y + ' later games; the check needs 15.</p>'
      : '<p>After past runs in the same band (' + BANDS[r.band] + '), he reached ' + t + '+ in <strong>' + r.x + ' of ' +
        r.y + '</strong> of the next 5 games. Wilson 95% range: ' + range(r.x, r.y) + '. Past spots: ' + r.spots + '.</p>';
    out.innerHTML = '<div class="checker-card"><h2>' + esc(p.n) + ', ' + t + '+ ' + esc(p.s) + '</h2>' +
      '<p class="checker-big">' + r.k + ' of ' + r.n + '</p><p>His latest ' + r.n + ' played games (data read ' +
      esc(data.read) + '). Wilson 95% range: ' + range(r.k, r.n) + '.</p><h3>Did runs like this hold?</h3>' + held +
      '<h3>The games counted</h3><table><caption>' + esc(p.n) + ': last ' + r.n + ' games</caption><thead><tr>' +
      '<th scope="col">Date</th><th scope="col">Opponent</th><th scope="col">Yards</th><th scope="col">Reached ' + t +
      '+</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }
  fetch('/streak-checker/nfl.json').then(function (r) { return r.json(); }).then(function (d) {
    data = d;
    list.innerHTML = d.players.map(function (p) { return '<option value="' + esc(label(p)) + '"></option>'; }).join('');
    root.querySelector('.checker-status').textContent = d.players.length + ' players loaded. Data read ' + d.read + '.';
    var start = d.players.filter(function (p) { return p.n === 'Justin Jefferson'; })[0] || d.players[0];
    who.value = label(start);
    render();
  });
  line.addEventListener('input', function () { line.dataset.touched = '1'; render(); });
  who.addEventListener('change', function () { delete line.dataset.touched; render(); });
  win.addEventListener('change', render);
  form.addEventListener('submit', function (event) { event.preventDefault(); render(); });
})();
"""


def checker_body() -> str:
    faqs = [
        ('Where do the numbers come from?',
         '<p>From nflverse weekly player statistics for the 2024, 2025 and 2026 regular seasons, joined to the nflverse '
         f'schedules file for dates and opponents. The 2026 file was read {PLAYER_2026_READ} and is read again each '
         'Tuesday during the season.</p>'),
        ('Which number does each player use?',
         '<p>Passing yards for quarterbacks, rushing yards for running backs, and receiving yards for wide receivers and '
         'tight ends, by the position on his latest recorded game. The box starts at his median over his latest 17 games, '
         'rounded to the nearest 5 yards. Type any number you like.</p>'),
        ('What counts as a game?',
         '<p>A recorded regular-season game. Missed weeks add no game and no zero. A game equal to the number counts as '
         'reaching it. Postseason games are left out.</p>'),
        ('Is anything I type sent anywhere?',
         '<p>No. The page loads one data file and does the counting in your browser. There is no form to submit and '
         'nothing is stored.</p>'),
    ]
    return (f'<article><section class="hero search-hero"><h1>{e(TITLE)}</h1>'
            '<p class="lede">Choose a player and a yardage number. The checker counts how often he reached it in his last '
            '5 or 10 games, with a range, then looks back at his own past runs at the same rate and counts what came in '
            'the next 5 games.</p>' + cta(True) + '</section>'
            '<div class="search-body" id="checker">'
            '<form class="checker-form" autocomplete="off">'
            '<label for="who">Player</label><input id="who" list="players" placeholder="Start typing a name">'
            '<datalist id="players"></datalist>'
            '<label for="line">Yards</label><input id="line" type="number" min="0" step="1" inputmode="numeric">'
            '<label for="win">Games</label><select id="win"><option value="5">Last 5</option>'
            '<option value="10" selected>Last 10</option></select></form>'
            '<p class="checker-status" aria-live="polite">Loading players.</p>'
            '<div id="result" aria-live="polite"><noscript><p>The checker needs JavaScript. Every player page under '
            '<a href="/nfl-player-stats/">NFL player stats</a> shows the same counts without it.</p></noscript></div>'
            '<h2>How the later check works</h2>'
            '<p>The rate in your window falls in one of five bands: under 40%, 40 to 59%, 60 to 69%, 70 to 79%, and 80% '
            'and over. The checker walks through the player\'s games in date order. At each game it reads only the window '
            'ending there. When that rate falls in your band, it counts the next 5 games he played, then skips ahead '
            'past them, so no later game counts twice. Under 15 later games, it says so instead of showing a rate.</p>'
            '<p>Across every NFL player we checked, high recent rates came back toward the middle in the games after. '
            'Read <a href="/does-a-player-streak-hold-up/">the pooled player study</a> and the '
            '<a href="/nfl-player-stats/#carry">2025 to 2026 carry table</a>.</p>' +
            faq(faqs) +
            '<section class="sources"><h2>Sources</h2><ul>' + ''.join(
                f'<li><a href="{e(url)}">nflverse weekly player statistics, {year} CSV</a>. Read '
                f'{PLAYER_READ if year < 2026 else PLAYER_2026_READ}.</li>'
                for year, url in ((2024, PLAYER_SOURCES[0]), (2025, PLAYER_SOURCES[1]), (2026, PLAYER_2026_SOURCE))) +
            f'<li><a href="{e(NFL_SOURCE)}">nflverse games.csv</a>. Read {NFL_READ} for 2024 and 2025, and '
            f'{NFL_READ_2026} for 2026.</li>' + nfl_credit() + '</ul></section>'
            '</div></article><script src="/streak-checker/checker.js" defer></script>')
