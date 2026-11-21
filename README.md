# bookbreaker.bet

The website for BookBreaker, a planned sports statistics app for Mac and Windows. It is in development, with no download or launch date.

- Build: `python3 _src/build.py` writes index.html, privacy/, 404.html, the seven search pages, the 33 NFL scoring pages, llms.txt and sitemap.xml. It does not write robots.txt.
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
- `/nfl-team-scoring/`: a sortable comparison of all 32 teams, linked to each team's 2025 game log.

Still coming: every app feature in `_src/data/claims.json`, the desktop app itself, player logs and a real app screen. An OG image is also still coming. The page metadata does not point to an image that does not exist.

Facts live in `_src/data/facts.json`. Rival facts use the exact source URLs and read times from the supplied dated local notes. The named rivals are Linemate, PropsMadness and Dimers Pro. League URL patterns are code text from PLAN-FIXES.md, section 2, with the browser test date. Replace the player placeholders when using them.

The checker adds hosts from http or https fact sources to its allowed list. Hosts absent from both lists still fail. Its banned words and old-path rules are unchanged.

`_src/stats.py` reads the local nflverse file at build time. It computes Detroit counts and all five rows of the later-games study. The study uses 24 or more team points, a last-10 window and the next 5 played games. Bands run separately. Later games do not repeat within a team's calculation for one band, but can appear across bands. The Wilson example table uses constructed counts to explain the formula, not invented player results.

## NFL scoring batch

`_src/data/nfl_teams.json` maps the file's 32 team codes to plain names and slugs. `_src/pages.py` derives the 33 paths for the build, checker and tests. `_src/nfl.py` draws the charts and builds the team tables, trend cards, splits and FAQs.

The only CSV entry point is `schedule_rows()` in `_src/stats.py`. It retains only the job's 16 allowed fields, then returns completed regular-season rows for the requested season. No other CSV field is passed to a calculation or page. The source and read date are `NFL_SOURCE` and `NFL_READ` in that file. There is no network step.

Every displayed game log uses the 2025 season. The team's median score, rounded up, sets three thresholds: that number and 7 points either side. Splits use the median threshold. The index uses 24 points for every team, so that column compares the same mark. Home and away are designated sides, including neutral venues.

Only the held-up-later search joins the previous 2024 regular season. It uses the team's final last-10 band, the median threshold and a 5-game horizon. It calls the existing `held_up()` function for one team. Under 15 later games, no score or range is shown. The threshold is chosen from the full 2025 season, so this is a description of stored results, not a test of a threshold chosen before that season. The 2026 season is excluded. January 2026 dates in a 2025 game log still belong to the 2025 season.

Each team links to the two most recently faced distinct division opponents in its displayed log. The table on the index starts in name order and has keyboard-accessible column buttons. It remains readable without JavaScript.

The NFL tests recount every game, trend and split, and independently walk the past spots. Detroit's average and 24-point count are recounted separately. Poison fixtures add fake unknown field values and completed 2026 games, then rebuild all pages and require unchanged output. Every new scoring test also runs against a deliberately broken input, restored in memory afterward. All pairs of team pages must stay below a 0.5 five-word shingle Jaccard score; each team versus every other HTML page must stay below 0.3. These checks use all words in main, including tables.

Run `python3 -m unittest discover -s _src/tests -v`. This runs the build and checker as subprocesses, checks the pages and registries, and breaks rules in memory to verify that the tests reject them. It uses Python 3.9 and the standard library, with no network or packages.

The named-action check catches common present-tense verbs after “BookBreaker” outside registered claims. It does not understand every verb, pronouns, implied subjects or words in pictures. A person must still review the copy. Visual checks at 375 and 1280 pixels also remain required; browser access was denied in this workspace.

Go-live order for Claude: re-read every rival fact at its source and save the read time, run the gate and inspect the layouts, then publish, then IndexNow. Nothing in this job publishes or submits URLs.
