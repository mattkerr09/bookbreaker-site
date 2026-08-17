# Deploying bookbreaker.bet

## State as of 2026-08-17

Local scaffold only. **Nothing has been pushed and no DNS has been touched** —
creating the repo, publishing and pointing the domain are outward-facing and
irreversible, so they wait for a decision rather than a build loop.

- 3 pages render from the engine at `../arb betting aqpp`.
- `CNAME` set to `bookbreaker.bet`.
- `_build/gates.sh` passes: site check clean, 7/7 deliberate breaks caught.

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

## Still to do, and each needs a decision rather than a commit

1. **Create `mattkerr09/bookbreaker-site`** and push `main`.
2. **Enable GitHub Pages** from `main` at `/`. Once `CNAME` exists Pages serves
   *only* the custom domain — `mattkerr09.github.io/bookbreaker-site/` will 404
   or redirect. That is expected, not a broken build.
3. **Point DNS.** Four A records to GitHub Pages, then wait for the certificate
   and enforce HTTPS.
4. **Write `_build/submit.py`** — IndexNow covers Bing, Yandex, Seznam and
   Naver in one POST. Google dropped its sitemap ping in 2023 and needs the
   Search Console account, which is yours.

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
