/* The calculators on bookbreaker.bet.

   There is no arithmetic in this file, on purpose. A second implementation of
   the maths in JavaScript would drift from the engine, and nobody would see it
   until a bet was placed on the difference. So this file does three things: it
   loads the engine, hands it what was typed as plain strings, and draws what
   comes back. Reading "+150", the stakes, the percentages and the rounding all
   happen in the engine and in calc.py, which formats each answer the way the
   worked example on the same page does. The build refuses to publish this file
   if it grows a Math call or a number parser.

   Nothing is fetched until someone presses Calculate for the first time. Then
   the browser loads Pyodide (a Python runtime) from jsDelivr, installs the
   same engine wheel this site offers for download, and runs calc.py. After
   that every answer is local and instant. What you type never leaves the page.

   The capitalised constants below are filled in by render.py from measured
   facts: the pinned Pyodide version and its hash, the wheel the site is
   announcing, and the size that was measured. */
(function () {
  'use strict';

  var BASE = 'https://cdn.jsdelivr.net/pyodide/v0.29.5/full/';
  var SRI = 'sha384-VR47TfKeAmT7vMej7bwOVg0tHTQLLGMSIpsXtFMCZG5OpKZSIXoSLtGY//qHcxc6';
  var PACKAGES = ["micropip", "sqlite3"];
  var WHEEL = '/releases/overlay-0.1.11-py3-none-any.whl';
  var RUNNER = '/calc.py?v=5b45fa39fe';
  var SIZE = '6';
  var VERSION = '0.1.11';

  var boxes = document.querySelectorAll('form[data-calc]');
  if (!boxes.length) return;

  var loading = null;

  function script(src) {
    return new Promise(function (resolve, reject) {
      var tag = document.createElement('script');
      tag.src = src;
      tag.integrity = SRI;
      tag.crossOrigin = 'anonymous';
      tag.onload = resolve;
      tag.onerror = function () { reject(new Error('runtime')); };
      document.head.appendChild(tag);
    });
  }

  function text(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error(url);
      return r.text();
    });
  }

  /* Resolves to calc.run_json, the one function the page calls. */
  function engine() {
    if (loading) return loading;
    var py;
    loading = script(BASE + 'pyodide.js')
      .then(function () { return window.loadPyodide({ indexURL: BASE }); })
      .then(function (p) { py = p; return py.loadPackage(PACKAGES); })
      .then(function () {
        py.globals.set('wheel_url', location.origin + WHEEL);
        return py.runPythonAsync(
          'import micropip\nawait micropip.install(wheel_url, deps=False)');
      })
      .then(function () { return text(RUNNER); })
      .then(function (source) {
        py.FS.writeFile('/home/pyodide/calc.py', source);
        return py.pyimport('calc').run_json;
      })
      .catch(function (err) {
        loading = null;
        throw err;
      });
    return loading;
  }

  function add(parent, tag, cls, content) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (content !== undefined) el.textContent = content;
    parent.appendChild(el);
    return el;
  }

  function say(out, cls, content) {
    out.textContent = '';
    add(out, 'p', cls, content);
  }

  function row(parent, cells, tag) {
    var tr = add(parent, 'tr');
    cells.forEach(function (cell) { add(tr, tag, '', cell); });
  }

  function draw(out, result) {
    out.textContent = '';
    if (!result.ok) {
      add(out, 'p', 'own-no', result.error);
      return;
    }
    if (result.headline) add(out, 'span', 'own-big', result.headline);
    if (result.caption) add(out, 'span', 'own-cap', result.caption);
    if (result.table) {
      var wrap = add(out, 'div', 'scroll');
      var table = add(wrap, 'table');
      if (result.table.head) row(table, result.table.head, 'th');
      result.table.rows.forEach(function (cells) { row(table, cells, 'td'); });
    }
    (result.notes || []).forEach(function (note) { add(out, 'p', 'own-cap', note); });
    add(out, 'p', 'own-note',
        'Worked out in this browser by Bookbreaker’s engine, release ' +
        VERSION + ', the one you can download. Nothing you typed was sent anywhere.');
  }

  function values(form) {
    var typed = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name) return;
      typed[el.name] = el.type === 'checkbox' ? (el.checked ? 'yes' : '') : el.value;
    });
    return JSON.stringify(typed);
  }

  Array.prototype.forEach.call(boxes, function (form) {
    var out = form.parentNode.querySelector('.own-out');
    var button = form.querySelector('button[type="submit"]');
    button.disabled = false;

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      var slug = form.getAttribute('data-calc');
      var typed = values(form);
      button.disabled = true;
      if (!loading) {
        say(out, 'own-hint', 'Loading the engine (once, about ' + SIZE + ' MB)…');
      }
      engine().then(function (runJson) {
        draw(out, JSON.parse(runJson(slug, typed)));
      }).catch(function () {
        say(out, 'own-no', 'The engine did not load, so there is no answer to ' +
            'show here; the worked example on this page still stands.');
      }).then(function () {
        button.disabled = false;
      });
    });
  });
})();
