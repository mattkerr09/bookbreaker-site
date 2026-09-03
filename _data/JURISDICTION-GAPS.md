# Jurisdiction facts not yet sourced

Generated 2026-09-02 from `_data/jurisdictions.csv`. Each row below is a fact
the state page CANNOT show, because `jurisdiction_facts()` renders only fields
that were sourced — deliberately, since "a blank is a fact nobody verified, and
it renders as nothing at all rather than as a plausible default".

## Why this is worth filling

similarity-gate reports 11 near-duplicate pairs on this site and every one is a
pair of /sportsbooks/ pages. Measured on two of them, KY and MO: 3,304 and 3,348
characters of visible text, **91.2% identical**, with roughly 300 characters of
genuinely per-state fact. The template is not the problem — it already renders
every sourced field and cites each one. The differentiator is data that has not
been researched yet.

min_age is the trap. It is 21 in almost every US state, which is exactly why it
must not be defaulted: a page asserting an age for a state nobody checked is the
failure this file exists to prevent.

## The queue, with the primary source already on file

- **OR** — missing launch_date, tax_rate, min_age, college_props, retail_venues
  - regulator: Oregon Lottery
  - source: https://www.oregonlottery.org/about/
- **PA** — missing launch_date, tax_rate, min_age, college_props, retail_venues
  - regulator: Pennsylvania Gaming Control Board
  - source: https://gamingcontrolboard.pa.gov/
- **NJ** — missing launch_date, min_age, college_props, retail_venues
  - regulator: New Jersey Division of Gaming Enforcement
  - source: https://www.nj.gov/treasury/taxation/newlegislation.shtml
- **NV** — missing launch_date, min_age, college_props, retail_venues
  - regulator: Nevada Gaming Control Board
  - source: https://www.gaming.nv.gov/divisions/tax-license-division/license-fees-and-tax-rate-schedule/
- **KS** — missing launch_date, college_props, retail_venues
  - regulator: Kansas Racing and Gaming Commission
  - source: https://krgc.kansas.gov/sports-wagering
- **LA** — missing launch_date, min_age, retail_venues
  - regulator: Louisiana Gaming Control Board
  - source: https://legis.la.gov/Legis/Law.aspx?d=1239411
- **WY** — missing tax_rate, min_age, college_props
  - regulator: Wyoming Gaming Commission
  - source: https://gaming.wyo.gov/OSW
- **FL** — missing tax_rate, retail_venues
  - regulator: Florida Gaming Control Commission
  - source: https://www.flsenate.gov/Laws/Statutes/2025/285.710
- **IN** — missing launch_date, retail_venues
  - regulator: Indiana Gaming Commission
  - source: https://www.in.gov/igc/files/sportswagering/Sports-Wagering-FAQs.pdf
- **NY** — missing min_age, retail_venues
  - regulator: New York State Gaming Commission
  - source: https://gaming.ny.gov/sports-wagering
- **OH** — missing college_props, retail_venues
  - regulator: Ohio Casino Control Commission
  - source: https://codes.ohio.gov/ohio-revised-code/section-5753.021
- **TN** — missing tax_rate, college_props
  - regulator: Tennessee Sports Wagering Council
  - source: https://www.tn.gov/swac/about/faqs.html
- **AZ** — missing retail_venues
  - regulator: Arizona Department of Gaming
  - source: https://www.cftc.gov/media/12146/ArizonaDepartmentOfGaming060225/download
- **CT** — missing retail_venues
  - regulator: Connecticut Department of Consumer Protection
  - source: https://portal.ct.gov/gaming/knowledge-base/categories/online-gaming/sports-wagering
- **IL** — missing tax_rate
  - regulator: Illinois Gaming Board
  - source: https://igb.illinois.gov/sports-wagering/sports-reports.html
- **KY** — missing retail_venues
  - regulator: Kentucky Horse Racing and Gaming Corporation
  - source: https://taxanswers.ky.gov/Sales-and-Excise-Taxes/Pages/Sports-Wagering-.aspx
- **MA** — missing launch_date
  - regulator: Massachusetts Gaming Commission
  - source: https://massgaming.com/regulations/revenue/
- **MD** — missing college_props
  - regulator: Maryland Lottery and Gaming Control Commission
  - source: https://www.mdgaming.com/sports-wagering/
- **MI** — missing retail_venues
  - regulator: Michigan Gaming Control Board
  - source: https://www.michigan.gov/mgcb/detroit-casinos/resources/revenues-and-wagering-tax-information
- **NC** — missing college_props
  - regulator: North Carolina State Lottery Commission
  - source: https://ncgaming.gov/faqs-2/
- **VA** — missing retail_venues
  - regulator: Virginia Lottery
  - source: https://law.lis.virginia.gov/vacode/title58.1/chapter40/section58.1-4037/
- **WV** — missing college_props
  - regulator: West Virginia Lottery Commission
  - source: https://code.wvlegislature.gov/29-22D-16/

**47 facts across 22 states.**

Fill a cell only from that state's own regulator or statute, and set
`fetched_at` to the day you read it. A wrong entry here is a confident wrong
claim about somebody's gambling law, which is worse than a blank.
