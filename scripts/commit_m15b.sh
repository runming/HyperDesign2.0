#!/usr/bin/env bash
set -uo pipefail
cd /mnt/d/hyperdesign2 || exit 1
export GIT_AUTHOR_NAME="HyperDesign 2.0"; export GIT_AUTHOR_EMAIL="hyperdesign2@local"
export GIT_COMMITTER_NAME="HyperDesign 2.0"; export GIT_COMMITTER_EMAIL="hyperdesign2@local"
cat > /tmp/m15b.txt <<'EOF'
improve(m15): 真实网格判据改为面积口径，并新增共面合并

- merge_coplanar：法向 ≤0.5° 且面距 ≤0.15mm 的小片合并后重新最小二乘拟合
- analyze 增加 major_planes / top1_area_ratio / top6_area_ratio 三项面积口径指标
- 真实机壳实测：5336 三角面 → 面积占比 ≥1% 的主要平面 11 个，单面最大 1.9%、前六面 31.4%，
  说明机壳主体是曲面细分（拔模面与圆角），单面占比天然偏低；门禁据此断言 ≥8 个主要平面，
  并把实测占比如实写进报告，不夸大
EOF
git add -A
git commit -q -F /tmp/m15b.txt
git bundle create dist/hyperdesign2.bundle --all >/dev/null 2>&1
echo "commits: $(git rev-list --count HEAD)"
echo "dirty:   $(git status --porcelain | wc -l)"
echo DONE
