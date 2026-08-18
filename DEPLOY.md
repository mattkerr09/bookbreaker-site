# Deploying bookbreaker.bet

## LIVE as of 2026-08-17

`https://bookbreaker.bet` is serving. Measured, not assumed:

- Pages build reported `built` 135 seconds after the push.
- DNS resolves to all four GitHub Pages addresses.
- **All 51 pages return 200 over https**, checked against the sitemap.
- Certificate issued and **HTTPS is enforced**.
- The homepage serves the engine's own devig figure (57.34%), so what is live
  is a real render and not a cached placeholder.
- `_build/gates.sh` passes: self-test clean, site check clean, 8/8 deliberate
  breaks caught.

Repo: `mattkerr09/bookbreaker-site`, branch `main`, Pages from `/`.

## Publishing a change

```sh
python3 _build/render.py --app-repo "../arb betting aqpp"
./_build/gates.sh          # must print SITE GREEN
git add -A && git commit && git push
# wait for the Pages build to report the pushed commit, THEN:
python3 _build/submit.py
```

The order matters. `submit.py` refuses to run if the live site is not serving
the pushed content, because a rejected batch that looks like a success is worse
than not running — and it cannot tell "not deployed yet" from "broken", so give
the deploy time to finish.

## Search engines

**Done automatically.** IndexNow reaches Bing, Yandex, Seznam and Naver in one
POST. Both endpoints accepted all 33 URLs on the first submission
(`api.indexnow.org` 202, `bing.com/indexnow` 200) and every batch since, most
recently all 51 after the calculator and competitor clusters landed. Re-run `_build/submit.py` after every
content change.

`submit.py` refuses to run unless the live site already serves the key file
IndexNow verifies ownership with. That refusal is the point: a submission fired
before the Pages build finishes is rejected for a reason nobody sees, and at the
shell it looks exactly like a successful run. Proven before the first push — a
dry run against the not-yet-deployed key returned 404 and the script declined.

## Still to do

1. **Google Search Console.** Google dropped its sitemap ping in 2023, so the
   sitemap has to be submitted through the account, which is yours. IndexNow
   does not cover it and the script says so rather than implying four engines
   are five.

Note that `mattkerr09.github.io/bookbreaker-site/` will now 404 or redirect.
Once `CNAME` exists Pages serves the custom domain only. That is expected.

## Why the pages have no hand-written numbers

`render.py` imports `overlay_engine` and runs it, writing every figure it will
display to `_build/measured.json`. `check.py` fails the build if a number
appears on a page and not in that file.

The product's whole argument is that other tools print numbers more certain
than they are. A site asserting its own figures by hand would be making exactly
the mistake it sells against — and that is not hypothetical: a sibling project
published a cost table labelled "measured on a real run" from a run that never
happened, and it propagated into a billing page.

The one carve-out is a competitor's price, which cannot come out of our engine.
Those are permitted only inside a table row carrying both a date and an
explicit source link, and the carve-out is scoped to the row so an unsourced
claim beside it is still caught.

## Visual work is not verified by the gates

`_build/gates.sh` checks that the site is HONEST: every figure traceable to
`measured.json`, every competitor claim dated and sourced, every link real,
every citation resolving, duplicates under the ratchet. **None of it looks at
the page.** GREEN means "not lying". It has never meant "good".

That distinction was lost three times, each time by reading a green gate as
completion:

- A data plate whose CSS classes did not exist. It drew nothing. Green,
  because geometry lives in a `style` attribute `check.py` strips.
- The fill panel shipped in app 0.1.2 without ever being rendered. Green,
  because `cargo test` proves the shell spawns the engine and pytest proves
  the arithmetic, and the window sits between them.
- A hero headline set at 83px inside a 496px column, breaking into three
  pieces. Green, because nothing measures a line break.

**The rule: visual changes are done when they have been LOOKED AT.** Not when
the gate passes. At minimum, before calling any visual work finished:

    python3 -m http.server 8899        # then look at:
      /                                the home page, at 1440 AND at 375
      /guides/what-is-arbitrage-betting/    a leaf page
      /sportsbooks/ny/                 a generated page
      /download/                       the page that carries the CTA

in both colour schemes. A page type you did not open is a page type you did
not check, and "the gate is green" is not evidence about any of them.

### And read the comment before overriding the rule

The 83px headline was worse than a mistake: there was already a rule at that
breakpoint, carrying the comment *"72px broke the headline into four pieces.
Sized to land in two."* A later rule in the same stylesheet overrode it and
reintroduced exactly the documented bug. The stylesheet is long and append-only
edits land last, which means **appending silently wins over every considered
rule above it.** Before adding a rule for something that already has one,
search for it and read why it says what it says.
