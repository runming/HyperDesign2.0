#!/usr/bin/env bash
set -uo pipefail
cd /mnt/d/hyperdesign2 || exit 1
export GIT_AUTHOR_NAME="HyperDesign 2.0"; export GIT_AUTHOR_EMAIL="hyperdesign2@local"
export GIT_COMMITTER_NAME="HyperDesign 2.0"; export GIT_COMMITTER_EMAIL="hyperdesign2@local"

# 1) 忽略终检渲染产物
grep -q '_audit/' .gitignore 2>/dev/null || printf '\n# 终检渲染产物（可随时重生成）\ndocs/_audit/\n' >> .gitignore

# 2) 从索引移除已跟踪的渲染图（保留工作区文件）
git rm -r --cached --quiet docs/_audit 2>/dev/null || true

git add -A
git commit -q -m 'chore: 终检渲染图不入库（docs/_audit 加入忽略）' || echo '(nothing)'
git gc --aggressive --prune=now -q
git bundle create dist/hyperdesign2.bundle --all >/dev/null 2>&1

echo "commits: $(git rev-list --count HEAD)"
echo "files:   $(git ls-files | wc -l)"
echo "git dir: $(du -sh .git | cut -f1)"
echo "bundle:  $(du -h dist/hyperdesign2.bundle | cut -f1)"
echo "dirty:   $(git status --porcelain | wc -l)"
echo DONE
