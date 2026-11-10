#!/usr/bin/env bash
# 提交材料更新并推送（令牌从第 1 个参数传入）
set -uo pipefail
cd /mnt/d/hyperdesign2 || exit 1
: "${REPO_TOKEN:=${1:-}}"
[ -n "${REPO_TOKEN}" ] || { echo "缺少令牌"; exit 1; }
export REPO_TOKEN
export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=/bin/true
export GIT_AUTHOR_NAME="HyperDesign 2.0"; export GIT_AUTHOR_EMAIL="hyperdesign2@local"
export GIT_COMMITTER_NAME="HyperDesign 2.0"; export GIT_COMMITTER_EMAIL="hyperdesign2@local"
HELPER='!f() { echo username=x-access-token; echo password=$REPO_TOKEN; }; f'
URL=https://github.com/runming/HyperDesign2.0.git

git add -A
git commit -q -m "docs: 申报书写入公开仓库与视频直链（HyperDesign2.0 已上线）" || echo "(nothing)"
git bundle create dist/hyperdesign2.bundle --all >/dev/null 2>&1

echo "== push =="
timeout 600 git -c credential.helper="$HELPER" -c http.postBuffer=52428800 \
    push "$URL" HEAD:refs/heads/main 2>&1 | tail -6
echo "== 远端 =="
timeout 90 git -c credential.helper="$HELPER" ls-remote "$URL" 2>&1 | head -3
echo "commits: $(git rev-list --count HEAD)  dirty: $(git status --porcelain | wc -l)"
echo DONE
