#!/usr/bin/env bash
set -uo pipefail
cd /mnt/d/hyperdesign2 || exit 1
export GIT_AUTHOR_NAME="HyperDesign 2.0"; export GIT_AUTHOR_EMAIL="hyperdesign2@local"
export GIT_COMMITTER_NAME="HyperDesign 2.0"; export GIT_COMMITTER_EMAIL="hyperdesign2@local"
cat > /tmp/v.txt <<'EOF'
docs(video): 演示视频扩至 122 秒 / 17 段，新增 AI 助手、自动修复、DXF 公差三段

- 第 13 段：Studio「AI 助手」页签真机对话截图
- 第 14 段：助手前中后期职责与越界拒绝
- 第 15 段：工程证据自动修复（5 实体 → 1 轮通过）
- 第 16 段：DXF 四图层与 IT9 公差标注
- 材料清单同步：视频 122 秒、评测报告 14 章 23 页、申报书 23 页 9,207 字
EOF
git add -A
git commit -q -F /tmp/v.txt
git bundle create dist/hyperdesign2.bundle --all >/dev/null 2>&1
echo "commits: $(git rev-list --count HEAD)"
echo "dirty:   $(git status --porcelain | wc -l)"
echo DONE
