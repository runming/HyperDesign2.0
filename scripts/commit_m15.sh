#!/usr/bin/env bash
set -uo pipefail
cd /mnt/d/hyperdesign2 || exit 1
export GIT_AUTHOR_NAME="HyperDesign 2.0"; export GIT_AUTHOR_EMAIL="hyperdesign2@local"
export GIT_COMMITTER_NAME="HyperDesign 2.0"; export GIT_COMMITTER_EMAIL="hyperdesign2@local"
cat > /tmp/m15.txt <<'EOF'
feat(cadrefit): 网格→解析特征恢复（平面/圆柱）+ 误差证书（M15 6/6 通过）

- backend/app/cadrefit/mesh_analytic.py：STL 解析、法向聚类分平面、圆柱基元优先识别+内点精化、
  逐特征 RMS/MAX 误差证书（仅 numpy）
- 关键顺序：孔壁/圆角由多个平面小片组成，必须先识别圆柱再聚类平面，否则会被平面吃掉
- 实测：长方体三向尺寸 100/60/30 恢复误差 0.000mm；圆柱管 R5 恢复误差 0.000mm、覆盖 352.5°；
  σ=0.05mm 噪声下仍 ≤0.05mm；容差收紧到 0.0005mm 时证书判不通过
- 门禁 scripts/m15_analytic_fit.py：6/6 PASS；报告 docs/poc/M15-ANALYTIC-FIT.md
EOF
git add -A
git commit -q -F /tmp/m15.txt
git bundle create dist/hyperdesign2.bundle --all >/dev/null 2>&1
echo "commits: $(git rev-list --count HEAD)"
echo "dirty:   $(git status --porcelain | wc -l)"
echo DONE
