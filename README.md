# bookbreaker.bet

The website for BookBreaker, a sports statistics app for Mac and Windows (NBA, NFL, MLB, NHL), coming 18 December 2026.

- Build: `python3 _src/build.py` writes index.html, privacy/, 404.html, llms.txt, robots.txt and sitemap.xml.
- Gate: `python3 _src/check.py` must print SITE GREEN (exit 0) before any commit. It fails on the banned words listed in it, on outbound
  links outside the allowed list, and on anything left from the old product.
- Deploy: GitHub Pages from `main`, with CNAME bookbreaker.bet. A push is live only when Pages reports the build for that
  commit and the live page shows it.

BookBreaker shows statistics and trends only. The site for the old product is in this repo's history at 272aa076; the
reasons it was removed are in ~/ops/research/bookbreaker-site-rewrite-2026-11-20.md.
