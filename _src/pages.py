"""One inventory for the generator, checker and page tests."""
from __future__ import annotations

import json
from pathlib import Path

# The site-wide "Checked" date: every rival price and platform on the site was re-read at its source that day (rule 15).
SITE_CHECKED = "22 November 2026"
SITE_CHECKED_ISO = "2026-11-22"
PUBLISHED_ISO = "2026-11-21"

from player_data import PLAYER_2026_CHECKED, PLAYER_2026_READ, player_catalog, with_2026

SEARCH_PAGES = [
    {"slug": "nba-player-stats-app", "title": "What should an NBA player stats app show?",
     "link_title": "An NBA player stats app checklist",
     "description": "A player stats checklist: game counts, ranges, recent games and context. Dated rival prices and a look at the planned BookBreaker desktop app.",
     "answer": "Start with the game count behind each rate. Then look for a range, recent games beside the season, and filters for home or away and opponent. A single percentage leaves too much out. Choose the device and payment plan that fit how you read stats, after checking what is available today.",
     "note": "Game counts, ranges, filters and dated rival prices."},
    {"slug": "free-nba-player-game-logs", "title": "Where can I read free NBA player game logs?",
     "description": "Start with the league's player game-log page. Learn to count the last 10 games by hand before looking at the planned BookBreaker app.",
     "answer": "Use the league’s own player game-log page first. You can read the played games, choose a stat and count the rows yourself. For a last 10 view, take the newest 10 games the player actually played. Keep the dates and your chosen number beside the count so you can check the result again.",
     "note": "The free league route and a way to read ten games by hand."},
    {"slug": "pay-once-sports-stats-app", "title": "Can I pay once for a sports stats app?",
     "description": "Worked costs over one, two and three years from dated rival reads, beside BookBreaker's planned $39 licence and optional yearly data update.",
     "answer": "Separate the app licence from the cost of fresh games. Paying once can mean keeping the software, while new data still has a yearly fee. Compare both totals over the time you expect to use it. Also check what you can still open if you stop paying for updates, before choosing a plan.",
     "note": "Licence costs and optional data updates over three years."},
    {"slug": "linemate-alternative", "title": "Looking for a Linemate alternative for stats?",
     "description": "Linemate's dated App Store price and rating reads beside BookBreaker's planned desktop approach. Phone use, cost and trend checks are separate choices.",
     "answer": "Begin with how you want to read your stats: on a phone or at a computer. Then compare the payment plan and the evidence beside each trend. A different app is useful when it fits that job. A desktop plan still in development cannot replace something you need to use on your phone today.",
     "note": "Phone use and dated Linemate reads beside a desktop plan."},
    {"slug": "how-often-did-a-player-clear-a-number", "title": "How often did a player clear a number?",
     "description": "Count games at or above your chosen number. A computed Detroit team-points example shows last 10 games beside the full 2025 regular season.",
     "answer": "Choose the number before you count. Mark each played game that reached it, including a game equal to the number. Count those marks as k, and all the played games in your window as n. Read the result as k of n. Keep a season count beside a recent count so the window stays clear.",
     "note": "A Detroit team-points example of counting games at a threshold."},
    {"slug": "is-a-10-game-trend-reliable", "title": "Is a 10-game trend reliable?",
     "description": "Ten games describe ten results. Computed Wilson ranges for 5, 10 and 20 games show why a small sample leaves room for doubt.",
     "answer": "Ten games can describe what just happened, but leave a wide range for the underlying rate. Five games leave even more doubt. Twenty can narrow the range without settling what happens next. Read the count, the range and the game context together. None of them promises that a recent trend will continue.",
     "note": "Wilson ranges explain what a short run of games can tell you."},
    {"slug": "did-the-trend-hold-up", "title": "Did the trend hold up in later games?",
     "description": "A worked NFL team-points study checks later games without using them to choose past spots. Counts and Wilson ranges for all five rate bands.",
     "answer": "To check a trend later, freeze what you knew when you spotted it. Find past points in time with a similar rate, then count what happened in the following games. Keep those later games out of the spot choice. Show the pooled count and its range, and withhold a score when there are too few games.",
     "note": "A reproducible later-games study on one NFL season of team points."},
    {"slug": "does-a-player-streak-hold-up", "title": "Does a player's streak hold up in the next games?",
     "description": "NFL player yards study: an 82% average last-5 rate became 56% in later games, 482 of 860. Counts, Wilson ranges and the 2024 threshold method.",
     "answer": "In this NFL player study, spots showing an 80% or higher last-5 rate averaged 82% in those past games. The later rate was 56%: 482 of 860 games, with a Wilson 95% range of 53% to 59%. The past count was right. It described those games, without settling what came next.",
     "note": "Player yards shown versus later, with numbers fixed from 2024."},
    {"slug": "nfl-nba-player-stats-on-windows", "title": "Is there an NFL and NBA player stats tool for Windows?",
     "link_title": "NFL and NBA player stats on Windows",
     "description": "Read NFL and NBA player game logs on a Windows PC today: league pages, a spreadsheet count from nflverse data, and the planned BookBreaker desktop app.",
     "answer": "Yes, through a web browser today. The NFL and NBA both publish player game logs that open in a browser on a Windows PC. For NFL numbers you can also load the free nflverse weekly file into a spreadsheet and count games yourself. BookBreaker is a planned Mac and Windows app, still in development, with no download yet.",
     "note": "League game logs, a spreadsheet count and a planned desktop app."},
    {"slug": "sports-stats-app-no-account", "title": "Is there a sports stats app with no account?",
     "link_title": "A sports stats app with no account",
     "description": "What no account means for a stats app, what a local app keeps on your computer and still sends, three checks for any app, and the BookBreaker plan.",
     "answer": "Not from this site yet. BookBreaker is planned with no account and with your history kept on your computer, but it is still in development, with no download. For any app that says it needs no account, look for a sign-in screen, read its privacy page, and open it with the internet switched off.",
     "note": "What no account means, what a local app still sends, and how to check."},
]
SEARCH_PATHS = [f"{page['slug']}/index.html" for page in SEARCH_PAGES]
NFL_TEAMS = json.loads((Path(__file__).resolve().parent / 'data/nfl_teams.json').read_text())
NFL_INDEX = {"slug": "nfl-team-scoring", "title": "NFL team scoring stats, 2025 season",
             "description": "Every 2025 regular-season team score, points per game, threshold counts, Wilson ranges and a check of later games for all 32 NFL teams."}
TEAM_PAGES = [dict(team, slug=f"{NFL_INDEX['slug']}/{team['slug']}",
                   title=f"{team['name']} points by game, 2025 season",
                   description=f"{team['name']} 2025 regular-season points by game, last 5 and last 10 counts, home and away splits, Wilson ranges and a later-games check.")
              for team in NFL_TEAMS]
DATA_PAGES = [NFL_INDEX, *TEAM_PAGES]
DATA_PATHS = [f"{page['slug']}/index.html" for page in DATA_PAGES]
PLAYER_INDEX = {"slug": "nfl-player-stats", "title": "NFL player stats by game, 2025 and 2026",
                "description": "NFL player game logs: 2025 passing, rushing and receiving yards, last 10 counts, Wilson ranges, splits, and each player's 2026 games so far.",
                "checked": PLAYER_2026_CHECKED, "modified": PLAYER_2026_READ}
PLAYER_PAGES = with_2026(player_catalog())
PLAYER_DATA_PAGES = [PLAYER_INDEX, *PLAYER_PAGES]
PLAYER_PATHS = [f"{page['slug']}/index.html" for page in PLAYER_DATA_PAGES]
PUBLISHED = ["index.html", "pricing/index.html", "privacy/index.html", "streak-checker/index.html",
             "streak-checker/nfl.json", "streak-checker/checker.js", "404.html", "llms.txt", "robots.txt", "sitemap.xml", "README.md",
             *SEARCH_PATHS, *DATA_PATHS, *PLAYER_PATHS]
