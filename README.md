# bookbreaker.bet

The website for BookBreaker, a planned sports statistics app for Mac and Windows. It is in development, with no download or launch date.

- Build: `python3 _src/build.py` writes index.html, privacy/, 404.html, the seven search pages, llms.txt and sitemap.xml. It does not write robots.txt.
- Gate: `python3 _src/check.py` must print SITE GREEN (exit 0) before any commit. It fails on the banned words listed in it, on outbound
  links outside the allowed list, and on anything left from the old product.
- Deploy: GitHub Pages from `main`, with CNAME bookbreaker.bet. A push is live only when Pages reports the build for that
  commit and the live page shows it.

BookBreaker will show statistics and trends. The site for the old product is in this repo's history at 272aa076; the
reasons it was removed are in ~/ops/research/bookbreaker-site-rewrite-2026-11-20.md.

## Search pages

The page inventory is `_src/pages.py`. The generator, checker and tests use it.

- `/nba-player-stats-app/`: counts, ranges, filters and dated rival reads.
- `/free-nba-player-game-logs/`: the league log route and a manual count.
- `/pay-once-sports-stats-app/`: annual costs beside the planned licence and optional updates.
- `/linemate-alternative/`: phone use, price and rating evidence beside the desktop plan.
- `/how-often-did-a-player-clear-a-number/`: Detroit team points, last 10 and the season.
- `/is-a-10-game-trend-reliable/`: computed Wilson ranges and their limits.
- `/did-the-trend-hold-up/`: a later-games study on the 2025 NFL regular season.

Still coming: every app feature in `_src/data/claims.json`, the desktop app itself, player logs and a real app screen. An OG image is also still coming. The page metadata does not point to an image that does not exist.

Facts live in `_src/data/facts.json`. Rival facts use the exact source URLs and read times from the supplied dated local notes. The named rivals are Linemate, PropsMadness and Dimers Pro. League URL patterns are code text from PLAN-FIXES.md, section 2, with the browser test date. Replace the player placeholders when using them.

The checker adds hosts from http or https fact sources to its allowed list. Hosts absent from both lists still fail. Its banned words and old-path rules are unchanged.

`_src/stats.py` reads the local nflverse file at build time. It computes Detroit counts and all five rows of the later-games study. The study uses 24 or more team points, a last-10 window and the next 5 played games. Bands run separately. Later games do not repeat within a team's calculation for one band, but can appear across bands. The Wilson example table uses constructed counts to explain the formula, not invented player results.

Run `python3 -m unittest discover -s _src/tests -v`. This runs the build and checker as subprocesses, checks the pages and registries, and breaks rules in memory to verify that the tests reject them. It uses Python 3.9 and the standard library, with no network or packages.

The named-action check catches common present-tense verbs after “BookBreaker” outside registered claims. It does not understand every verb, pronouns, implied subjects or words in pictures. A person must still review the copy. Visual checks at 375 and 1280 pixels also remain required; browser access was denied in this workspace.

Go-live order for Claude: re-read every rival fact at its source and save the read time, run the gate and inspect the layouts, then publish, then IndexNow. Nothing in this job publishes or submits URLs.
