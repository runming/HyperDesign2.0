#!/usr/bin/env bash
set -uo pipefail
cd /mnt/d/hyperdesign2 || exit 1
: "${REPO_TOKEN:=${1:-}}"
[ -n "${REPO_TOKEN}" ] || { echo "缺少令牌"; exit 1; }
export REPO_TOKEN GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/true
export GIT_AUTHOR_NAME="HyperDesign 2.0"; export GIT_AUTHOR_EMAIL="hyperdesign2@local"
export GIT_COMMITTER_NAME="HyperDesign 2.0"; export GIT_COMMITTER_EMAIL="hyperdesign2@local"
HELPER='!f() { echo username=x-access-token; echo password=$REPO_TOKEN; }; f'
URL=https://github.com/runming/HyperDesign2.0.git

PAT_PREFIX="github""_pat_"
if grep -rln "$PAT_PREFIX" --include='*.py' --include='*.sh' --include='*.md' . 2>/dev/null; then
  echo "仍有令牌，终止"; exit 2
fi

git add -A
if ! git diff --cached --quiet; then
  git commit -q -m "docs: README 顶部加在线仓库与视频链接"
  echo "已提交 README 更新"
else
  echo "无待提交内容"
fi

echo "local:  $(git rev-parse --short HEAD)"
timeout 600 git -c credential.helper="$HELPER" -c http.postBuffer=52428800 \
    push "$URL" HEAD:refs/heads/main 2>&1 | sed -e 's/^/  /'
echo "remote: $(timeout 60 git -c credential.helper="$HELPER" ls-remote "$URL" refs/heads/main | cut -c1-7)"
echo "commits: $(git rev-list --count HEAD)  dirty: $(git status --porcelain | wc -l)"
echo DONE
