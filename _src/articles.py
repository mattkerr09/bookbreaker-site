"""Search answers. build.py supplies the site's shared page shell."""
from __future__ import annotations

from content import FACTS, cell, claim, cta, e, fact, faq, onward, sources, table
from costs import annual_cost, planned_cost
from stats import held_up, season_scores, wilson
from player_article import player_body
from functools import lru_cache
from nfl import TEAM_BY_CODE, count_text, interval
from nfl_players import player_reports
from pages import PLAYER_INDEX, PLAYER_PAGES
from player_data import PLAYER_READ, PLAYER_SOURCES


RIVALS = ('linemate', 'madness', 'dimers')


def app_checklist(x: dict) -> str:
    checklist = [
        [cell('Game count', True), cell('A count beside every rate'), cell('How many played games made this number?')],
        [cell('Range', True), cell('Low and high ends beside the rate'), cell('How much sampling doubt remains?')],
        [cell('Window', True), cell('Last 5, 10, 20 and the season'), cell('Am I reading a recent run or the whole season?')],
        [cell('Context', True), cell('Home or away, and opponent'), cell('Which games did a filter leave out?')],
    ]
    rows = [[fact(r + '-name', 'th'), fact(r + '-price', 'td'), fact(r + '-platform', 'td'),
             fact(r + '-read', 'td')] for r in RIVALS]
    keys = [r + suffix for r in RIVALS for suffix in ('-name', '-price', '-platform', '-read')]
    keys += ['madness-filters', 'madness-free', 'linemate-rating']
    return f'''<h2>Read the denominator first</h2>
<p>A player stats app should let you see which games make up a number. Start with the count. A rate without its games
can hide a small sample, an old season or a filter you forgot was on. Keep the recent view beside the season so those
questions are easy to ask before you make sense of the result.</p>
{table(['Look for', 'What should be visible', 'Question to ask'], checklist, 'A checklist for a player stats view')}
<p>A useful range shows the doubt around an observed share under stated assumptions. It is not another score for the next
game. A useful filter changes the denominator as well as the count of reaches. When you move from all games to home games,
check that both parts of the answer moved with the rows.</p>
<h2>Prices and platforms in the saved reads</h2>
<p>I make BookBreaker. It is in development. This table describes dated rival reads, so it is a starting point for checking
choices rather than a claim about today’s checkout. Missing information stays missing. An App Store listing is not proof
of a Windows version, and a monthly starting price is not a full yearly plan.</p>
{table(['App', 'Stated price', 'Platform evidence', 'Price read at UTC'], rows, 'Rival reads, with no ranking')}
<p>The Dimers row records a sale read. Its end date was not recorded. Do not treat that row as a current offer. A free
download can also have paid plans inside it. Read the plan that includes the stats you need, rather than treating the
download price as the full cost of using every feature.</p>
<h2>Where the available apps are ahead</h2>
{fact('madness-filters')}{fact('madness-free')}{fact('linemate-rating')}
<p>Phone use, an existing rating history and a free tier are real reasons to choose something you can use now. A future
desktop plan does not fill a phone need today. The table records phone platforms where the notes name them. A blank in
the source is a reason to check, rather than a reason to assume a feature is absent.</p>
<h2>The desktop plan</h2>
{claim('filters')}{claim('counts')}{claim('held')}
<p>I would test an app with a question whose answer I can count by hand. Keep the same player, stat, season and threshold
in both views. If they disagree, compare the included dates before comparing the percentages. That check says more about
whether the tool fits your research than a long list of feature names.</p>
{faq([
    ('Which window should I start with?', '<p>Start with the window in your question. If you want recent games, compare them with the season rather than silently switching between the two. A longer window can include older conditions.</p>'),
    ('Can I use BookBreaker on a phone today?', '<p>BookBreaker is in development. There is no download yet.</p>' + claim('desktop')),
    ('Does a range tell me the next result?', '<p>No. It estimates uncertainty about a rate under a statistical model. It does not remove changes in conditions or make the next game certain. Read its assumptions as well as its endpoints.</p>'),
])}
{sources(keys)}
{onward(['free-nba-player-game-logs', 'pay-once-sports-stats-app', 'linemate-alternative'])}'''


def cost_rows() -> list[list[str]]:
    rows = []
    for rival, first, later, label in (
        ('linemate', 'linemate-annual-low', 'linemate-annual-low', 'Lower annual listing'),
        ('linemate', 'linemate-annual-high', 'linemate-annual-high', 'Higher annual listing'),
        ('madness', 'madness-annual', 'madness-annual', 'Pro annual'),
        ('dimers', 'dimers-annual-first', 'dimers-annual-later', 'Dated sale read, then stated renewal'),
    ):
        rows.append([fact(rival + '-name', 'th'), cell(label), fact(first, 'td'),
                     *[cell(annual_cost(FACTS[first]['text'], FACTS[later]['text'], years)) for years in (1, 2, 3)]])
    rows.append([claim('cost-without-updates', 'th'), cell('No later updates'), cell('Included in licence'),
                 *[cell(planned_cost(years, False)) for years in (1, 2, 3)]])
    rows.append([claim('cost-with-updates', 'th'), cell('With later updates'), cell('Included in licence'),
                 *[cell(planned_cost(years, True)) for years in (1, 2, 3)]])
    return rows


def pay_once(x: dict) -> str:
    keys = [r + '-name' for r in RIVALS] + [r + '-price' for r in RIVALS]
    keys += ['linemate-annual-low', 'linemate-annual-high', 'madness-annual', 'dimers-annual-first', 'dimers-annual-later', 'cheapest-annual']
    return f'''<h2>Keep the licence and the updates separate</h2>
{claim('price')}{claim('keep')}
<p>The word “once” needs a clear object. It can refer to the app licence without covering every future season’s data.
I would write down both parts before comparing bills. One question is what you can keep opening. The other is what you
pay to keep receiving fresh games. A plan should answer both in plain words.</p>
{fact('cheapest-annual')}
<h2>One, two and three years worked out</h2>
<p>The table uses the annual amounts in the saved reads. For a steady yearly price, I multiply it by the number of years.
For the dated Dimers sale read, I add the first-year amount to the stated renewal for each later year. The sale end date
was not recorded. These are arithmetic examples from those reads, not current offers.</p>
{table(['App', 'Assumption', 'First annual price', '1 year total', '2 years total', '3 years total'], cost_rows(), 'Costs if the stated annual prices stay fixed')}
<p>The two Linemate rows use the lower and higher annual listings separately. They do not imply that the plans include
the same things. The table does not turn a monthly starting price into an annual plan. Where no yearly amount was read,
there is no invented total. Taxes, future price changes and plan changes are outside this arithmetic.</p>
<h2>The source amounts</h2>
{''.join(fact(r + '-price') for r in RIVALS)}
<p>For the planned desktop rows, the first year includes the licence and its included new games. Each additional year of
new games adds the planned update price. The row without later updates holds the licence cost fixed. That row cannot be
read as a plan for fresh games every season. The difference matters when you choose the time period for your comparison.</p>
<h2>Ask what remains on your computer</h2>
{claim('local')}{claim('offline')}
<p>A low total is useful only if it describes the work you want to do. Before choosing any app, ask what happens to old
results when a paid period ends. Ask whether a log needs another sign-in to open. If the saved source does not answer,
check that point directly rather than filling the gap with an assumption.</p>
<p>I want the planned price to be easy to understand before there is a purchase button. BookBreaker is in development.
There is no download or checkout here. These tables make the proposed payment split visible while the app is still being
built. They cannot establish which available plan fits a particular reader’s needs.</p>
{faq([
    ('Is the yearly data update required?', claim('keep')),
    ('Why not multiply the monthly price by 12?', '<p>That would answer the cost of paying monthly at that price. It would not prove that the rival sells a yearly plan at the same total. This table uses stated annual amounts and leaves unread plans blank.</p>'),
    ('Does the lowest price decide which app to use?', '<p>No. Check the features, device and data you need as well as the bill. Two plans can have different jobs even when their annual totals are close. Read the plan details before choosing.</p>'),
    ('Will old history need an account?', claim('local')),
])}
{sources(keys)}
{onward(['nba-player-stats-app', 'linemate-alternative'])}'''


def linemate(x: dict) -> str:
    keys = ['linemate-name', 'linemate-price', 'linemate-rating', 'linemate-platform', 'cheapest-annual']
    rows = [[cell('Phone use', True), fact('linemate-platform', 'td'), claim('desktop', 'td')],
            [cell('Payment', True), fact('linemate-price', 'td'), claim('price', 'td')],
            [cell('Reader evidence', True), fact('linemate-rating', 'td'), cell('In development, with no app download yet')],
            [cell('Later-games check', True), cell('Not established by the saved read'), claim('held', 'td')]]
    return f'''<h2>Keep the phone question separate</h2>
{fact('linemate-platform')}
<p>If you want to read a player’s numbers on a phone today, start with that need. Moving to a planned desktop app changes
where you work. A computer can suit a longer session with tables open beside one another. It does not solve the same task
as a phone you already have in your hand.</p>
<p>I make BookBreaker, and it is in development. The differences below are plans on this side of the table. A dated read
on the other side is evidence of what was recorded then. Neither should be mistaken for a fresh test of every feature
available today. There is no ranking or winner here.</p>
{table(['Question', 'Linemate saved read', 'BookBreaker plan'], rows, 'A phone app read beside a planned desktop approach')}
<h2>What the price read says</h2>
{fact('cheapest-annual')}
<p>A monthly listing and an annual listing answer different billing questions. Check the plan name and period together.
A lower annual amount is not proof that it includes everything in a higher listing. The saved notes record the price
range without a full feature map for each in-app purchase. I would check that map before comparing a specific plan.</p>
<p>The worked-cost page keeps the lower and higher annual amounts as separate rows. It also separates the planned app
licence from later data updates. That makes the time period visible. It does not assume that either product’s data or
features are the same. A comparison is easier to use when its gaps are left in view.</p>
<h2>What an existing rating history adds</h2>
{fact('linemate-rating')}
<p>That is evidence from people who have already rated an available app. It is a real head start over an app still in
development. A rating is also a different kind of evidence from a checked answer to a stats question. I would use the
rating to decide what to inspect, then check the workflow that matters to me.</p>
<p>The average belongs with its read date and rating count. Do not copy it as though it were measured today. The saved
notes do not establish that every rating concerned the same feature. They also do not replace trying the particular
table or filter you need. A useful comparison leaves room for both kinds of check.</p>
<h2>The planned differences to inspect later</h2>
{claim('local')}{claim('counts')}{claim('held')}
<p>The later-games idea is a separate test of past situations. It needs rules for which spots qualify, how many later
games count, and when to withhold a score. I explain those rules with a worked team-points study. That study is evidence
for the website’s calculation, rather than proof that a finished app has passed a player-log test.</p>
<p>To compare a future card, I would choose a player and a threshold, write the window down, and count the source rows.
Then I would compare the game dates included by each view. That gives any disagreement somewhere concrete to start.
An attractive percentage with no trace back to its rows is harder to check.</p>
{faq([
    ('Can I switch to BookBreaker now?', '<p>Not yet. BookBreaker is in development. There is no download and no launch date. Use an available source or app for the work you need to do today.</p>'),
    ('Is Linemate’s annual listing the cheapest read?', fact('cheapest-annual')),
    ('Has the saved read checked every Linemate feature?', '<p>No. A price and rating read is narrower than a full workflow test. Where the table says a feature was not established, it means the saved notes do not answer that question. It is not a claim that the feature is absent.</p>'),
    ('Where can I check the counting method first?', '<p>Start with the free game-log walkthrough and count one window by hand. Then read the later-games study if you want to see how past spots are chosen without using future results.</p>'),
])}
{sources(keys)}
{onward(['pay-once-sports-stats-app', 'free-nba-player-game-logs', 'did-the-trend-hold-up'])}'''


def free_logs(x: dict) -> str:
    rows = [[cell('Choose a question', True), cell('Player, season, stat and number'), cell('Write it before counting')],
            [cell('Set the window', True), cell('Newest 10 played games'), cell('Keep the dates on the rows')],
            [cell('Mark each row', True), cell('At or above the chosen number'), cell('An equal value counts')],
            [cell('Report the result', True), cell('Marks of played rows'), cell('Keep the count beside any percentage')]]
    return f'''<h2>Start at the league’s page</h2>
{fact('nba-logs', code='nba.com/stats/player/<id>/boxscores-traditional')}
{fact('nfl-logs', code='nfl.com/players/<slug>/stats/logs/')}
<p>These are URL patterns. Replace the player ID or name placeholder with the one for the player you want. The source
notes tested LeBron James for the NBA and Josh Allen for the NFL. A saved read tells you what was checked then; it cannot
promise how a page will load on another day. The free route is to read the league’s page and do the count yourself.</p>
<p>I would start with the raw rows before paying for a more convenient view. It gives you something to compare with an
app’s answer. Keep the player’s name, the season and the chosen stat on your note. A count loses its meaning quickly if
you cannot tell which table it came from.</p>
<h2>Read the last 10 played games by hand</h2>
<p>Put the games in date order. Start at the newest played game and work backward until you have the window you want.
Do not confuse a team’s schedule with the games the player played. Keep fewer rows if that is all you have, and say how
many you counted. Never fill a missing played game with a zero just to finish the window.</p>
{table(['Step', 'What to keep', 'Check'], rows, 'A handwritten last-10 worksheet')}
<p>For each row, compare the selected stat with your number. Make a mark when the stat is equal to or above it. Count the
marks, then count all the rows used. Write the answer as k of n. If you also want a percentage, divide k by n and multiply
by 100. Keep k and n visible after rounding.</p>
<p>Read the column heading again before counting. Points, minutes and another stat are different questions. Keep the
same stat throughout the window. If you change a season or a filter, start the row check again. A result copied from an
earlier view may no longer match what is in front of you.</p>
<h2>A check you can repeat</h2>
<p>Save your written rule with the date you read the page. A second pass should start from the rows, rather than from
your earlier total. Count the marks again without looking at the answer. If the totals disagree, compare the dates and
the threshold rule first. Then compare each included row. That leaves a short path to finding the difference.</p>
<p>The worked example on this site uses Detroit team points from a local NFL schedules file. It cannot answer a player
question. Use the league route above for the player you are researching, and keep the source with your own count.</p>
{claim('player-data')}
<h2>What an app will add</h2>
{claim('threshold')}{claim('counts')}{claim('held')}
<p>The useful part of a saved view is being able to ask the same question again without rebuilding your worksheet.
The cost of doing it by hand is the row work. Before changing that routine, check a future app answer against a count you
already understand. Convenience is easier to judge when the question and the underlying games stay fixed.</p>
<p>A range and a later-games check answer questions beyond the raw total. They need their own rules. A player’s recent
count does not become a forecast just because it is easy to read. I explain the small-sample range and the later-games
method on separate pages so you can inspect each part.</p>
{faq([
    ('Do I need to buy BookBreaker to count a log?', '<p>No. You can read a source table and count its rows by hand. BookBreaker is in development. The free method on this page stands on its own.</p>'),
    ('Should I count a game the player missed?', fact('method-missing')),
    ('Can I copy the percentage without the rows?', '<p>You can write it down, but also keep its game count and window. Without those, you cannot tell what the percentage summarizes or repeat the work when you check it later.</p>'),
    ('Is a team score a player log?', '<p>No. Team scores explain the arithmetic here. To answer a player question, use that player’s own rows for the selected stat and season.</p>'),
])}
{sources(['nba-logs', 'nfl-logs', 'method-missing'])}
{onward(['how-often-did-a-player-clear-a-number', 'nba-player-stats-app', 'is-a-10-game-trend-reliable'])}'''


def counting(x: dict) -> str:
    rows = [[cell("Last 10 played", True), cell(f"{x['last_k']} of {x['last_n']}"),
             cell(f"{x['last_pct']}%"), cell(f"{x['last_lo']}% to {x['last_hi']}%")],
            [cell("2025 regular season", True), cell(f"{x['k']} of {x['n']}"),
             cell(f"{x['pct']}%"), cell(f"{x['lo']}% to {x['hi']}%")]]
    game_rows = [[cell(g["date"], True), cell(g["site"]), cell(g["opponent"]), cell(g["points"]),
                  cell("Yes" if g["points"] >= x["line"] else "No")] for g in x["games"][-10:]]
    return f'''<h2>Make the question precise</h2>
<p>“Clear” can be unclear. Does a game equal to your number count? Here it does. I use “24 or more points” rather than
“over 24.” Write that rule down before looking at the scores. Changing the rule after seeing the answer makes a different
question, even when the words sound close.</p>
<p>Next choose the subject, the stat and the window. A player’s points and a team’s points need separate rows. Use games
played rather than calendar days. A date gap does not create an extra result. If there are not enough played games for
your chosen window, write the count you actually have.</p>
<h2>A team example from Detroit</h2>
<p>This is a team example because the local data file has team scores, with no player logs.
The rule here is Detroit Lions points at or above {x['line']} in the {x['season']} regular season. Postseason games
are left out. Games are sorted by date, then game ID. The last {x['last_n']} played games are taken from that ordered list.</p>
{table(['Window', 'Reached the number', 'Rate', 'Wilson 95% range'], rows, 'Detroit points at or above ' + str(x['line']))}
<p>The recent count is {x['last_k']} of {x['last_n']}. The season count is {x['k']} of {x['n']}. Neither replaces the other.
The recent view answers a shorter question. The season view includes earlier games too. Both use the same threshold and
the same rule for an equal score. The range describes sampling uncertainty, under a model with a steady underlying rate.</p>
<h2>Count the rows yourself</h2>
<p>Here are the recent rows used in the first line. Read down the points column and mark each score that reaches the
number. Count the yes marks. Then count every row, including the no marks. That second count is the denominator. Do not
leave out a low score because it looks unusual.</p>
{table(['Game date', 'Home or away', 'Opponent code', 'Points', '24 or more?'], game_rows, 'The last 10 Detroit regular-season games')}
<p>To turn the count into a percentage, divide the yes count by the row count and multiply by 100. Round at the end.
Keep the unrounded count beside it. A rounded percentage alone can hide the difference between a short run and a much
longer record. It can also hide that a filter removed games from your sample.</p>
<h2>Make a fair comparison</h2>
<p>If you split home and away, start again with the filtered rows. Do not keep the full-season denominator after removing
away games. If you change the threshold, count the marks again. Keep a note of the date, season and filter so someone else
can repeat the same work. That is more useful than a number with no trail back to its games.</p>
{claim('threshold')}{claim('filters')}{claim('counts')}
{claim('player-data')}
<p>The table above is a calculation made for this page, rather than a screen from a working app. I would use the same
written question to check a future player card against its source rows. A team example explains the counting rule. It
does not establish a player’s rate.</p>
{faq([
    ('Does exactly the chosen number count?', '<p>Yes, for the rule on this page. “At or above” includes equality. If you want a strict greater-than rule, write that down and recount. Do not mix the two rules in one table.</p>'),
    ('What if the player missed a game?', fact('method-missing')),
    ('Does this tell me what happens next?', '<p>No. It describes the games in the stated window. You can study later games separately, but this count alone cannot promise another result. A range helps show the doubt left by a short sample.</p>'),
])}
{sources(['method-missing'])}
{onward(['free-nba-player-game-logs', 'is-a-10-game-trend-reliable', 'did-the-trend-hold-up'])}'''


def reliability(x: dict) -> str:
    rows = []
    for n in (5, 10, 20):
        k = 3 * n // 5
        lo, hi = wilson(k, n)
        rows.append([cell(f"{k} of {n}", True), cell(f"{round(100 * k / n)}%"),
                     cell(f"{round(100 * lo)}% to {round(100 * hi)}%")])
    return f'''<h2>The same rate can carry different weight</h2>
<p>A short sample can look neat because a percentage is neat. The count behind it is the part to read first. The table
holds the observed share steady and changes how many games it came from. These are calculated counts to explain the
formula, rather than player results. They are not another sample from the NFL data file.</p>
{table(['Count', 'Observed rate', 'Wilson 95% range'], rows, 'The same observed share over 5, 10 and 20 games')}
<p>The wider range leaves more room for the underlying rate. Adding games can narrow that range when the share stays the
same. It does not make the next game certain. A whole season can also mix quite different conditions. More rows help with
sampling doubt; they do not prove that the situation stayed the same.</p>
<h2>How I work out the range</h2>
<p>I use the Wilson score interval. Divide the number of reaches, k, by the games played, n, to get the observed share p.
Use z = 1.96 for the 95% interval. Square z. Add z squared divided by twice n to p, then divide by one plus z squared
divided by n. That gives the adjusted centre.</p>
<p>For the half width, take the square root of p times one minus p divided by n, plus z squared divided by four times n
squared. Multiply that root by z, then divide by one plus z squared divided by n. Subtract the half width from the centre
for the low end. Add it for the high end. The table rounds both ends to whole percentages after doing the calculation.</p>
<p>This model treats games as separate trials with a common underlying rate. Real games may not fit that assumption.
Related opponents, changed roles and different conditions can matter. A 95% interval is a method that would cover the
fixed rate in about 95% of repeated samples under that model. It is not a 95% promise about the next game.</p>
<h2>Detroit puts the range in context</h2>
<p>In the local file, Detroit reached {x['line']} or more points in {x['k']} of {x['n']} games in its {x['season']}
regular season. That is {x['pct']}% after rounding. Its Wilson range runs from {x['lo']}% to {x['hi']}%.
This example uses team points. For players, the NFL streak study counts what came next.</p>
{claim('player-data')}
<p>A large-looking season percentage can therefore sit beside a wide interval. Read both. I would also inspect the dated
rows before trying to explain the count. The calculation tells you how much sampling doubt remains under its assumptions.
It does not tell you why those scores happened.</p>
<h2>Choose the window before the result</h2>
<p>Use a short window to ask about a recent stretch. Use the season to ask about the season. Put them next to one another
if both questions matter. Moving between windows until one looks striking gives you a different sort of search. A range
around that chosen result does not account for every other result you looked at along the way.</p>
{claim('counts')}{claim('filters')}
<p>I want the count visible at the moment someone reads a rate. A reader should not have to hunt through another screen
to see whether the number came from a short run. The table here shows the arithmetic behind that choice while the app is
in development.</p>
{faq([
    ('Are 20 games always enough?', '<p>No fixed window settles every question. A longer window can contain older conditions. Check what those games represent as well as how many there are. A narrower range still rests on the model used to make it.</p>'),
    ('Does a wide range make the count wrong?', '<p>No. The count can be exact for those games while the underlying rate remains uncertain. Those are different statements. Keep the observed count and the estimated range together.</p>'),
    ('Can a later-games check remove the doubt?', '<p>It adds evidence from another period. It still needs its own count, range and clear rules for choosing past spots. Later results must not decide which earlier spots get into the study.</p>'),
])}
{sources([])}
{onward(['how-often-did-a-player-clear-a-number', 'did-the-trend-hold-up'])}'''


def later(x: dict) -> str:
    teams = season_scores()
    results = held_up(teams)
    rows = []
    for result in results:
        score = 'Too few past spots to tell' if result['too_few'] else f"{result['k']} of {result['n']} · {result['pct']}%"
        interval = 'No score' if result['too_few'] else f"{result['lo']}% to {result['hi']}%"
        rows.append([cell(result['band'], True), cell(result['spots']), cell(result['n']), cell(score), cell(interval)])
    method_ids = ['method-trend', 'method-bands', 'method-spots', 'method-horizon', 'method-pool',
                  'method-missing', 'method-corrections', 'method-type']
    return f'''<h2>A test that starts in the past</h2>
<p>A recent rate describes the games that made it. A later-games study asks another question: after a similar past rate,
what followed? I keep those questions separate. If later results help choose an earlier spot, the study has already seen
its answer. That can make a tidy table without making a fair test.</p>
{claim('held')}
<h2>The planned method</h2>
{fact('method-trend')}{fact('method-bands')}{fact('method-spots')}{fact('method-horizon')}{fact('method-pool')}
<p>The score counts threshold reaches in later games. It does not ask whether a later rate stayed inside the earlier band.
Those are different outcomes. The band chooses the past situations to inspect; the following games supply the outcome.</p>
<h2>One season of team scores</h2>
<p>For this worked study I use all {len(teams)} NFL teams in the {x['season']} regular season from the local schedules
file. The threshold is {x['line']} or more team points. The window is the last 10 played games, ending at each spot.
The horizon is the next 5 played games. Postseason games are excluded. This is one season of team scores, with no player
data.</p>
{claim('player-data')}
<p>This study is narrower than the planned method’s two-season search. No earlier season is joined to this calculation.
A team needs a full window before its first eligible spot. I run each band as a separate question for each team. Once a
spot is selected, I skip ahead until its horizon has passed before selecting another spot for that same band.</p>
{table(['Past rate band', 'Spots with later games', 'Later games', 'Reached 24 or more', 'Wilson 95% range'], rows, 'Later team points after a last-10 rate, 2025 regular season')}
<p>The spots column counts selected spots with at least one later game. A spot at the final game has no later result to
add. Near the end, every available later game counts, even if the full horizon is not available. I pool reaches and games
across teams, rather than taking an average of team percentages.</p>
<p>No future game repeats within a team’s calculation for one band. A game can appear in more than one row because the
bands are studied independently. Do not add the rows together as though they were a fresh set of distinct games. Teams
can also play one another, so these results are not fully independent trials.</p>
<h2>What this study can support</h2>
<p>Read the counts before comparing the rounded rates. A higher starting band does not require a higher later rate.
The table reports what this file gives under these rules. I have not searched thresholds to find a pleasing order. The
Wilson ranges are the same binomial calculation used elsewhere on this site, with the same limits when games are related.</p>
<p>This is descriptive evidence from a fixed season, not a forecast check on a new season. Team points cannot establish
how player points behave. A useful next check would hold the rules fixed and use another period. It would still need its
own source rows and counts.</p>
{fact('method-missing')}{fact('method-corrections')}{fact('method-type')}
{faq([
    ('Can changing a later score create an earlier spot?', '<p>It must not. A spot uses the window ending at that game. Tests change every later score and check that the earlier selection stays the same. The later outcome may change, which is expected.</p>'),
    ('What happens with fewer than 15 later games?', '<p>The page withholds the rate and range and says “too few past spots to tell.” The later-game count remains visible. A zero count is not a score of zero.</p>'),
    ('Is this the app running?', '<p>No. This table is built from the local team-scores file by the website generator. The app is still in development. The method and the source are stated so this page can be checked before a desktop build exists.</p>'),
])}
{sources(method_ids)}
{onward(['is-a-10-game-trend-reliable', 'how-often-did-a-player-clear-a-number'])}'''


WINDOWS_PLAYER = 'nfl-player-stats/amon-ra-st-brown'


@lru_cache(maxsize=1)
def windows_example() -> tuple:
    """One player's 2025 log, from the same reports the NFL player pages use."""
    p = next(p for p in PLAYER_PAGES if p['slug'] == WINDOWS_PLAYER)
    return p, player_reports(players=[p])[p['player_id']]


def windows(x: dict) -> str:
    p, r = windows_example()
    t, last, season = r['threshold'], r['last'], r['season']
    stat = p['stat'].replace('_', ' ')
    steps = [[cell('Keep one player', True), cell('Filter player_display_name to one name and season_type to REG'), cell('Regular-season rows only')],
             [cell('Put the weeks in order', True), cell('Sort by week, oldest first'), cell('The newest games end the list')],
             [cell('Choose one column', True), cell('passing_yards, rushing_yards or receiving_yards'), cell('One stat per count')],
             [cell('Count reaches', True), cell(f'=COUNTIF(range,">={t}") over the newest 10 rows'), cell('This gives k')],
             [cell('Count rows', True), cell('=COUNT(range) over the same rows'), cell('This gives n')]]
    game_rows = [[cell(f"Week {g['week']}", True), cell(g['date']), cell(TEAM_BY_CODE[g['opponent']]['name']),
                  cell(g['yards']), cell('Yes' if g['yards'] >= t else 'No')] for g in r['games'][-10:]]
    rivals = ['linemate-platform', 'madness-platform', 'dimers-platform']
    csv_li = [f'<li><a href="{e(PLAYER_SOURCES[1])}">nflverse weekly player statistics, 2025 CSV</a>. Read {PLAYER_READ}.</li>']
    return f'''<h2>Two league tables that open in a browser</h2>
{fact('nba-logs', code='nba.com/stats/player/<id>/boxscores-traditional')}
{fact('nfl-logs', code='nfl.com/players/<slug>/stats/logs/')}
<p>Chrome, Firefox and Microsoft’s own browser all run on Windows, so a PC can read both tables with nothing extra installed. Swap the
placeholder in each pattern for the player you want. Each table lists a player’s games one row at a time, which is all
a hand count needs. Write the date you read the page beside your note, because a league table can change after a stat
correction.</p>
<h2>Count NFL games in a spreadsheet</h2>
<p>For the NFL there is a second free route. The nflverse project publishes weekly player statistics as CSV files on
GitHub. Excel and LibreOffice Calc both open a CSV on Windows. One file holds every player and week of a season, so a few
filters turn it into a game log you control.</p>
{table(['Step', 'What to do', 'Result'], steps, 'Counting one player in the nflverse weekly CSV')}
<p>A row in this file comes from recorded plays. If a player was active but recorded nothing in a game, that week may be
missing. Compare your row count with the league’s game log before you trust n. The file is shared under CC BY 4.0, so
credit nflverse when you pass a table along. The Sources section below shows the credit line this site uses.</p>
<h2>A worked count: {e(p['name'])}, 2025</h2>
<p>Here is the same count done from the site’s copy of that file. The mark is {t} {stat}, the one on his
<a href="/{p['slug']}/">player page</a>. A game equal to the mark counts as a reach. The rows are his newest
{last['n']} played games of the 2025 regular season.</p>
{table(['Week', 'Date', 'Opponent', stat.capitalize(), f'{t} or more?'], game_rows, f"{p['name']}, last {last['n']} played games of 2025")}
<p>Read down the last column. He reached {t} yards in {last['k']} of those {last['n']} games, with a Wilson 95% range
of {interval(last)}. Across all {len(r['games'])} games he played that season, the count was {count_text(season)}, with
a range of {interval(season)}. The short window and the season answer different questions, so keep both counts in view.</p>
<p>The <a href="/{PLAYER_INDEX['slug']}/">NFL player stats pages</a> repeat this layout for {len(PLAYER_PAGES)} players,
with splits and a later-games check. They are ordinary web pages, so they work in any Windows browser. This site has no
NBA player tables. For an NBA player, the league’s own game log and a hand count remain the route.</p>
<h2>Phones, browsers and a computer</h2>
{''.join(fact(k) for k in rivals)}
<p>Two of those reads name a phone app. The Dimers read also lists web, so a browser on a PC can reach it. None of the
saved reads records a Windows install, which is a gap in the notes rather than proof that one is missing. The plan here
is a computer app. It does not meet a phone need today.</p>
<h2>What the planned desktop app adds</h2>
{claim('desktop')}{claim('leagues')}{claim('counts')}{claim('filters')}{claim('held')}{claim('price')}
<p>The spreadsheet steps above are the routine the app is meant to replace. That makes them a fair test for any tool,
this one included. Run one count by hand, then compare it with the tool’s answer for the same player, stat, window and
mark. If the two disagree, compare the dates of the included games first.</p>
{faq([
    ('Does the NBA game log need an install on Windows?', '<p>No. It is a web page, read in a browser. The saved notes record a browser test of the table and its URL pattern.</p>'),
    ('Can I get BookBreaker for Windows now?', '<p>Not yet. BookBreaker is in development. There is no download and no launch date.</p>' + claim('desktop')),
    ('Can I share a table made from the nflverse file?', '<p>The data is licensed CC BY 4.0, which allows sharing and adapting with credit. Read the licence itself for the full terms before you publish anything.</p>'),
    ('Why does this site show NFL players only?', '<p>Its player tables come from the public nflverse NFL files. No NBA file of that kind is part of this site’s build, so NBA counts here are by hand.</p>'),
])}
{sources(['nba-logs', 'nfl-logs', *rivals], csv_li)}
{onward(['free-nba-player-game-logs', 'how-often-did-a-player-clear-a-number', 'sports-stats-app-no-account'])}'''


def no_account(x: dict) -> str:
    parts = [[cell('Saved views and typed numbers', True), cell('A file on your own disk'), cell('Nothing, unless the app syncs it')],
             [cell('The stats themselves', True), cell('The last downloaded copy'), cell('A request each time new games arrive')],
             [cell('A paid licence', True), cell('A key or receipt on the computer'), cell('Whatever the licence check sends')],
             [cell('Crash reports and usage counts', True), cell('Varies by app'), cell('Only if the app collects them')]]
    checks = [[cell('Sign-in screen', True), cell('Install the app and open it fresh'), cell('Whether a sign-up step comes before any numbers')],
              [cell('Privacy page', True), cell('Search it for account, email, sync, cloud and third parties'), cell('What the maker says it collects')],
              [cell('Offline test', True), cell('Turn off Wi-Fi, then open a saved view'), cell('Whether your history and data are local')]]
    rows = [[fact(r + '-name', 'th'), fact(r + '-platform', 'td'), fact(r + '-read', 'td'), cell('Not recorded')]
            for r in RIVALS]
    keys = [r + suffix for r in RIVALS for suffix in ('-name', '-platform', '-read')]
    return f'''<h2>What “no account” means</h2>
<p>An account is a record about you kept on the maker’s server. It usually holds an email address, a password and the
settings tied to them. A stats app with no account skips that record. You open it and read numbers without signing up
first. That is a narrower promise than “never goes online,” because new games still have to arrive from somewhere.</p>
<p>History is the other half of the question. Saved views, the players you follow and the numbers you typed can live in a
sync service or in a file on your disk. With no account there is nowhere to sync them, so they stay on the computer that
made them. The trade is that backups become your job.</p>
{claim('local')}
<h2>What stays on the computer, and what still travels</h2>
<p>The table describes local stats apps in general. It is a map of where to look, rather than a description of any one
product.</p>
{table(['Part of a local stats app', 'Where it usually lives', 'What crosses the network'], parts, 'What a local stats app keeps and sends')}
<p>A download is still a contact with a server. That server sees an internet address and the time of the request, as any
web page does. So “no account” and “sends nothing” are separate claims, and each one deserves its own question. Besides
new games, a licence check is the usual reason a paid local app makes contact.</p>
{claim('privacy')}{claim('offline')}
<h2>Three checks you can run on any app</h2>
{table(['Check', 'How', 'What it tells you'], checks, 'Checking a no-account claim yourself')}
<p>The offline test is the strongest of the three. If a saved view opens with the network off, the data and your history
are on the machine. To see the files, look in the AppData folder inside your user folder on Windows, or in Library,
Application Support, in your home folder on a Mac. Copy that folder before you reinstall or move to a new computer. With
no account, nothing restores it for you.</p>
<h2>What the saved rival reads record</h2>
<p>These reads were taken for prices and platforms. They do not say whether each app asks for an account, so that column
is left as a gap. A blank means the notes are silent, not that an account is or is not required.</p>
{table(['App', 'Platform evidence', 'Read at UTC', 'Account rule in the saved read'], rows, 'Rival reads, with no ranking')}
<h2>The planned approach</h2>
{claim('keep')}{claim('price')}
<p>A one-time licence fits a no-account design, because a key can be checked without a profile behind it. When the
privacy details appear, the licence check is the part to read closely. This website is separate from the app. It counts
visits with Plausible, which sets no cookies, and the <a href="/privacy/">privacy page</a> says what it records.</p>
{faq([
    ('Can I try BookBreaker without an account now?', '<p>Not yet. BookBreaker is in development. There is no download and no launch date.</p>' + claim('local')),
    ('Does no account mean the app never goes online?', '<p>No. New games have to be downloaded. A local app can still read the last file it received while the network is off.</p>' + claim('offline')),
    ('What happens to my history on a new computer?', '<p>With no account, nothing copies it across for you. Move the app’s data folder yourself, or use an export if the app offers one.</p>'),
    ('What does a licence check send?', claim('privacy')),
])}
{sources(keys)}
{onward(['pay-once-sports-stats-app', 'linemate-alternative', 'nfl-nba-player-stats-on-windows'])}'''


ARTICLE_BODIES = {
    'nba-player-stats-app': app_checklist,
    'free-nba-player-game-logs': free_logs,
    'pay-once-sports-stats-app': pay_once,
    'linemate-alternative': linemate,
    'how-often-did-a-player-clear-a-number': counting,
    'is-a-10-game-trend-reliable': reliability,
    'did-the-trend-hold-up': later,
    'does-a-player-streak-hold-up': player_body,
    'nfl-nba-player-stats-on-windows': windows,
    'sports-stats-app-no-account': no_account,
}
