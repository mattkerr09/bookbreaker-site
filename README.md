# bookbreaker.bet

The website for BookBreaker, a planned sports statistics app for Mac and Windows. It is in development, with no download or launch date.

- Build: `python3 _src/build.py` writes index.html, privacy/, 404.html, the eight search pages, the 33 NFL scoring pages, the 274 NFL player pages, llms.txt and sitemap.xml. It does not write robots.txt.
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
- `/does-a-player-streak-hold-up/`: NFL player yards shown versus later, with each number fixed from 2024.
- `/nfl-team-scoring/`: a sortable comparison of all 32 teams, linked to each team's 2025 game log.

Still coming: every app feature in `_src/data/claims.json`, the desktop app itself, player logs in the app and a real app screen. An OG image is also still coming. The page metadata does not point to an image that does not exist.

Facts live in `_src/data/facts.json`. Rival facts use the exact source URLs and read times from the supplied dated local notes. The named rivals are Linemate, PropsMadness and Dimers Pro. League URL patterns are code text from PLAN-FIXES.md, section 2, with the browser test date. Replace the player placeholders when using them.

The checker adds hosts from http or https fact sources to its allowed list. Hosts absent from both lists still fail. Its banned words and old-path rules are unchanged.

NFL pages also carry the nflverse credit and a CC BY 4.0 link. The checker reads that licence link's host in the same way as fact-source hosts.

`_src/stats.py` reads the local nflverse file at build time. It computes Detroit counts and all five rows of the later-games study. The study uses 24 or more team points, a last-10 window and the next 5 played games. Bands run separately. Later games do not repeat within a team's calculation for one band, but can appear across bands. The Wilson example table uses constructed counts to explain the formula, not invented player results.

## NFL scoring batch

`_src/data/nfl_teams.json` maps the file's 32 team codes to plain names and slugs. `_src/pages.py` derives the 33 paths for the build, checker and tests. `_src/nfl.py` draws the charts and builds the team tables, trend cards, splits and FAQs.

The schedule CSV entry point is `schedule_rows()` in `_src/stats.py`. It retains only the job's 16 allowed fields, then returns completed regular-season rows for the requested season. No other CSV field is passed to a calculation or page. The source and read date are `NFL_SOURCE` and `NFL_READ` in that file. There is no network step.

Every displayed game log uses the 2025 season. The team's median score, rounded up, sets three thresholds: that number and 7 points either side. Splits use the median threshold. The index uses 24 points for every team, so that column compares the same mark. Home and away are designated sides, including neutral venues.

Only the held-up-later search joins the previous 2024 regular season. It uses the team's final last-10 band, the median threshold and a 5-game horizon. It calls the existing `held_up()` function for one team. Under 15 later games, no score or range is shown. The threshold is chosen from the full 2025 season, so this is a description of stored results, not a test of a threshold chosen before that season. The 2026 season is excluded. January 2026 dates in a 2025 game log still belong to the 2025 season.

Each team links to the two most recently faced distinct division opponents in its displayed log. The table on the index starts in name order and has keyboard-accessible column buttons. It remains readable without JavaScript.

The NFL tests recount every game, trend and split, and independently walk the past spots. Detroit's average and 24-point count are recounted separately. Poison fixtures add fake unknown field values and completed 2026 games, then rebuild all pages and require unchanged output. Every new scoring test also runs against a deliberately broken input, restored in memory afterward. All pairs of team pages must stay below a 0.5 five-word shingle Jaccard score; each team versus every other HTML page must stay below 0.3. These checks use all words in main, including tables.

## Player yards shown versus later

`_src/player_study.py` requests only player_id, position, season, week, season_type, passing_yards, rushing_yards and receiving_yards from the local nflverse weekly player CSVs for 2024 and 2025. No name field is read. The files are in `/Users/matthewkerr/bb-lab/research/nfl/data/nflverse-player-week/`. Source URLs and the 2026-11-21 read date are shared through `_src/player_data.py` and on the page. There is no network step.

`python3 _src/player_study.py` reproduces the research run's output.txt exactly, including every printed count, percentage and range. A frozen copy is in `_src/tests/fixtures/player-study-output.txt`. The study keeps regular-season QB, RB, WR and TE rows, grouped by player and position. At least eight 2024 rows and a 2024 median rounded up to at least 10 yards set eligibility. Rounding comes before the cutoff, so a 9.5-yard median qualifies. Only 2024 sets the number.

Each 2025 spot uses the five or ten played games ending there, including late 2024 when needed. Its outcome contains up to five later 2025 rows. The next spot in the same band is at least six games later, matching the saved run. Games can repeat across bands and windows. Counts are pooled across logs; the shown average gives each spot equal weight. The page reports the 40% shown to 42% later exception in the last-5 table, rather than claiming that every band from 40% up fell.

`_src/player_article.py` builds both tables and one SVG from those results. The new tests check the frozen output, allowlisted reading, 2024-only thresholds, prefix selection, no overlap, partial horizons, no exposed player IDs, table and chart numbers, metadata, links and similarity against every page. Each new check rejects a deliberately broken input and restores it in memory. CSS tests reject old product words, sizes below 12 pixels and text palette contrast below 4.5:1. The new page uses present development wording, including its shared call to action and footer, to avoid future-result language.

Run `python3 -m unittest discover -s _src/tests -v`. This runs the build and checker as subprocesses, checks the pages and registries, and breaks rules in memory to verify that the tests reject them. It uses Python 3.9 and the standard library, with no network or packages.

The named-action check catches common present-tense verbs after “BookBreaker” outside registered claims. It does not understand every verb, pronouns, implied subjects or words in pictures. A person must still review the copy. Visual checks at 375 and 1280 pixels also remain required; browser access was denied in this workspace.

Go-live order for Claude: re-read every rival fact at its source and save the read time, run the gate and inspect the layouts, then publish, then IndexNow. Nothing in this job publishes or submits URLs.

## NFL player pages

`_src/player_data.py` owns the single player CSV boundary, `read_player_rows()`. It selects only the 21 approved fields by column index. The pooled study requests its original eight-field subset. Unknown values are never accessed or passed to calculations. The two source files and their 2026-11-21 read date are named there. Schedule dates, designated sides and division flags still come through `schedule_rows()` with its existing allowlist and source read date.

`_src/pages.py` derives one index and 273 eligible player paths from the local files: 37 QB, 60 RB, 116 WR and 60 TE. Eligibility uses at least 8 recorded 2025 regular-season games and an exact median of at least 10 yards in the position's main stat. No missed game becomes a row or a zero. Slugs use the lowercase display name with punctuation replaced by hyphens; duplicate names gain position, then team. The latest recorded 2025 row supplies the position. Pages name every team in a traded player's 2025 log and appear on each of those team pages.

`_src/nfl_players.py` joins recorded player rows to schedule games by team and game ID, checks week and opponent, and refuses an unmatched or duplicate game. Each player has a position-specific game log, three threshold cards, four splits, a drawn SVG with the exact median line, a measured observation, three personal FAQs and source links. The index has one table per position and the shared method. The home and footer Guides lists link to it. Each team page lists all its eligible players. Player pages link to up to two eligible teammates at their position.

Thresholds use the exact 2025 median rounded upward to a whole yard, multiplied by 0.75, 1 and 1.25. Each is rounded to the nearest 5 yards, with halves upward. Small medians can give the lower and middle cards the same mark. Splits and the individual later check use the middle rounded mark, while the chart line and index median column show the exact median. Every last-10 count shows its real denominator, including logs with only 8 or 9 games.

The individual later check uses the final last-10 band and searches that player's 2024 and 2025 regular-season games with the existing five-game horizon and five-game step from PLAN-FIXES section 1. Only that check uses 2024. The threshold was chosen from the full 2025 season, so it describes stored results rather than testing a number fixed before that season. The separate pooled study keeps its original 2024 threshold and six-game step, and still reproduces its saved output. Of the 273 player pages, 238 have fewer than 15 later games and show “too few past spots to tell” with no score or range.

The player tests verify the eligible set, slug collisions, metadata and every page component, game logs, cards, splits, chart coordinates, all index rows and team links. They independently recount the later spots and three named players, using a second Wilson formula. Synthetic poison columns are guarded against cell access, then the allowed rows reproduce the player pages. Missing games, postseason and 2026 rows, images, advice words and five-word Jaccard limits have separate checks. Each new test also rejects a deliberately broken input patched in memory, then restores it. Will Dissly's recorded name is preserved; the advice-word check removes recorded display names before checking prose.

## Launch redirect kit

The site still uses https://bookbreaker.bet. `_src/build.py` has one `ORIGIN` constant for canonical, OG, sitemap,
llms.txt and JSON-LD URLs. Switch it only in the new site's launch-day build.
The offline redirect generator, CSV contract, account steps and fallback limits are in [`_launch/README.md`](_launch/README.md).
The saved `_launch/bulk-redirects.csv` is for review and later Cloudflare import. Nothing here changes DNS or enables redirects.
