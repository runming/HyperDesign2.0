#!/usr/bin/env bash
set -uo pipefail
cd /mnt/d/hyperdesign2 || exit 1
export GIT_AUTHOR_NAME="HyperDesign 2.0"; export GIT_AUTHOR_EMAIL="hyperdesign2@local"
export GIT_COMMITTER_NAME="HyperDesign 2.0"; export GIT_COMMITTER_EMAIL="hyperdesign2@local"
cat > /tmp/m1617.txt <<'EOF'
feat(m16,m17): 工程证据自动修复闭环 + DXF 尺寸公差标注

M16 自动修复（GeomVerity 式 Self-Correction）
- backend/app/harness/repair.py：参数预检 + 证据→补丁→重建→再裁决，最多 2 轮
- 实测：实体数 5（立柱悬空）→ POST_H 抬到 H−WALL → 1 轮通过；拔模 0.9°→1.8°；
  壁厚 2.0→2.4 并同步立柱高；包络严重不符时**不硬修**如实回报
- 助手新增「修复」意图，对话里可直接说"能不能修好"
- 门禁 m16 6/6 PASS

M17 DXF 工程图（尺寸+公差，而非光轮廓）
- backend/app/caddraw/dxf_writer.py：R12 ASCII 自带写出器（零第三方依赖）
- 四图层分工：CUT_PROFILE / HIDDEN_LINE / DIMENSIONS / TITLE_BLOCK
- 公差按 GB/T 1800.1 IT9 自动查表写入尺寸文本（%%p0.087 等 CAD 控制码）
- 中文用 \U+XXXX 转义，几何保持纯 ASCII；ezdxf 独立复核 AC1009、audit 0 错误
- 门禁 m17 6/6 PASS
EOF
git add -A
git commit -q -F /tmp/m1617.txt
git bundle create dist/hyperdesign2.bundle --all >/dev/null 2>&1
echo "commits: $(git rev-list --count HEAD)"
echo "files:   $(git ls-files | wc -l)"
echo "dirty:   $(git status --porcelain | wc -l)"
echo DONE
