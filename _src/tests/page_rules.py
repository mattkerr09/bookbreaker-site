"""Standard-library HTML checks, also exercised with deliberately broken copies."""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser

from pages import SEARCH_PAGES


class Node:
    def __init__(self, tag: str, attrs: dict | None = None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list = []

    def text(self, skip_claims: bool = False) -> str:
        if skip_claims and 'data-claim' in self.attrs:
            return ''
        return ' '.join(c.text(skip_claims) if isinstance(c, Node) else c for c in self.children)

    def all(self, tag: str | None = None, attr: str | None = None) -> list[Node]:
        found = [self] if (tag is None or self.tag == tag) and (attr is None or attr in self.attrs) else []
        for child in self.children:
            if isinstance(child, Node):
                found.extend(child.all(tag, attr))
        return found

    def classes(self, name: str) -> list[Node]:
        return [n for n in self.all() if name in n.attrs.get('class', '').split()]


class Document(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.root = Node('document')
        self.stack = [self.root]
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'):
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def words(text: str) -> list[str]:
    return re.findall(r"\b\w+(?:['’]\w+)*\b", text.lower())


def shingles(source: str) -> set[tuple[str, ...]]:
    parts = words(Document(source).root.all('main')[0].text())
    return {tuple(parts[i:i + 5]) for i in range(len(parts) - 4)}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a or b else 1.0


def article_issues(source: str, config: dict) -> list[str]:
    doc = Document(source).root
    errors = []
    want = lambda condition, label: errors.append(label) if not condition else None
    url = f'https://bookbreaker.bet/{config["slug"]}/'
    titles = doc.all('head')[0].all('title') if doc.all('head') else []
    want(len(titles) == 1 and clean(titles[0].text()) == config['title'], 'title')
    metas = doc.all('meta')
    get_meta = lambda key, value: [m.attrs.get('content', '') for m in metas if m.attrs.get(key) == value]
    want(get_meta('name', 'description') == [config['description']], 'description')
    want([n.attrs.get('href') for n in doc.all('link') if n.attrs.get('rel') == 'canonical'] == [url], 'canonical')
    for key, value in (('type', 'article'), ('title', config['title']), ('description', config['description']), ('url', url), ('site_name', 'BookBreaker')):
        want(get_meta('property', 'og:' + key) == [value], 'og:' + key)
    want(len([s for s in doc.all('script') if s.attrs.get('src') == 'https://plausible.io/js/script.js'
              and s.attrs.get('data-domain') == 'bookbreaker.bet' and 'defer' in s.attrs]) == 1, 'analytics')
    scripts = [s for s in doc.all('script') if s.attrs.get('type') == 'application/ld+json']
    try:
        schemas = [json.loads(s.text()) for s in scripts]
        want(len(schemas) == 1 and schemas[0]['@type'] == 'Article'
             and schemas[0]['author'] == {'@type': 'Person', 'name': 'Matthew Kerr'}
             and schemas[0]['datePublished'] == schemas[0]['dateModified'] == '2026-11-21'
             and schemas[0]['mainEntityOfPage'] == url and schemas[0]['headline'] == config['title'], 'schema')
    except (ValueError, KeyError, TypeError):
        errors.append('schema')
    mains = doc.all('main')
    if len(mains) != 1:
        return errors + ['main']
    main = mains[0]
    want(len(doc.all('h1')) == 1 and clean(doc.all('h1')[0].text()) == config['title'], 'h1')
    paragraphs = main.all('p')
    want(bool(paragraphs) and 40 <= len(words(paragraphs[0].text())) <= 70, 'answer length')
    want(bool(paragraphs) and clean(paragraphs[0].text()) == config['answer'], 'answer text')
    want('Checked 21 November 2026 · By Matthew Kerr, who makes BookBreaker' in clean(main.text()), 'byline')
    count = len(words(main.text()))
    want(600 <= count <= 1400, 'main length')
    bodies = main.classes('search-body')
    want(len(bodies) == 1 and 600 <= len(words(bodies[0].text())) <= 1200, 'body length')
    heroes = main.classes('search-hero')
    want(len(heroes) == 1 and len(heroes[0].classes('development')) == 1, 'early app')
    want(bool(main.all('table') or main.all('svg')), 'visual')
    faqs = main.classes('search-faq')
    want(len(faqs) == 1 and 3 <= len(faqs[0].all('details')) <= 6
         and len(faqs[0].all('summary')) == len(faqs[0].all('details')), 'faq')
    sources = main.classes('sources')
    want(len(sources) == 1 and [clean(h.text()) for h in sources[0].all('h2')] == ['Sources']
         and bool(sources[0].all('li')), 'sources')
    links = {a.attrs.get('href') for a in (bodies[0].all('a') if bodies else [])}
    own = {f'/{p["slug"]}/' for p in SEARCH_PAGES}
    want(len((links & own) - {f'/{config["slug"]}/'}) >= 2, 'onward')
    return errors


def registry_issues(source: str, facts: dict, claims: dict) -> list[str]:
    doc = Document(source).root
    errors = []
    main = doc.all('main')[0]
    source_nodes = main.classes('sources')
    source_text = clean(' '.join(s.text() for s in source_nodes))
    source_links = {a.attrs.get('href') for s in source_nodes for a in s.all('a')}
    for node in doc.all(attr='data-fact'):
        key = node.attrs['data-fact']
        entry = facts.get(key)
        if not entry:
            errors.append('unknown fact')
            continue
        text = ''.join(c.text() if isinstance(c, Node) else c for c in node.children)
        if clean(text) != entry['text']:
            errors.append('fact text')
        if entry['source'].startswith('https://') and entry['source'] not in source_links:
            errors.append('fact source')
        if not entry['source'].startswith('https://') and entry['source'] not in source_text:
            errors.append('fact source')
        if entry['readAt'] not in source_text:
            errors.append('fact date')
    for node in doc.all(attr='data-claim'):
        entry = claims.get(node.attrs['data-claim'])
        if not entry:
            errors.append('unknown claim')
            continue
        coming = node.classes('coming')
        texts = node.classes('claim-text')
        if len(coming) != 1 or clean(coming[0].text()).lower() != 'coming' or any(
                k in coming[0].attrs for k in ('hidden', 'style', 'aria-hidden')):
            errors.append('coming label')
        if len(texts) != 1 or clean(texts[0].text()) != entry['text']:
            errors.append('claim text')
        if entry['status'] != 'planned' or not re.search(r'\bwill\b', entry['text'], re.I):
            errors.append('claim status')
    unclaimed = clean(main.text(skip_claims=True))
    # Narrow by design: explicit product name plus common present-tense verbs.
    # Pronouns, implied subjects, unusual verbs, and text inside pictures need review.
    if re.search(r'\bBookBreaker\s+(?:shows|keeps|works|offers|uses|supports|covers|checks|runs|downloads|has|needs|lets|gives|puts|stores|requires|provides|displays|computes)\b', unclaimed, re.I):
        errors.append('present action')
    return errors
