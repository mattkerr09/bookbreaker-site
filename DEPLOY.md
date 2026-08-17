# Deploying bookbreaker.bet

## LIVE as of 2026-08-17

`https://bookbreaker.bet` is serving. Measured, not assumed:

- Pages build reported `built` 135 seconds after the push.
- DNS resolves to all four GitHub Pages addresses.
- **All 33 pages return 200 over https**, checked against the sitemap.
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

## Still to do

1. **`_build/submit.py`** — IndexNow covers Bing, Yandex, Seznam and Naver in
   one POST. It needs a key file served from the site root, so it is a content
   change as well as a script.
2. **Google Search Console.** Google dropped its sitemap ping in 2023, so the
   sitemap has to be submitted through the account, which is yours.

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
