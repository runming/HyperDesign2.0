#!/usr/bin/env bash
# 初始化 HyperDesign 2.0 仓库 + 提交 + 生成离线 bundle
set -uo pipefail
cd /mnt/d/hyperdesign2

git init -q 2>/dev/null || true
git config user.name 'HyperDesign 2.0'
git config user.email 'hyperdesign2@local'
git add -A

echo "== 暂存文件数: $(git diff --cached --name-only | wc -l)"
echo "== 顶层分布 =="
git diff --cached --name-only | cut -d/ -f1 | sort | uniq -c | sort -rn
echo "== 大于 1MB 的文件 =="
git diff --cached --name-only | while read -r f; do
  if [ -f "$f" ]; then sz=$(stat -c%s "$f"); if [ "$sz" -gt 1048576 ]; then printf "%8d KB  %s\n" $((sz/1024)) "$f"; fi; fi
done | sort -rn | head -5
echo "== 总大小 =="
git diff --cached --name-only | while read -r f; do [ -f "$f" ] && stat -c%s "$f"; done | awk '{s+=$1} END {printf "%.2f MB\n", s/1048576}'

git commit -q -m "HyperDesign 2.0：可验证的工业设计智能体平台（M0–M6 全部通过门禁）

- 受控几何中间表示（CAD-IR）+ 固定白名单解释器：智能体只产出数据，拒绝任意代码执行
- 准入规则引擎（Harness）：四严重级 / 四聚合值 / 受控算子 / 条款引用 / 建议动作；指标缺失判 invalid
- 智能体输出信封 + 技能注册表（6 技能，允许列表与输入校验）
- 工作流引擎：持久化 DAG、事件流 seq/SSE、人工审批门、物理否决、幂等续跑
- Studio 零构建单页：工作流节点 / 三维视窗 / 规则取证 / 知识库 / 审批 / 事件流
- 自研有限元 CAE：Hermite 梁误差 0.0000%；CST 带孔板 Kt=3.128（理论 3.0）
- 知识资产：BM25+向量+RRF、RBAC、证据门控（无证据拒答）
- 参赛材料：申报书（按官方模板填写，仿宋GB2312 五号）、作品介绍 PDF（6 页）
- 六份可复跑门禁报告 + 9 张界面实测截图" 2>&1 | tail -3

echo "== git log =="
git --no-pager log --oneline -2
echo "== 生成 bundle =="
mkdir -p dist
git bundle create dist/hyperdesign2.bundle --all 2>&1 | tail -2
ls -lh dist/hyperdesign2.bundle
echo "REPO_DONE"
