#!/usr/bin/env bash
# 修正 HEAD（去掉令牌）后推送；令牌从第 1 个参数传入
set -uo pipefail
cd /mnt/d/hyperdesign2 || exit 1
: "${REPO_TOKEN:=${1:-}}"
[ -n "${REPO_TOKEN}" ] || { echo "缺少令牌"; exit 1; }
export REPO_TOKEN GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/true
export GIT_AUTHOR_NAME="HyperDesign 2.0"; export GIT_AUTHOR_EMAIL="hyperdesign2@local"
export GIT_COMMITTER_NAME="HyperDesign 2.0"; export GIT_COMMITTER_EMAIL="hyperdesign2@local"
HELPER='!f() { echo username=x-access-token; echo password=$REPO_TOKEN; }; f'
URL=https://github.com/runming/HyperDesign2.0.git

echo "== 复核：工作区不应再有令牌 =="
PAT_PREFIX="github""_pat_"
if grep -rln "$PAT_PREFIX" --include='*.py' --include='*.sh' --include='*.md' . 2>/dev/null; then
  echo "仍有令牌，终止"; exit 2
fi
echo "  工作区干净"

echo "== amend HEAD（保留原父提交，仅替换本提交内容） =="
git add -A
git commit -q --amend -m "docs: 申报书写入公开仓库与视频直链（HyperDesign2.0 已上线）" --no-edit 2>/dev/null || \
  git commit -q --amend -m "docs: 申报书写入公开仓库与视频直链（HyperDesign2.0 已上线）"
git log --oneline -2

echo "== 复核历史 =="
git log --oneline -S "$PAT_PREFIX" --all 2>/dev/null | head -5 || echo "  历史无令牌"

echo "== push =="
timeout 600 git -c credential.helper="$HELPER" -c http.postBuffer=52428800 \
    push "$URL" HEAD:refs/heads/main 2>&1 | sed -e 's/^/  /' | tail -10
echo "== 远端 =="
timeout 60 git -c credential.helper="$HELPER" ls-remote "$URL" 2>&1 | head -3
echo DONE
