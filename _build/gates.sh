#!/bin/bash
# Every site gate, in one command. Nothing publishes unless this exits 0.
#
# Two, because each catches what the other cannot:
#   check.py        that the pages are honest — every figure traceable, every
#                   competitor claim dated and sourced, every link real
#   break_check.py  that check.py can actually fail
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
if [ "$fail" -ne 0 ]; then echo "SITE RED"; exit 1; fi
echo "SITE GREEN"
