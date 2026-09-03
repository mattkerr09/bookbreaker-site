# Privacy — UNPUBLISHED DRAFT, needs Matthew

Not deployed. Jekyll skips `_`-prefixed directories, and this is `.md` rather
than `.html` because `_build/render.py` unlinks every `.html` under the site
root that a render did not produce — it ate the first copy of this file.

## Why this exists

The 2026-09-02 audit's recommended next action is "Plausible on
bookbreaker.bet". Right thing to want, wrong thing to do first.

This site has **no privacy page**: `/privacy/`, `/legal/privacy/`, `/legal/`,
`/privacy.html` and `/legal/privacy.html` all return 404. `privacy-gate` passes
today only because the site loads no third party at all — its verdict is
literally "no third-party subresources".

Adding an analytics script would make it track visitors with nothing disclosing
it. That is precisely the incident that gate was written for: crispvideo.app
ran an affiliate tracker for weeks that its privacy policy never mentioned.

A tracker and its disclosure ship together. If they must split, the policy goes
first. So: approve this text, publish it, and Plausible goes in the next commit.

## Draft text

**Privacy**

Bookbreaker is a public website with no accounts, no sign-in and no forms.
There is nothing to fill in, so there is nothing we collect from you directly.

**What is measured.** We use Plausible Analytics to count page views. Plausible
is hosted in the EU, sets no cookies, and does not build a profile of you or
follow you to other sites. It records the page you viewed, the site that
referred you, and coarse details your browser sends anyway: country, device
type and browser. It does not store your IP address. That is the only third
party this site loads.

**What is not measured.** No advertising pixels. No session recording. No
cross-site identifiers. No email collection. No account of any kind.

**The calculators.** Everything you type into a calculator on this site stays in
your browser. It is not sent anywhere, including to us. You can confirm that in
your browser's network tab.

**Contact.** Questions about this page: `<ADDRESS NEEDED>`

## Two things to set before publishing

1. **The contact address.** `contact-gate` requires a legal page to offer a way
   to reach us — "this is the page a dispute cites". I will not invent an
   address for a gambling-adjacent site.
2. **Whether Plausible is actually going in.** If it is not, "What is measured"
   is wrong and this should say the site measures nothing, which is true today.
