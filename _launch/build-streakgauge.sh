#!/bin/zsh
# Rebuild ~/streakgauge-site from the sources: build and gate into a fresh temp folder, then sync (keeping its .git).
set -euo pipefail
repo=${0:A:h:h}
target=${1:-$HOME/streakgauge-site}
tmp=$(mktemp -d)
nice -n 19 python3 "$repo/_src/launch.py" "$tmp/site"
mkdir -p "$target"
rsync -a --delete --exclude .git "$tmp/site/" "$target/"
echo "synced to $target (temp build left at $tmp/site for inspection)"
