import sys

sys.path.insert(0, r"D:\hyperdesign2\backend")
from app.materials import content as C

print("TABLES keys:", list(C.TABLES.keys()))
for k, v in C.TABLES.items():
    titles = [t["title"][:20] for t in v]
    print(f"  锚点 {k}: {len(v)} 张表 -> {titles}")
print("SECTIONS[42] 段数:", len(C.SECTIONS[42]))
print("表 4 行数:", len(C.TABLES[42][0]["rows"]))
