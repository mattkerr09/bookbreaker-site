#!/bin/bash
# Every site gate, in one command. Nothing publishes unless this exits 0.
#
# Two, because each catches what the other cannot:
#   check.py        that the pages are honest — every figure traceable, every
#                   competitor claim dated and sourced, every link real
#   break_check.py  that check.py can actually fail
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
echo "── site check ─────────────────────────────────────"
python3 _build/check.py --app-repo "${APP_REPO:-../arb betting aqpp}" || fail=1
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
if [ "$fail" -ne 0 ]; then echo "SITE RED"; exit 1; fi
echo "SITE GREEN"
