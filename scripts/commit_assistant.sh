#!/usr/bin/env bash
set -uo pipefail
cd /mnt/d/hyperdesign2 || exit 1
export GIT_AUTHOR_NAME="HyperDesign 2.0"; export GIT_AUTHOR_EMAIL="hyperdesign2@local"
export GIT_COMMITTER_NAME="HyperDesign 2.0"; export GIT_COMMITTER_EMAIL="hyperdesign2@local"
git rev-parse --is-inside-work-tree || { echo "NOT A REPO"; exit 1; }
git add -A
git commit -q -F docs/poc/_msg.txt && rm -f docs/poc/_msg.txt
git bundle create dist/hyperdesign2.bundle --all >/dev/null 2>&1
echo "commits: $(git rev-list --count HEAD)"
echo "files:   $(git ls-files | wc -l)"
echo "dirty:   $(git status --porcelain | wc -l)"
echo "bundle:  $(du -h dist/hyperdesign2.bundle | cut -f1)"
echo DONE
