# Launch-day redirect kit

This kit is ready for review. It does not change DNS or the live site.
The build origin is still https://bookbreaker.bet. Keep this checkout and its old-host sitemap for the redirect checks.
Build the new host in a separate checkout on launch day.

## Plan A: one dynamic Redirect Rule

Use Cloudflare's "Redirect a domain" guide:
https://developers.cloudflare.com/fundamentals/manage-domains/redirect-domain/

1. Claude prepares the new site. Matthew approves the launch. Make https://streakgauge.com live with the same paths.
   In that site's `_src/build.py`, change only `ORIGIN` to `https://streakgauge.com` for canonical URLs, OG URLs,
   sitemap URLs, llms.txt links and JSON-LD URLs. Rebuild and review before sending old-host traffic there.
   This kit does not change the current origin. Product name, analytics and other launch changes need their own review.
2. Matthew signs in to Cloudflare and adds the zone for bookbreaker.bet. Copy and check the existing DNS records,
   including any mail records. Keep web records for bookbreaker.bet and www.bookbreaker.bet proxied so Cloudflare
   can answer requests. Check HTTPS coverage for both old hostnames. In this zone, create and enable one
   Single Redirect with these settings:

   - Match all requests to either old hostname with this custom filter expression:
     `(http.host eq "bookbreaker.bet") or (http.host eq "www.bookbreaker.bet")`
   - Type: Dynamic.
   - Target expression: `concat("https://streakgauge.com", http.request.uri.path)`.
   - Status code: 301.
   - Preserve query string: on.

   This rule keeps each path and query string. It covers every path, including paths outside the sitemap.
3. Matthew signs in to Porkbun. Replace the current nameservers, whose names end in ns.porkbun.com, with the
   nameservers Cloudflare assigns to this zone. Wait for Cloudflare to report the zone active.
   Keep the old GitHub Pages content in place while DNS changes reach users.
4. Claude or Matthew runs `python3 _src/redirects.py --verify` from this old-host checkout until it exits 0.
   This command uses the network and is for launch day only. It sends one GET per old URL without following redirects.
   Every response must be 301 with Location exactly equal to the matching Streakgauge URL. A connection error,
   wrong status, wrong Location or missing Location fails the check. Repeat after DNS has settled.
   The 323 checks cover the 320 mapped URLs and these three extra requests:

   - `https://bookbreaker.bet/no-such-page/` must go to `https://streakgauge.com/no-such-page/`.
   - `https://bookbreaker.bet/llms.txt?x=1` must go to `https://streakgauge.com/llms.txt?x=1`.
   - `https://www.bookbreaker.bet/no-such-page/` must go to `https://streakgauge.com/no-such-page/`.

   These probes check an unlisted path, query preservation and the www hostname.
5. Matthew signs in to Bing Webmaster Tools and Google Search Console. Verify both hosts, submit the new sitemap,
   and complete each service's change-of-address flow. This needs Matthew's sign-in.
6. After the redirect check passes, Claude prepares IndexNow submissions for the old and new URL lists.
   Matthew or the approved release runner submits both hosts with each host's valid key. Check that key verification
   still works for each host after the redirect. Do not copy or change key files as part of this kit.

Steps 2, 3 and 5 need Matthew's sign-in: the Cloudflare zone, nameserver change and search consoles.
No account action, live check or submission has been run for this job.
The old host currently uses GitHub Pages, which cannot supply these HTTP 301 responses.

## Plan A2: Cloudflare Bulk Redirects

Use a Bulk Redirect list for the same path and query result on each listed URL. Plan A is preferred because it also
covers unlisted paths and the www hostname. The account, DNS and search console work above still applies.
Import `_launch/bulk-redirects.csv` and create and enable a Bulk Redirect rule that uses that list.
The CSV format follows Cloudflare's reference:
https://developers.cloudflare.com/rules/url-forwarding/bulk-redirects/reference/csv-file-format/

Generate the file from the unchanged old-host sitemap:

```text
python3 _src/redirects.py --csv _launch/bulk-redirects.csv
```

The CSV must not include a header row with column names. It has 320 data rows.
The columns are in this exact order, shown here only as a reference:

```text
source_url,target_url,status_code,preserve_query_string,include_subdomains,subpath_matching,preserve_path_suffix
```

Each row contains the full old HTTPS URL, the full new HTTPS URL, `301`, `true`, `false`, `false`, `false`.
Cloudflare accepts these lowercase boolean values. The paths stay identical, including trailing slashes.
Duplicate URLs appear only once. The inventory is every sitemap URL plus `/llms.txt`, `/sitemap.xml`, `/robots.txt`
and `/privacy/`. Review the import preview before enabling the rule. Keep query preservation on, and subdomain
matching, subpath matching and path suffix copying off.

This exact-match list does not cover unlisted paths, assets outside the inventory, the www host or HTTP variants.
Plan A2 alone cannot pass the extra catch-all probes in `--verify`. Use Plan A for the full launch check.

## Plan B: fallback only

Use this only if Plan A cannot be completed that day. Generate a separate output tree:

```text
python3 _src/redirects.py --stubs /tmp/bookbreaker-launch-stubs
```

Each page has a canonical link to its new URL, a zero-delay meta refresh and one visible link.
The command requires an output directory and refuses the live site tree. It never replaces the current pages by default.
Claude reviews the output before Matthew approves any later release of the fallback pages.

This is not a 301. GitHub Pages still sends 200 for HTML files. Search engines may handle this fallback differently.
HTML written at text or XML paths, such as llms.txt, sitemap.xml and robots.txt, does not create an HTTP redirect.
Those clients may not process a canonical link or meta refresh. Do not replace robots.txt or other protected files
with generated HTML. Plan A is required for real 301 responses for all paths.
The fallback has no external styles, scripts, images or links other than the matching new URL.
It cannot pass `--verify`. Complete Plan A and rerun the real check when the account steps are ready.

## Offline checks

Run `python3 -m unittest discover -s _src/tests -v`.
Tests use stub transports for good and bad responses, including the three extra launch probes.
They never request the live old or new host. No network was used to prepare this fix.
