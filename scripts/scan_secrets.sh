#!/usr/bin/env bash
# 密钥扫描（避免在脚本里写出 PAT 字面量，用变量拼接模式）
set -uo pipefail
cd /mnt/d/hyperdesign2 || exit 1
PAT_PREFIX="github""_pat_"
echo "== 工作区命中 =="
grep -rln "$PAT_PREFIX" --include='*.py' --include='*.sh' --include='*.md' --include='*.json' . 2>/dev/null || echo "(无)"
echo "== 历史命中提交 =="
git log --oneline -S "$PAT_PREFIX" --all 2>/dev/null | head -10 || echo "(无)"
echo DONE
