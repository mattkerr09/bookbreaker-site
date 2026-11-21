"""Prepare the launch redirect kit offline. Only --verify uses the network."""
from __future__ import annotations

import argparse
import csv
import html
import http.client
from pathlib import Path
import sys
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET

SITE = Path(__file__).resolve().parents[1]
NEW_ORIGIN = "https://streakgauge.com"
EXTRA_PATHS = ("/llms.txt", "/sitemap.xml", "/robots.txt", "/privacy/")


def mapping(sitemap_path: Path, new_origin: str) -> list[tuple[str, str]]:
    target = urlsplit(new_origin)
    if (target.scheme != "https" or target.netloc != "streakgauge.com"
            or target.path not in ("", "/") or target.query or target.fragment):
        raise ValueError("new origin must be the HTTPS Streakgauge host")
    urls = [node.text.strip() for node in ET.parse(sitemap_path).findall(
        "{http://www.sitemaps.org/schemas/sitemap/0.9}url/"
        "{http://www.sitemaps.org/schemas/sitemap/0.9}loc") if node.text]
    if not urls:
        raise ValueError("sitemap has no URLs")
    source = urlsplit(urls[0])
    for url in urls:
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.netloc != "bookbreaker.bet"
                or parts.query or parts.fragment or not parts.path.startswith("/")
                or any(p in (".", "..") for p in parts.path.split("/"))):
            raise ValueError(f"invalid old URL: {url}")
    urls.extend(urlunsplit((source.scheme, source.netloc, path, "", "")) for path in EXTRA_PATHS)
    return [(old, new_origin.rstrip("/") + urlsplit(old).path) for old in dict.fromkeys(urls)]


def write_csv(pairs: list[tuple[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        for old, new in pairs:
            writer.writerow((old, new, 301, "true", "false", "false", "false"))


def write_stubs(pairs: list[tuple[str, str]], output: Path) -> None:
    output = output.resolve()
    if output == SITE or output in SITE.parents or (SITE in output.parents and SITE / "_launch" not in (output, *output.parents)):
        raise ValueError("stubs must stay outside the live tree; use a temporary directory or _launch/stubs")
    for old, new in pairs:
        path = urlsplit(old).path
        relative = path.lstrip("/") + ("index.html" if path.endswith("/") else "")
        dest = output / relative
        if output not in dest.resolve().parents:
            raise ValueError(f"stub path escapes output: {path}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = html.escape(new, quote=True)
        dest.write_text('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
                        '<title>Page moved</title>\n'
                        f'<link rel="canonical" href="{url}">\n'
                        f'<meta http-equiv="refresh" content="0; url={url}">\n'
                        f'</head><body><p><a href="{url}">This page has moved.</a></p></body></html>\n',
                        encoding="utf-8")


def request(url: str) -> tuple[int, dict[str, str]]:
    """One GET, no redirect following. The caller can replace this transport."""
    parts = urlsplit(url)
    connection = http.client.HTTPSConnection(parts.netloc, timeout=15)
    try:
        connection.request("GET", urlunsplit(("", "", parts.path or "/", parts.query, "")))
        response = connection.getresponse()
        return response.status, dict(response.getheaders())
    finally:
        connection.close()


def verify(pairs: list[tuple[str, str]], transport=request, output=None) -> int:
    output = sys.stdout if output is None else output
    misses = 0
    for old, new in pairs:
        try:
            status, headers = transport(old)
            location = next((value for key, value in headers.items() if key.lower() == "location"), None)
            if status == 301 and location == new:
                print(f"PASS {old}", file=output)
                continue
            detail = f"status {status}, Location {location!r}; expected 301, Location {new!r}"
        except (OSError, http.client.HTTPException) as error:
            detail = str(error)
        misses += 1
        print(f"MISS {old}: {detail}", file=output)
    print(f"{len(pairs)} redirects checked; {misses} misses", file=output)
    return 1 if misses else 0


def main(argv=None, transport=request) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sitemap", type=Path, default=SITE / "sitemap.xml")
    parser.add_argument("--new-origin", default=NEW_ORIGIN)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--csv", type=Path, metavar="OUT")
    action.add_argument("--stubs", type=Path, metavar="OUTDIR")
    action.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    try:
        pairs = mapping(args.sitemap, args.new_origin)
        if args.verify:
            source = urlsplit(pairs[0][0])
            old_origin = urlunsplit((source.scheme, source.netloc, "", "", ""))
            www_origin = urlunsplit((source.scheme, "www." + source.netloc, "", "", ""))
            pairs.extend([
                (old_origin + "/no-such-page/", args.new_origin.rstrip("/") + "/no-such-page/"),
                (old_origin + "/llms.txt?x=1", args.new_origin.rstrip("/") + "/llms.txt?x=1"),
                (www_origin + "/no-such-page/", args.new_origin.rstrip("/") + "/no-such-page/"),
            ])
            return verify(pairs, transport)
        if args.csv:
            write_csv(pairs, args.csv)
        else:
            write_stubs(pairs, args.stubs)
    except (OSError, ValueError, ET.ParseError) as error:
        parser.error(str(error))
    print(f"wrote {len(pairs)} redirects")
    return 0


if __name__ == "__main__":
    sys.exit(main())
