#!/usr/bin/env bash
set -uo pipefail
cd /mnt/d/hyperdesign2 || exit 1
export GIT_AUTHOR_NAME="HyperDesign 2.0"; export GIT_AUTHOR_EMAIL="hyperdesign2@local"
export GIT_COMMITTER_NAME="HyperDesign 2.0"; export GIT_COMMITTER_EMAIL="hyperdesign2@local"
cat > /tmp/msync.txt <<'EOF'
docs: M14–M17 同步进参赛材料（评测报告 14 章 / 申报书新增 AI 协作与解析特征两节）

- 评测报告扩为 14 章 23 页：新增 交互式助手 / 网格解析特征恢复 / 证据自动修复 / DXF 公差
- 申报书：实现方案补 (9) 交互式协作与证据自校正、(10) 解析特征恢复与公差图纸；
  创新点补「七：AI 协作越界即拒」「八：把 AI 网格还原成可验证机械特征」
- 申报书附录门禁清单扩为 ⑭ 项（新增 M14–M17）
- 修正评测报告章节结论识别（此前会把表格里的"未通过项"误判为章节未通过）
- 终检：四份材料无空白页；一致性核对 PASS
EOF
git add -A
git commit -q -F /tmp/msync.txt
git bundle create dist/hyperdesign2.bundle --all >/dev/null 2>&1
echo "commits: $(git rev-list --count HEAD)"
echo "dirty:   $(git status --porcelain | wc -l)"
echo DONE
