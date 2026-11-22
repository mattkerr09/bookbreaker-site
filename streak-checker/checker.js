(function () {
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
        r.y + '</strong> later games (up to 5 after each past run). Wilson 95% range: ' + range(r.x, r.y) + '. Past spots: ' + r.spots + '.</p>';
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
