#!/usr/bin/env bash
set -uo pipefail
cd /mnt/d/hyperdesign2 || exit 1
: "${REPO_TOKEN:=${1:-}}"
[ -n "${REPO_TOKEN}" ] || { echo "缺少令牌"; exit 1; }
export REPO_TOKEN GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/true
HELPER='!f() { echo username=x-access-token; echo password=$REPO_TOKEN; }; f'
URL=https://github.com/runming/HyperDesign2.0.git
echo "== 完整 push 输出 =="
timeout 300 git -c credential.helper="$HELPER" push "$URL" HEAD:refs/heads/main 2>&1 | sed -e 's/^/  /'
echo "== 现有分支 =="
timeout 60 git -c credential.helper="$HELPER" ls-remote --heads "$URL" 2>&1
echo DONE
