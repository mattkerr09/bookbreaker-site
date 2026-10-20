#!/usr/bin/env python3
"""Structured data may only say what the page says.

    python3 _build/verify_structured_data_matches_page.py              # every built page (_build/gates.sh runs it)
    python3 _build/verify_structured_data_matches_page.py --self-test

Copied as is from docket-site scripts/ on 2026-10-19 (the CEO). Two changes only: SITE is this repo's root, where
render.py writes the built pages, and folders starting with "_" or "." (the build tools, git) are skipped.

WHY. Google's structured-data rules say the markup must describe content the reader can see: an FAQ question that
exists only in JSON-LD is "content that is not visible to the user". On 19 October 2026 a sister site found 34 pages
whose FAQPage carried questions nobody could read, some of them copied in from another page's schema. Nothing here
checked for that. The first run on docketseo.app found it clean: 126 FAQPage blocks, 578 questions, 120 Article
blocks. This keeps it that way.

WHAT FAILS, on every built page except the noindex meta-refresh stubs:
  - a JSON-LD block that does not parse;
  - an FAQPage question whose text is not in the page's visible text;
  - an FAQPage answer whose opening (its first 80 characters) is not in the visible text;
  - an Article, BlogPosting, TechArticle or NewsArticle headline that is in neither the visible text nor the H1;
  - a datePublished or dateModified whose day ("19 October 2026", the form every byline uses) is not on the page.
Visible text is the HTML with script, style, template, noscript and comments removed, entities decoded, whitespace
and curly quotes normalised, compared case-insensitively.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT
ARTICLE_TYPES = ("Article", "BlogPosting", "TechArticle", "NewsArticle")
ANSWER_PREFIX = 80


def norm(x: str) -> str:
    x = html.unescape(re.sub(r"<[^>]+>", " ", x or ""))
    x = x.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", x).strip().lower()


def visible(page: str) -> str:
    page = re.sub(r"<(script|style|template|noscript)\b[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    page = re.sub(r"<!--.*?-->", " ", page, flags=re.S)
    return norm(page)


def blocks(page: str):
    for m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', page, flags=re.S):
        try:
            data = json.loads(m.group(1))
        except ValueError as exc:
            yield {"_error": str(exc)}
            continue
        items = data.get("@graph", [data]) if isinstance(data, dict) else data
        for it in items if isinstance(items, list) else [items]:
            if isinstance(it, dict):
                yield it


def problems(page: str) -> list:
    out = []
    vis = visible(page)
    h1m = re.search(r"<h1\b[^>]*>(.*?)</h1>", page, flags=re.S | re.I)
    h1 = norm(h1m.group(1)) if h1m else ""
    for it in blocks(page):
        if "_error" in it:
            out.append(f"a JSON-LD block does not parse ({it['_error']})")
            continue
        types = it.get("@type")
        types = types if isinstance(types, list) else [types]
        if "FAQPage" in types:
            for q in it.get("mainEntity") or []:
                name = norm(q.get("name"))
                if name and name not in vis:
                    out.append(f"FAQ question not visible on the page: {q.get('name')!r}")
                answer = norm((q.get("acceptedAnswer") or {}).get("text"))
                if answer and answer[:ANSWER_PREFIX] not in vis:
                    out.append(f"FAQ answer not visible on the page: {answer[:60]!r}...")
        if any(t in ARTICLE_TYPES for t in types):
            head = norm(it.get("headline"))
            if head and head != h1 and head not in vis:
                out.append(f"Article headline not on the page: {it.get('headline')!r} (H1 {h1[:60]!r})")
            for key in ("datePublished", "dateModified"):
                value = it.get(key)
                if value:
                    try:
                        d = dt.date.fromisoformat(str(value)[:10])
                    except ValueError:
                        out.append(f"{key} is not a date: {value!r}")
                        continue
                    if f"{d.day} {d.strftime('%B %Y')}".lower() not in vis:
                        out.append(f"{key} {value} is not shown on the page")
    return out


def self_test() -> int:
    good = ("<html><head><script type=\"application/ld+json\">"
            + json.dumps({"@context": "https://schema.org", "@graph": [
                {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": "Is it free?",
                 "acceptedAnswer": {"@type": "Answer", "text": "Yes, the first audit is free."}}]},
                {"@type": "Article", "headline": "A page", "datePublished": "2026-10-19"}]})
            + "</script></head><body><h1>A page</h1><p>Published 19 October 2026</p>"
            "<h3>Is it free?</h3><p>Yes, the first audit is free.</p></body></html>")
    assert problems(good) == [], problems(good)
    hidden_q = good.replace("<h3>Is it free?</h3>", "")
    assert any("question not visible" in p for p in problems(hidden_q)), problems(hidden_q)
    hidden_a = good.replace("<p>Yes, the first audit is free.</p>", "")
    assert any("answer not visible" in p for p in problems(hidden_a)), problems(hidden_a)
    wrong_head = good.replace("<h1>A page</h1>", "<h1>Another page</h1>")
    assert any("headline not on the page" in p for p in problems(wrong_head)), problems(wrong_head)
    wrong_date = good.replace("19 October 2026", "18 October 2026")
    assert any("datePublished" in p for p in problems(wrong_date)), problems(wrong_date)
    broken = good.replace('"@graph"', '"@graph" x')
    assert any("does not parse" in p for p in problems(broken)), problems(broken)
    only_in_script = good.replace("<h3>Is it free?</h3>", "<script>var q='Is it free?'</script>")
    assert any("question not visible" in p for p in problems(only_in_script)), "text inside a script is not visible"
    print("STRUCTURED DATA self-test ok")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    checked = failed = 0
    for f in sorted(SITE.rglob("*.html")):
        if any(part.startswith(("_", ".")) for part in f.relative_to(SITE).parts):
            continue
        page = f.read_text(errors="ignore")
        if 'http-equiv="refresh"' in page or "application/ld+json" not in page:
            continue
        checked += 1
        for p in problems(page):
            failed += 1
            print(f"  FAIL  /{f.parent.relative_to(SITE).as_posix()}/: {p}")
    if failed:
        print(f"STRUCTURED DATA: {failed} problem(s) on {checked} pages with JSON-LD. Markup may only describe what the "
              "reader can see (Google's structured-data guidelines); fix the page or the markup.")
        return 1
    print(f"STRUCTURED DATA ok: {checked} pages; every FAQ question and answer, Article headline and date is on its page")
    return 0


if __name__ == "__main__":
    sys.exit(main())
