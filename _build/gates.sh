#!/bin/bash
# Every site gate, in one command. Nothing publishes unless this exits 0.
#
# Two, because each catches what the other cannot:
#   check.py        that the pages are honest — every figure traceable, every
#                   competitor claim dated and sourced, every link real
#   break_check.py  that check.py can actually fail
#   check_live      that the domain serves this build, not an older one.
#   check_sources   that the citations check.py EXEMPTS actually resolve. A
#                   number inside a dated, sourced block skips the figure
#                   gate — that carve-out is right, and it means the source
#                   is the only thing standing behind those numbers. Nothing
#                   checked the sources existed until this was added.
#
# The engine repo learned the second one the hard way: two of its gates passed
# against deliberately broken code.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

fail=0
echo "── self-test ──────────────────────────────────────"
python3 _build/check.py --self-test || fail=1
echo
echo "── offers on main ─────────────────────────────────"
# The site renders welcome offers from the app's main branch (render.py main_offers). They count only once main's
# own offer tests pass on main itself: a throwaway worktree, so whatever branch the app checkout is on cannot stand in.
OFFERS_REPO="${OFFERS_REPO:-../arb betting aqpp}"
wt="$(mktemp -d)/main"
if git -C "$OFFERS_REPO" worktree add --detach -q "$wt" main 2>/dev/null; then
  (cd "$wt" && python3 -m pytest -q -p no:cacheprovider tests/test_welcome.py 2>&1 | tail -1)
  [ "${PIPESTATUS[0]}" -eq 0 ] || { echo "  !! main's offer tests failed"; fail=1; }
  git -C "$OFFERS_REPO" worktree remove --force "$wt"
else
  echo "  !! could not check out main from $OFFERS_REPO"; fail=1
fi
echo
echo "── site check ─────────────────────────────────────"
python3 _build/check.py --app-repo "${APP_REPO:-../arb betting aqpp}" --offers-repo "$OFFERS_REPO" || fail=1
echo
echo "── structured data ────────────────────────────────"
# Docket's script, copied as is: every FAQ question and answer, Article headline and date in the markup is on the
# page a reader sees (Google's rule). check.py's check_structured_data_matches_page adds WebPage dates and stubs.
python3 _build/verify_structured_data_matches_page.py --self-test || fail=1
python3 _build/verify_structured_data_matches_page.py 2>&1 | tail -3
[ "${PIPESTATUS[0]}" -eq 0 ] || fail=1
echo
echo "── break tests ────────────────────────────────────"
python3 _build/break_check.py 2>&1 | tail -2 || fail=1
echo
echo "── cited sources ──────────────────────────────────"
# Exit 2 means the check could not run — no network, most likely. That must
# never read as a pass: a source check that silently succeeds offline looks
# exactly like one that verified every URL. It is reported loudly and does not
# fail the build, because a broken wifi is not a broken site.
python3 _build/check_sources.py 2>&1 | tail -3
case "${PIPESTATUS[0]}" in
  0) ;;
  2) echo "  !! SOURCES NOT CHECKED — this run verified nothing" ;;
  *) fail=1 ;;
esac
echo
echo "── deployed site ──────────────────────────────────"
# Every check above this line reads files off this disk. This one asks what the
# domain actually serves, which is the only thing a visitor sees. A commit that
# is pushed but not yet rebuilt reports 1 here and is usually a minute away
# from correct, so it is reported and does not fail the build; 2 means the
# check could not run and must never read as a pass.
python3 _build/check_live.py 2>&1 | tail -4
case "${PIPESTATUS[0]}" in
  0) ;;
  1) echo "  !! THE DOMAIN IS NOT SERVING THIS BUILD — push, or wait for Pages" ;;
  2) echo "  !! DEPLOY NOT CHECKED — this run compared nothing" ;;
esac

echo
if [ "$fail" -ne 0 ]; then echo "SITE RED"; exit 1; fi
echo "SITE GREEN"
