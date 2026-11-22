"""Build the Streakgauge site (streakgauge.com) from the same sources, into a folder of its own. Offline.

Usage: python3 _src/launch.py OUTDIR
It builds with the new origin, renames the brand, swaps the mark and icons, writes CNAME, robots.txt and the IndexNow key
file, then gates the result: the usual site gate, no BookBreaker or .bet left anywhere, and every page answering. It does
not deploy. Launch-day steps are in _launch/README.md.
"""
from __future__ import annotations

import contextlib
import io
import re
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parent
REPO = SOURCE.parent
ASSETS = REPO / '_launch' / 'streakgauge-assets'
sys.path.insert(0, str(SOURCE))

import build  # noqa: E402
import check  # noqa: E402
from pages import PUBLISHED  # noqa: E402
from redirects import NEW_ORIGIN  # noqa: E402

NAME, DOMAIN = 'Streakgauge', 'streakgauge.com'
OLD = re.compile(r'book\s*breaker|bookbreaker|\.bet\b', re.I)
STATIC = ['style.css', 'fonts']
ICONS = ['icon.svg', 'favicon.ico', 'apple-touch-icon.png', 'icon-512.png']
MARK = ('<svg class="mark" viewBox="0 0 64 64" aria-hidden="true">' +
        (ASSETS / 'icon.svg').read_text().split('>', 1)[1].strip().removesuffix('</svg>').replace('sgTile', 'sgTileM') +
        '</svg>')
# Bing gives each domain its own verification code; the new one is added on launch day (Matthew's Bing sign-in).
BING = re.compile(r'<meta name="msvalidate\.01" content="[^"]*" />\n')


def rename(text: str) -> str:
    text = text.replace(build.MARK, MARK)
    text = BING.sub('', text)
    return text.replace('bookbreaker.bet', DOMAIN).replace('BookBreaker', NAME)


def make(out: Path) -> None:
    if out.exists() and any(p for p in out.iterdir() if p.name != '.git'):
        raise SystemExit(f'{out} is not empty; give an empty folder or remove its old build first')
    out.mkdir(parents=True, exist_ok=True)
    with patch.object(build, 'SITE', out), patch.object(build, 'ORIGIN', NEW_ORIGIN), \
            contextlib.redirect_stdout(io.StringIO()):
        build.main()
    for path in out.rglob('*'):
        if path.suffix in ('.html', '.txt', '.xml') and '.git' not in path.parts:
            path.write_text(rename(path.read_text()))
    for name in STATIC:
        source = REPO / name
        (shutil.copytree if source.is_dir() else shutil.copy2)(source, out / name)
    for name in ICONS:
        shutil.copy2(ASSETS / name, out / name)
    key = (ASSETS / 'indexnow-key.txt').read_text().strip()
    (out / f'{key}.txt').write_text(key + '\n')
    (out / 'CNAME').write_text(DOMAIN + '\n')
    (out / 'robots.txt').write_text(f'User-agent: *\nAllow: /\n\nSitemap: {NEW_ORIGIN}/sitemap.xml\n')
    (out / 'README.md').write_text(
        f'# {DOMAIN}\n\nThe website for {NAME}, a planned sports statistics app for Mac and Windows. Built by '
        '`_src/launch.py` in the site source repo; edit the sources there, never these files.\n')


def gate(out: Path) -> list[str]:
    fails = []
    published = [*PUBLISHED, f'{(ASSETS / "indexnow-key.txt").read_text().strip()}.txt']
    hosts = check.allowed_hosts()  # read from the repo's registry before the gate points at the build folder
    with patch.object(check, 'allowed_hosts', lambda: hosts), \
            patch.object(check, 'SITE', out), patch.object(check, 'PUBLISHED', published), \
            patch.object(check, 'DOMAIN', re.compile(re.escape(DOMAIN), re.I)), \
            patch.object(check, 'OWN_HOST', DOMAIN), contextlib.redirect_stdout(io.StringIO()) as log:
        if check.main():
            fails += [line[5:] for line in log.getvalue().splitlines() if line.startswith('FAIL ')]
    for path in out.rglob('*'):
        if path.is_file() and '.git' not in path.parts and path.suffix in ('.html', '.txt', '.xml', '.md', '.svg', '.css'):
            for m in OLD.finditer(path.read_text()):
                fails.append(f'{path.relative_to(out)}: old name {m.group(0)!r}')
    for rel in ICONS + ['CNAME', 'robots.txt']:
        if not (out / rel).exists():
            fails.append(f'missing {rel}')
    return fails


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out = Path(sys.argv[1]).expanduser().resolve()
    make(out)
    fails = gate(out)
    for line in fails:
        print('FAIL', line)
    print(f'STREAKGAUGE GREEN: {sum(1 for p in out.rglob("*.html"))} pages in {out}' if not fails
          else f'{len(fails)} problem(s)')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
