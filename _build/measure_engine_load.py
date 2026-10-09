#!/usr/bin/env python3
"""Measure what a visitor downloads the first time they press Calculate, and
record it in _data/engine_load.json.

The calculators run the engine in the browser, which means the browser first
fetches a Python runtime (Pyodide) from jsDelivr. That is the one cost of the
feature and the one number a person pressing the button is owed, so it is
measured rather than guessed: every file the runtime loads is asked for the
way a browser asks (Accept-Encoding: br), and the size jsDelivr reports for
what it will send is summed.

The file list is Pyodide's core files plus the packages calc.js loads and their
dependencies, read out of that version's own pyodide-lock.json. It was checked
against a cold-cache trace of a real headless Chrome the first time it was
written (2026-10-09, Pyodide 0.29.5): the same eight files, within the headers.

The script also records the SRI hash of pyodide.js, which calc.js puts on the
script tag. A script loaded from a CDN on a page about betting is worth pinning
to the exact bytes that were tested.

Nothing else is recorded. The wheel and calc.py come from this site, and
render.py adds their sizes to the total itself.

    python3 _build/measure_engine_load.py                  # re-measure the pinned version
    python3 _build/measure_engine_load.py --pyodide 0.29.6 # move the pin, then render
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
RECORD = SITE / "_data" / "engine_load.json"
BASE = "https://cdn.jsdelivr.net/pyodide/v{version}/full/"
CORE = ("pyodide.js", "pyodide-lock.json", "pyodide.asm.js",
        "pyodide.asm.wasm", "python_stdlib.zip")
#: What calc.js asks pyodide.loadPackage for. micropip installs the engine's
#: wheel; the engine imports sqlite3 at package import, though no calculator
#: touches a ledger.
PACKAGES = ["micropip", "sqlite3"]


def ask(url: str, method: str = "GET", encoding: str = "identity"):
    request = urllib.request.Request(
        url, method=method,
        headers={"Accept-Encoding": encoding, "User-Agent": "bookbreaker-measure"})
    return urllib.request.urlopen(request, timeout=60)


def size_sent(url: str) -> int | None:
    """Bytes jsDelivr sends for this file to a browser that accepts Brotli, or
    None when the version does not have the file at all."""
    try:
        with ask(url, "HEAD", "br") as response:
            return int(response.headers["Content-Length"])
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def closure(lock: dict, names: list[str]) -> list[str]:
    seen: list[str] = []

    def visit(name: str) -> None:
        key = name.lower()
        if key not in lock["packages"]:
            raise SystemExit(f"pyodide-lock.json has no package {name!r}")
        if key in seen:
            return
        for dep in lock["packages"][key].get("depends", []):
            visit(dep)
        seen.append(key)

    for name in names:
        visit(name)
    return seen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pyodide", help="the version to pin, like 0.29.5")
    args = parser.parse_args()

    previous = json.loads(RECORD.read_text()) if RECORD.exists() else {}
    version = args.pyodide or previous.get("pyodide")
    if not version:
        raise SystemExit("no version recorded yet: pass --pyodide 0.29.5")
    base = BASE.format(version=version)

    with ask(base + "pyodide-lock.json") as response:
        lock = json.load(response)
    names = [lock["packages"][p]["file_name"] for p in closure(lock, PACKAGES)]

    files = []
    for name in list(CORE) + names:
        size = size_sent(base + name)
        if size is None:
            print(f"  not in this version: {name}")
            continue
        files.append({"name": name, "bytes": size})
        print(f"  {size:>9,}  {name}")

    with ask(base + "pyodide.js") as response:
        digest = hashlib.sha384(response.read()).digest()

    record = {
        "pyodide": version,
        "sri": "sha384-" + base64.b64encode(digest).decode(),
        "packages": PACKAGES,
        "measured": datetime.date.today().isoformat(),
        "how": ("Content-Length of each file as jsDelivr sends it to a "
                "browser that accepts Brotli, summed. The wheel and calc.py "
                "are added from this site's own files."),
        "files": files,
        "bytes": sum(f["bytes"] for f in files),
    }
    RECORD.write_text(json.dumps(record, indent=2) + "\n")
    print(f"\n  {record['bytes']:,} bytes from jsDelivr for Pyodide {version}")
    print(f"  recorded in {RECORD.relative_to(SITE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
