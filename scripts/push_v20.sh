#!/usr/bin/env bash
# 推送到 HyperDesign2.0（一次性令牌从环境变量传入，不写入仓库）
set -uo pipefail
cd /mnt/d/hyperdesign2 || exit 1
export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=/bin/true
: "${REPO_TOKEN:=${1:-}}"
[ -n "${REPO_TOKEN}" ] || { echo "缺少令牌（作为第 1 个参数传入）"; exit 1; }
export REPO_TOKEN          # 必须导出：凭据助手在子 shell 里读取
HELPER='!f() { echo username=x-access-token; echo password=$REPO_TOKEN; }; f'

echo "== 本地状态 =="
git rev-parse --abbrev-ref HEAD
echo "commits: $(git rev-list --count HEAD)  files: $(git ls-files | wc -l)"

echo "== 远端可达性 =="
timeout 90 git -c credential.helper="$HELPER" ls-remote https://github.com/runming/HyperDesign2.0.git 2>&1 | head -5

echo "== 推送 main =="
timeout 600 git -c credential.helper="$HELPER" -c http.postBuffer=52428800 \
    push -u https://github.com/runming/HyperDesign2.0.git HEAD:refs/heads/main 2>&1 | tail -12

echo "== 推送后远端 refs =="
timeout 90 git -c credential.helper="$HELPER" ls-remote https://github.com/runming/HyperDesign2.0.git 2>&1 | head -6
echo PUSH_DONE
