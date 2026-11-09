#!/usr/bin/env bash
# 推送 HyperDesign 2.0 到 GitHub 的 v2.0 分支（fail-fast，带超时与进度）
set -uo pipefail
cd /mnt/d/hyperdesign2

export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=/bin/true
export GIT_HTTP_LOW_SPEED_LIMIT=1000
export GIT_HTTP_LOW_SPEED_TIME=60
TOKEN="${REPO_TOKEN:?}"
HELPER='!f() { echo username=x-access-token; echo password=$REPO_TOKEN; }; f'

echo "== 本地分支 =="
git branch
echo "== 提交 =="
git --no-pager log --oneline -3
echo "== 开始推送（超时 300s） =="
timeout 300 git -c credential.helper="$HELPER" -c http.postBuffer=52428800 \
    push https://github.com/runming/HyperDesign.git HEAD:refs/heads/v2.0 2>&1 | tail -8
echo "== 推送后远程 refs =="
timeout 60 git -c credential.helper="$HELPER" ls-remote https://github.com/runming/HyperDesign.git 2>&1 | head -6
echo "PUSH_DONE"
